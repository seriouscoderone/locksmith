# Role requests only work on a shared network — mailbox role is the network-independent path

**Status:** backlog — **DEFERRED by user 2026-07-29** (no internet-hosted mailbox yet; direct-mode
LAN posture for now via bridged VM networking + Windows firewall rule). Note when picking this
back up: a mailbox does NOT have to be internet-hosted — a LAN-local mailbox (e.g. one machine in
the office) gives always-on delivery within the network without any public exposure; the
internet-hosted one is only needed for cross-network reach. · **Raised:** 2026-07-28 ·
**Priority:** high (this is what makes the flow work "on any network")

## What we saw

Direct-mode peer TCP is the *only* declared channel for the Usurance authority
(`brands/usurance/egf/…EPyySfoR….json` → `endpoints: [{mode: "direct", scheme: "tcp"}]`). That
makes the role-request flow topology-bound: it can work on one LAN, or over an overlay, but never
between two arbitrary networks — RFC1918 addresses do not route between them. Making direct TCP
work across arbitrary networks means NAT traversal (STUN/TURN/hole-punching), which is a large
lift and not KERI's problem to solve.

KERI's own answer to "this AID is not directly reachable" is the **mailbox endpoint role**. Per
BE KERI NATIVE, reachability of an AID is a KERI-core concern with a KERI primitive — reach for
it rather than building a Locksmith-specific discovery/overlay abstraction.

## Three findings that make this much cheaper than it sounds

1. **The transport dispatch already exists.** `PeerAwarePoster` does peer-first-then-mailbox
   fallback (`peer/posting.py:88`).
2. **The EGF already supports it.** `Endpoint.mode` is forward-compatible — unknown modes are
   carried, not rejected. An authority can declare `direct` *and* `mailbox` with no schema change.
3. **The eligibility conflict we expected is not real.** Adding a mailbox does **not** require
   witnesses: keripy's `StreamPoster.deliver()` checks `{controller, agent, mailbox}` roles
   **first**, with witnesses only as `elif` (`keripy/src/keri/app/forwarding.py:343-352`). A
   witnessless AID with a designated mailbox role routes fine and stays `serviceaid_eligible`
   (`core/serviceaid_bridge.py:106` only checks `hab.kever.wits`). The HOA's
   `default_witnesses = []` bootstrap survives intact.

**So the blocker is mostly policy, not plumbing.** `ServiceaidApplyDoer` treats any non-`peer`
channel as a loud failure (`core/serviceaid_bridge.py:560`), and `RequestFlow` does the same for
grants (`ui/onboarding/request_flow.py:397`). Correct today, when direct is the only declared
channel. Wrong the moment mailbox is a legitimate route.

## Evidence update (2026-07-29, FIRST LIVE TWO-MACHINE TEST) — this item is now proven necessary

v0.3.6 live test: HOA on a Windows VM (Parallels, Shared/NAT networking) successfully applied to
the admin's Locksmith over peer TCP — **outbound through NAT works**. The GRANT never arrived:
the VM's advertised address (`10.211.55.x`, Parallels-only) is unroutable from the LAN, Windows
Defender Firewall blocks unsolicited inbound anyway (the MSI registers no rule), so the admin's
`peer_send` timed out and fell back to mailbox — and the requester has no mailbox, so the grant
evaporated. Restarting the requester cannot help: peer mode is push-only, there is nothing to
poll. This is the exact scenario this entry predicts. **Acceptance case for the fix: an HOA on a
NAT'd, firewalled machine receives the grant with zero user configuration.**

## Evidence update (2026-07-28, post loopback fix)

The loopback fix (`38d1aea3`) baked `tcp://192.168.1.162:5621` — a **DHCP lease**. When it
changes, the shipped artifact is stale for every install and nothing detects it; the re-pair
logic only helps after someone bakes and ships *again*. Third independent argument (after machine
replacement and overlay enrollment) that baked wallet addresses are structurally fragile and the
durable answer is an address the operator controls — a mailbox — plus multi-route. Near-term
mitigations: DHCP reservation for the admin machine; re-bake with the overlay/MagicDNS name once
Tailscale lands (the endpoint guard already permits DNS names).

## Scope note — mailbox is universal, not mandatory

An overlay network (Tailscale/WireGuard, SSO'd to the corporate M365/Entra tenant) gives the same
"any network" property with no relay, lower latency and no metadata leak — a good fit while
`usurance-internal` stays a **closed** employee ecosystem (`"openness": "closed"` in the EGF).
The counter-argument is durability: an overlay address is still *a laptop's* address, so a machine
replacement means a dead baked route and a rebuild. A mailbox address is a **service you operate**
and changes on your schedule.

With the EID work landed, an AID declares both and transport picks — this is not a one-way door.

## The actual work

1. Consume `mode: "mailbox"` endpoints on an EGF authority; dispatch by role.
2. HOA first-run designates a mailbox endpoint role for the default AID (stays witnessless, stays
   serviceaid-eligible). Mailbox AID sourced from `[bootstrap]` brand config.
3. Replace "non-peer channel = failure" with **"failed only if no declared channel succeeded"** at
   both call sites (`serviceaid_bridge.py:560`, `request_flow.py:397`).
4. Requester subscribes/polls its mailbox for the inbound grant (WS notify-and-fetch is already
   proven live — memory `project_mailbox_architecture_phases`).
5. usurance-custody designates a mailbox too, so applies land while it is asleep or behind NAT.

## Known gap this exposes

**Confidentiality.** Peer mode ships no TLS by deliberate choice, so a relay that sees plaintext
CESR sees credential contents. Signatures mean a hostile mailbox cannot forge or authorize
anything — the worst it does is fail to deliver (availability) or observe metadata. But
confidentiality is a real open question. See
`2026-07-28-peer-transport-confidentiality.md`.

## Evidence / references

- `peer/posting.py:88` · `core/serviceaid_bridge.py:106,560` · `ui/onboarding/request_flow.py:397`
- `keripy/src/keri/app/forwarding.py:343-352` (mailbox role checked before witness)
- Memory: `project_mailbox_architecture_phases`, `reference_mailbox_keri_host`,
  `feedback_tls_dropped`
- Siblings: `2026-07-28-peer-endpoint-not-a-real-eid.md`, `2026-07-28-single-route-per-peer.md`
