# Locksmith Direct Peer Mode — Design

**Status:** Spec draft. No implementation yet.

**Date:** 2026-05-27

## Goal

Let two Locksmith wallets on the same LAN or VPN exchange KERI peer messages (IPEX, KEL replay, OOBI resolution, signing handlers, etc.) directly over TCP, without relying on a shared witness/mailbox for the message-carrying hop. The witness is still used at pairing time to disseminate OOBIs; after that, traffic is wallet-to-wallet.

## Motivation

Locksmith today is wired exclusively for indirect mode: outbound exns go through the recipient's mailbox (currently bundled into their witness). For two wallets on the same network, the witness round-trip is unnecessary overhead and an unnecessary infrastructure dependency. A direct-mode peer transport is the simplest way to drop that hop.

Locksmith already ships most of the building blocks. The `locksmith.turret` module wires a keripy `Directant` to a Unix Domain Socket at `/tmp/keripy_kli.s` and exposes the full handler stack (IPEX, KEL, OOBI, sign, verify, decrypt, witness-auth) to a local browser-plugin shim. The bytes between the wallet and the plugin shim are the same KERI direct-mode CESR stream that would flow between two wallets — only the socket family is local. Direct peer mode is, concretely, "add an `AF_INET` listener next to the existing `AF_UNIX` one and gate it on an allowlist."

## Non-goals (MVP)

- TLS / on-the-wire encryption. KERI signatures cover integrity and authenticity. Privacy on the link is provided by the deployment context (VPN at L3, trusted L2 on home LAN). TLS is the natural v2.
- mDNS / Bonjour auto-discovery. Manual OOBI exchange is sufficient and works across VPN segments.
- NAT traversal / hole punching. The deployment is assumed to be a network where both wallets can route to each other directly.
- A standalone mailbox service. `mailbox.keri.host` is a separate effort; this design is compatible with it but does not depend on it.
- Per-handler gating. The new transport exposes the same handler set the UDS transport exposes today. No selective surfacing.

## Architecture

The vault gains a second direct-mode listener parallel to the existing `TurretDoer`. Both share the handler stack; they differ on the socket family, the gating model, and the lifecycle.

| | `TurretDoer` (today) | `PeerDoer` (new) |
|---|---|---|
| Socket | `AF_UNIX` at `/tmp/keripy_kli.s` | `AF_INET` on configured port |
| Gate | Single-AID match (sender == `plugin_identifier`) | Allowlist of paired peer AIDs + per-AID destination opt-in |
| Lifecycle | Always on while vault open | Off by default; opt-in via setting; on/off independent of vault state |
| Trust source | "Same-machine = trusted process" | "OOBI-resolved peer AID + signature on every message" |

Reused as-is: `keri.peer.exchanging.Exchanger`, every `*Handler` in `locksmith/turret/handling.py`, the `Directant`/`Reactant` flow (driven by a TCP server instead of a UDS one), and `Authenticator` for the per-message signature check.

Allowlist enforcement happens in one place: `PeerExchangerShim` inspects each inbound `exn` and verifies (a) the sender AID is in the paired-peers allowlist and (b) the destination AID has `role=peer` currently opted in. The destination AID is read off the exn envelope (recipient field on the exn `ked`) — whichever field name keripy currently uses for the exn recipient. Either gate failing drops the message and closes the connection. The handler stack itself stays untouched.

## Components

New code lives under `src/locksmith/peer/`. Existing files touched are listed at the end.

### Transport

- **`src/locksmith/peer/tcp.py`** — `TCPServer`, `TCPServerDoer`. Mirrors `turret/uxd/serving.py` but uses `AF_INET` + `SO_REUSEADDR`. Configurable bind address (default `0.0.0.0`) and port.
- `locksmith.turret.directing.Directant` — reused, instantiated with the new TCP server instead of the UDS one.

### Gate

- **`src/locksmith/peer/shim.py`** — `PeerExchangerShim`. Replaces `ExchangerShim`'s single-AID match with a two-step allowlist check (sender + destination). Drops rejected messages and emits a structured WARN log.
- **`src/locksmith/peer/allowlist.py`** — `PeerAllowlist`. Thin wrapper over a new Komer subkey (`peer.`) on `LocksmithBaser`. Stores `PeerRecord(aid, label, endpoint_url, paired_at, last_contacted_at)`.

### Doer

- **`src/locksmith/peer/doer.py`** — `PeerDoer(doing.DoDoer)`. Construction mirrors `TurretDoer` but takes a config (port, bind interface, enabled). Composes the TCP server doer, the `Directant`, and `PeerExchangerShim`.

### Vault integration

- `src/locksmith/core/vaulting.py` — extend the existing doer set: instantiate `PeerDoer` when `vault.settings.peer_mode.enabled` is true.
- `LocksmithBaser` — add a `peer_mode` settings record (enabled, port, bind interface, advertised host).

### OOBI plumbing

- Register a new role, `peer`, with the habery's role registry. Each opted-in AID publishes a `role=peer` endpoint authorization on its KEL pointing at `tcp://<advertised-host>:<port>`.
- The OOBI URL for the peer role takes the standard witness-served form during MVP: `http://<witness>/oobi/<controller-aid>/peer/<endpoint-aid>`. The witness serves the controller's KEL with the role authorization; no Locksmith-side HTTP service is added. This means pairing still touches a witness; the message-carrying hops after pairing do not.

### UI surfaces

- `src/locksmith/ui/vault/settings/page.py` — new "Direct peer mode" section (see §UX below).
- `src/locksmith/ui/vault/identifiers/identifier_sections.py` — add `Peer` to the OOBI roles dropdown and surface the peer-OOBI URL prominently.
- New `src/locksmith/ui/vault/peers/list.py` — "Paired peers" page.

## Data flow

### Pairing (one-time, both directions)

Both wallets enable peer mode (§5a) and opt the relevant AIDs in (§5b). Each AID's KEL now carries a `role=peer` endpoint authorization pointing at the local `tcp://host:port`. The peer-OOBI URL — served by the witness — embeds that binding.

Alice copies Bob's peer-OOBI into her wallet's "Add peer" dialog. The OOBI resolves through the witness; Locksmith fetches Bob's KEL, verifies the role authorization, and inserts a `PeerRecord` for Bob into the allowlist. Bob does the symmetric resolve for Alice. After this, both wallets have each other's AID + endpoint stored locally and the witness is no longer in the picture for the messaging hop.

### Outbound send (Alice → Bob)

The existing IPEX UI flow builds the signed `exn` message exactly as it does today. `Locksmith.send_exn` then chooses a channel:

1. If the destination AID has a `PeerRecord` with a reachable endpoint, open TCP to `tcp://<bob-host>:<bob-port>` and write the CESR-framed exn + attachments.
2. If the TCP connect fails or times out, **silently fall back to the mailbox path** (per user direction). The exn is sent via the recipient's published mailbox endpoint.
3. If neither succeeds, the existing send-failure UX takes over.

The send result includes a channel badge surfaced in the outbound notification toast and the issued-credentials list: `peer`, `mailbox`, or `peer→mailbox` (fallback used).

### Inbound

Bob's `PeerDoer` accepts the TCP connection. The first `exn` is read and handed to `PeerExchangerShim`:

- Sender AID not in Bob's paired-peers allowlist → drop, log `peer.gate.sender_rejected`, close connection.
- Destination AID does not currently have `role=peer` opted in → drop, log `peer.gate.destination_not_exposed`, close connection.
- Both gates pass → forward to the existing `Exchanger`, which runs signature verification and dispatches to the appropriate handler. From the handler's perspective, nothing changed.

Non-CESR bytes on the socket trip the `Parser`; the connection closes with a DEBUG-level log (likely a port scanner, not interesting).

## Endpoint OOBI shape & wire protocol

### OOBI artifact

A new role `peer` registered with habery. Endpoint URL is `tcp://<host>:<port>`. The OOBI URL form during MVP is the standard witness-served URL: `http://<witness>/oobi/<controller-aid>/peer/<endpoint-aid>`. This reuses the URL-based OOBI machinery already wired into KERI/Locksmith.

A CESR-blob OOBI (witness-less, fully self-contained) is a strict UX upgrade and is deferred to v2.

### Wire protocol

Vanilla KERI direct mode: a CESR-framed stream over TCP. No HTTP, no JSON-RPC. The same `exn` messages (`/ipex/grant`, `/ipex/admit`, `/oobi`, etc.) that flow through a witness mailbox today are written as raw CESR bytes onto the socket. The receiving wallet's `Parser` + `Exchanger` chain handles them with zero new code.

Each outbound send opens a fresh TCP connection, writes the framed exn(s) plus attachments, and closes once the send is acknowledged at the transport layer. Inbound mirrors this — accept connection, parse incoming exn(s), close when the stream ends or after handler dispatch. No long-lived sockets, no keep-alives, no reconnect logic in v1. This matches the per-exchange pattern from keripy's stock direct-mode `Director`/`Reactor`.

### Port and bind address

- Default port: **5621** (unregistered, low-collision; finalize before merge).
- Default bind: `0.0.0.0` (all interfaces). Configurable per-interface for VPN-only deployments.
- Advertised host in the OOBI: user picks from a dropdown of detected interfaces.

## UX surfaces

Two levels: the listener is vault-wide; the role authorization is per-AID.

### Vault settings — "Direct peer mode" section (vault-level: the listener)

- On/off toggle for the listener itself (default off). Off here = TCP socket is not bound; no AID is reachable via peer mode regardless of per-AID state.
- Port input (default 5621).
- Bind interface dropdown (`All interfaces` / per-detected-NIC).
- Advertised host dropdown — detected IPs; the chosen one is what goes into every opted-in AID's peer-OOBI URL.
- Status line: "Listening on `0.0.0.0:5621`" / "Stopped" / "Port in use — pick another".
- Read-only count: "N AIDs opted in" (links to the identifiers page).

### Identifier detail page — `Peer` as a first-class OOBI role (AID-level: authorization)

The existing OOBI roles dropdown gains a `Peer` row. Independently per AID:

- "Expose this AID over peer mode" toggle. ON = publish `role=peer` with the vault's advertised endpoint URL into this AID's KEL. OFF = no authorization; this AID is not reachable via the shared socket even when the listener is up.
- When on: peer-OOBI URL ready to copy, "Copy" button, "Show QR" button — same visual weight as the witness OOBI row.
- Disabled with explainer when the vault-level listener is off ("Turn on direct peer mode in vault settings to expose this AID.").

The set of AIDs whose `role=peer` is currently on is the **destination allowlist** for inbound exns.

### Paired peers page

A new page under the vault menu listing all `PeerRecord` rows: label, advertised endpoint, paired-at, last-contacted-at.

- "Add peer" button → dialog accepting a peer-OOBI URL (paste or QR scan). On resolve+verify, inserts a `PeerRecord` and refreshes.
- Per-row "Unpair" action removes the record from the allowlist; future inbound connections from that AID drop.
- Per-row "Test connection" opens TCP, sends a noop exn, closes; surfaces reachable / not-reachable for diagnostics.

### Outbound channel indicator

Per the auto-fallback rule, sends don't prompt the user. The completion notification and the issued-credentials list include a small badge per outbound exn: `peer`, `mailbox`, or `peer→mailbox` for the fallback case.

## Security model

Two allowlists plus KERI signature verification. Each gate maps to UI state the user already controls.

| Gate | Where it lives in UI | What it stops |
|---|---|---|
| **Sender allowlist** | "Paired peers" list — managed via the pairing flow | Random AIDs delivering exns to you |
| **Destination allowlist** | The per-AID `Peer` role toggle | Even a paired peer reaching an AID you didn't expose |
| **Signature verification** | Existing `Exchanger` + `Parser` chain — unchanged | Tampering, impersonation |

The TCP socket itself is not a gate — any peer who knows the port can open a connection; they just don't get past the sender allowlist without prior pairing.

Out-of-scope for MVP (plain-TCP consequences):

- Passive sniffing on the link — mitigated by deployment context (VPN encrypts at L3; home LAN is trusted L2). TLS upgrade is v2.
- DoS by an allowlisted peer — mitigation is unpair. No rate limiting in v1.

## Error handling & lifecycle

### Lifecycle

- **Vault open + peer mode enabled** → `PeerDoer` constructed; TCP server binds. If bind fails (port in use, EACCES, permission denied), the doer logs ERROR, surfaces the failure in the settings status line, stays in "Stopped." Vault opens normally — peer mode is degraded, not fatal.
- **Vault open + peer mode disabled** → no `PeerDoer` constructed; no socket bound.
- **Toggling peer mode mid-session** → starts/stops the `PeerDoer` cleanly via `DoDoer` add/remove; no vault restart.
- **Vault close** → `PeerDoer` is part of the vault's doer set; closes with everything else. In-flight connections drop (no draining for MVP).
- **Network change** (VPN connects/disconnects, IP changes) → the listener stays bound to whatever interface was selected. If the advertised IP is no longer reachable, peer connections fail and auto-fall-back to mailbox. The user re-publishes their peer-OOBI with the new IP when they notice.

### Pairing errors (Add peer dialog)

- Malformed OOBI URL → inline validation error.
- OOBI fetch fails (witness unreachable, no network) → "Couldn't reach the witness serving this OOBI. Try again."
- OOBI resolves but signature check on the KEL fails → "Couldn't verify this peer's KEL. The OOBI may be tampered." Dialog stays open; no record inserted.
- Duplicate AID already paired → "This peer is already paired" + jump to the existing row.

### Send errors (auto-fallback)

- Peer's TCP endpoint refuses / times out → silent fallback to mailbox; outbound badge shows `peer→mailbox`.
- Both peer and mailbox fail → existing send-failure UX.

### Receive errors

- Non-CESR bytes on the socket → `Parser` errors; connection closed; DEBUG log.
- CESR parses but sender AID not in allowlist → dropped + WARN log `peer.gate.sender_rejected` with sender AID and remote IP.
- CESR parses, sender allowlisted, destination AID not opted in → dropped + WARN log `peer.gate.destination_not_exposed`.
- Signature verification fails → existing handler-stack error path; logged; not delivered.

## Testing

Three layers. Integration tests must hit real components — no DB mocks. UI tests must be machine-checkable via structured log lines emitted by the production code.

### Unit tests — one file per new module

- `PeerAllowlist`: insert / contains / remove / list, persistence across reopen (real Komer, temp DB).
- `PeerExchangerShim`: forwards exn when sender in allowlist; drops + WARN when not; drops + WARN when destination AID not opted-in.
- `tcp.TCPServer.openAndBind`: bind succeeds on free port; clean failure when port held by a fixture socket; clean failure on EACCES privileged port.
- `PeerDoer` construction wires the three components correctly (snapshot of contained doers).

### Integration tests — two real vaults, no mocks

Reuse the dual-vault pattern already in use (HOME isolation). Tests live in `tests/integration/peer/`.

- **Pairing happy path** — vault A and vault B each have an AID with witness W. A's wallet calls "Add peer" with B's peer-OOBI → allowlist contains B → and vice-versa. Verified by reading the allowlist Komer after the resolve.
- **End-to-end IPEX over peer mode** — pairing done, A grants a credential to B with mailbox bind skipped. Verify B's `Exchanger` cues fire and a notification queues. A's outbound badge in the structured log = `peer`.
- **Auto-fallback** — pairing done, B's listener stopped. A grants → connect fails → A retries via mailbox. Outbound badge in A's log = `peer→mailbox`. B receives via mailbox.
- **Sender rejection** — A connects to B's listener with an AID B never paired. B drops the exn, logs `peer.gate.sender_rejected` with sender AID + remote IP, no notification.
- **Destination rejection** — A is paired with B, but the destination AID on B has `role=peer` toggled off. B drops the exn, logs `peer.gate.destination_not_exposed`, no notification.

### UI smoke via `locksmith-ui-tester`

- Open vault → toggle peer mode on → assert log `peer.listener.started port=5621`.
- Open identifier → toggle Peer role on → assert log `peer.role.enabled aid=…`.
- Click "Add peer" → paste OOBI → assert log `peer.pair.success aid=… endpoint=…` and the row appears in the Paired Peers list (queryable via the harness).
- Toggle peer mode off → assert log `peer.listener.stopped`.

### Structured log lines (added for testability)

One line per event, key=value pairs:

- `peer.listener.started`, `peer.listener.stopped`, `peer.listener.bind_failed`
- `peer.role.enabled`, `peer.role.disabled`
- `peer.pair.success`, `peer.pair.failed`
- `peer.gate.sender_rejected`, `peer.gate.destination_not_exposed`
- `peer.send.attempt`, `peer.send.peer_ok`, `peer.send.peer_failed`, `peer.send.fallback_mailbox`
- `peer.recv.delivered`

## Open questions

- Default port `5621` is a placeholder. Worth checking IANA assignments and common port collisions before merging.
- The CESR-blob OOBI (witness-less pairing) is deferred but worth scoping as v2 once `mailbox.keri.host` and peer mode are both shipped.
- Multi-witness controllers: when an opted-in AID has multiple witnesses, the peer-OOBI URL has to pick one to be served from. Trivial — pick the first available — but worth noting.
(none currently open beyond the above)

## Files touched (summary)

New:

- `src/locksmith/peer/__init__.py`
- `src/locksmith/peer/tcp.py`
- `src/locksmith/peer/shim.py`
- `src/locksmith/peer/allowlist.py`
- `src/locksmith/peer/doer.py`
- `src/locksmith/ui/vault/peers/list.py`
- `src/locksmith/ui/vault/peers/add_dialog.py`
- `tests/integration/peer/test_pairing.py`
- `tests/integration/peer/test_send.py`
- `tests/integration/peer/test_gates.py`
- `tests/unit/peer/test_allowlist.py`
- `tests/unit/peer/test_shim.py`
- `tests/unit/peer/test_tcp.py`
- `tests/unit/peer/test_doer.py`

Modified:

- `src/locksmith/core/vaulting.py` — wire `PeerDoer` into the vault's doer set when enabled.
- `src/locksmith/db/basing.py` — add the `peer.` Komer subkey for the allowlist and a settings record for `peer_mode`.
- `src/locksmith/ui/vault/settings/page.py` — add the "Direct peer mode" section.
- `src/locksmith/ui/vault/identifiers/identifier_sections.py` — add `Peer` to the OOBI roles dropdown.

## References

- KERI / ACDC / CESR specs available locally at `/Users/seriouscoderone/KERI/code/kerihost/scripts/markdown` for citation when implementing.
- `keri.app.directing` (upstream) — the stock TCP-based direct-mode Director/Reactor/Directant/Reactant pattern that this design follows.
- `locksmith/turret/*` — the existing UDS direct-mode pipeline being mirrored.
