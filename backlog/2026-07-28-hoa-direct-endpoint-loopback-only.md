# HOA direct-mode endpoint is loopback-only — remote requests can never connect

**Status:** SHIPPED 2026-07-28 — merged to `development` at `38d1aea3` (all five items, incl. the
re-baked artifact `tcp://192.168.1.162:5621`; unit suite 1416 passed with the endpoint guard green).
Residual risks moved to siblings: DHCP-lease drift of the baked address →
`2026-07-28-network-independent-delivery-mailbox-role.md` (evidence) — re-bake against the overlay
address once Tailscale lands; `open_inbound` still required admin-side →
`2026-07-28-first-contact-approval-inbox.md`.

**Raised:** 2026-07-28 · **Priority:** ~~high (blocks the first live two-machine role request)~~

## What we saw

Tracing the Usurance HOA "request a role" flow for a co-worker on another machine: it cannot
work, in either direction, and there is no way to fix it from the shipped UI.

1. **Outbound.** `brands/usurance/egf/oobis/EGjm-X1JMz-….cesr` — the bundled authority OOBI —
   carries a signed `/loc/scheme` rpy with `"url":"tcp://127.0.0.1:5621"`.
   `ensure_direct_transport` pairs the authority straight from that blob and writes the
   `PeerRecord` from `db.locs` (`core/direct_transport.py:111`). The requester's wallet dials
   *its own* loopback. The rpy is signed by the admin AID, so the URL cannot be text-edited —
   `parse_oobi_cesr` rejects a tampered blob.
2. **Reply path.** `core/direct_transport.py:84` hardcodes `advertised_host="127.0.0.1"`, so the
   in-band OOBI the requester sends (`core/serviceaid_bridge.py:155`) advertises
   `tcp://127.0.0.1:<port>`. The admin registers that and replies to its *own* loopback.
3. **Unfixable in the field.** `HoaVaultPage` peels identifiers/settings/peers
   (`ui/vault/hoa_page.py:38`), so an HOA build has no peer-settings section, no Add Peer dialog,
   no peer-OOBI export, and no way to see the listener port or peer health.
4. **Poisoned permanently.** `ensure_direct_transport` skips pairing when a `PeerRecord` already
   exists (`core/direct_transport.py:99`), so a bad endpoint never self-corrects — the same shape
   as the stale-mailbox-OOBI freeze (`reference_stale_mailbox_oobi_freeze`).

Symptom to the user: clicking **Request** returns *"the administrator's application isn't
reachable — is it running?"* (`core/serviceaid_bridge.py:560`), with nothing actionable behind it.

## Why it shipped this way

Every prior test of this flow used in-process transport — `tests/integration/test_multi_role_e2e.py`
says so explicitly ("the live two-app demo is the transport acceptance"). The network leg has
never been exercised, so loopback was never wrong in any test that ran.

## The actual work

1. **Advertised host is discovered, not hardcoded.** Replace the literal `"127.0.0.1"` at
   `core/direct_transport.py:84` with primary-interface auto-detection, plus a brand/env override
   for when the answer is ambiguous. *Note:* once an overlay (Tailscale/WireGuard) is up, the same
   auto-detect returns the overlay address — no separate code path. The override exists precisely
   for the both-present case.
2. **Re-bake the Usurance authority OOBI** with a routable endpoint, generated from the
   usurance-custody vault (it must be re-signed; a hand-edit is not possible).
3. **Regression guard:** a test asserting no shipped brand's `egf/oobis/*.cesr` contains a
   loopback or `0.0.0.0` URL. This bug class will recur every time an artifact is baked from a
   dev machine — the guard is worth more than the fix.
4. **Re-pair on endpoint change.** `ensure_direct_transport` must refresh a `PeerRecord` whose
   bundled endpoint no longer matches, rather than skipping. Failing that, a bad bake is
   permanent for every install that ever saw it.
5. **Minimal connection/diagnostics surface in the peeled HOA shell** — listener port, advertised
   address, per-peer reachability (`db.peerHealth` is already populated by
   `PeerHealthMonitorDoer`). Today nothing is inspectable in the field and there is no in-app log
   viewer, so the only diagnosis path is launching the `.app` binary from a terminal.

## Sequencing note

Item 2 re-bakes an artifact whose *shape* changes under
`2026-07-28-peer-endpoint-not-a-real-eid.md` (A0). Doing this first means re-baking twice.
Re-baking is cheap (regenerate + rebuild), so this is an accepted cost if the live test is
wanted before A0 lands — but it is a real choice, not an oversight.

## Evidence / references

- Bundled artifact: `brands/usurance/egf/oobis/EGjm-X1JMz-yKFeumEZ9meSVNvnV8VTXmjJMlyBVMMTO.cesr`
- `core/direct_transport.py:84,93,99,111` · `core/serviceaid_bridge.py:155,560`
- `ui/vault/hoa_page.py:38` (the peel) · `peer/health.py` (health data already collected)
- Sibling: `2026-07-28-peer-endpoint-not-a-real-eid.md`,
  `2026-07-28-network-independent-delivery-mailbox-role.md`
- Related memory: `reference_stale_mailbox_oobi_freeze`, `project_peer_mode_shipped`
