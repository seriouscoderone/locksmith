# A peer can only have one route — no LAN-plus-public, no ordered fallback

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** medium (blocked on the EID work)
**Blocked by:** ~~`2026-07-28-peer-endpoint-not-a-real-eid.md`~~ — UNBLOCKED 2026-07-28.
`peer/resolution.py` returns all authorized routes (ordered by authorization recency) and
`peer/listener_eid.py` mints per alias, so multi-EID is expressible. Still to do: `PeerRecord`
holding N routes, the selector, and the policy-declaration decision.

## What we saw

Asked: "when I define my reachability, can I have several — a Tailscale one and a globally
addressable one?" KERI and the EGF both say yes. Locksmith says no, at three separate layers.

- **KERI — yes.** `db.ends` is keyed `(cid, role, eid)`: one AID can authorize many EIDs for the
  same role (that is how witnesses work). But `db.locs` is keyed `(eid, scheme)` — **one URL per
  scheme per EID**. So multiplicity lives at the EID level; two tcp routes means two EIDs. With
  today's `eid == cid` you get exactly one tcp address per AID, full stop.
- **EGF — yes.** `Authority.endpoints` is a list, and unknown `mode` values are carried rather
  than rejected (`keri_serviceaid/egf/documents.py:57-61,144`). Declaring `direct` + `mailbox`
  needs no schema change.
- **Locksmith — no.** `PeerRecord.endpoint_url` is a single string (`peer/records.py:11`);
  `peer_send` dials that one URL (`peer/sending.py:47-82`); `direct_authorities` takes the
  **first** `mode == "direct"` endpoint and breaks (`core/direct_transport.py:35-45`).

## Selection policy is the interesting half

There is no ordering primitive to inherit — keripy picks at **random** among witness/mailbox EIDs
(`forwarding.py:209` `random.choice`). Fine for equivalent relays, wrong for "prefer the fast LAN
path, fall back to the relay."

The input for a better policy already exists: `PeerHealthMonitorDoer` probes every paired peer on
a cadence and writes `reachable / refused / timeout / unreachable` into `db.peerHealth`
(`peer/health.py`). "Try the route that was healthy 60s ago, fall back on failure" is reachable
with machinery already present — it just needs somewhere to put the second route.

**Open question, and it is a governance question not a transport one:** "prefer direct, fall back
to mailbox" leaks presence on a LAN; "always mailbox" leaks metadata to the relay. That posture
probably belongs declared in the EGF next to the endpoints rather than hardcoded in the wallet.
Decide before implementing the selector.

## The actual work

1. `PeerRecord` holds N routes (ordered), not one `endpoint_url`. Migration for existing records.
2. `peer_send` walks routes in policy order, honouring `db.peerHealth`, falling through on
   failure, and reporting *which* route succeeded (the channel is already surfaced to the UI via
   `PeerAwarePoster.last_outcome`).
3. `direct_authorities` stops taking only the first endpoint; carries the full declared set.
4. Decide + implement where selection policy is declared (EGF vs wallet default).

## Evidence / references

- `peer/records.py:11` · `peer/sending.py:47-82` · `core/direct_transport.py:35-45`
- `peer/health.py` (health data already collected, unused for routing)
- `keri_serviceaid/egf/documents.py:57-61,144` (endpoint list is already plural)
- Siblings: `2026-07-28-peer-endpoint-not-a-real-eid.md`,
  `2026-07-28-network-independent-delivery-mailbox-role.md`
