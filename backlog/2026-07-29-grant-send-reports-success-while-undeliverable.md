# The admin's grant "sends" while undeliverable — silent loss on the return leg

**Status:** backlog · **Raised:** 2026-07-29 · **Priority:** high (first live test lost the grant with no error on either side)

## What we saw

First live two-machine test (v0.3.6): admin issued and granted to a requester whose advertised
endpoint was unreachable (Parallels NAT + Windows Firewall). The admin-side send fell back from
peer to mailbox (`peer/posting.py:105-112`, `SendOutcome.FALLBACK`) — but the requester has no
mailbox endpoints, so the inner `StreamPoster.deliver()` had nowhere to route and the grant was
lost. Nothing surfaced on either side:

- **Admin:** the stock grant flow does not treat a fallback as a failure. `PeerAwarePoster`
  records `last_outcome = FALLBACK` and the legacy `SendGrantDoer` proceeds; the operator sees
  "sent". (Contrast: the REQUESTER's own sends have a loud direct-mode contract —
  `RequestFlow`'s outcome listener and `ServiceaidApplyDoer` both fail loudly on a non-peer
  channel. The admin's grant path has no equivalent.)
- **Requester:** peer mode is push-only; there is nothing to poll, so a restart shows nothing.
  The card stays PENDING forever.
- **No post-mortem trail:** Locksmith logs go to the console handler only — a Finder/installed
  launch leaves no log file, so the `peer.send.peer_failed` / `fallback_mailbox` lines that
  would have diagnosed this in one look were never persisted anywhere.

## The actual work

1. **Loud fallback on the admin's grant path:** when a grant's delivery outcome is not "peer"
   AND the recipient has no mailbox ends, surface a visible failure ("couldn't reach <label>'s
   wallet — it may be behind a firewall or NAT") instead of implying success. The channel is
   already reported (`last_outcome`); this is UI/policy, not transport.
2. **Durable outbox / retry:** an undeliverable grant should stay queued and re-attempt when the
   peer's health probe next reports reachable (`db.peerHealth` already tracks this), rather than
   being one-shot.
3. **Rotating file log** (small, separable): persist the structured log lines to a per-app-data
   file so installed builds can be diagnosed post-hoc. Task-1's Connection page shows *state*;
   this is the missing *history*.
4. Note: the durable fix for the scenario itself is the mailbox role
   (`2026-07-28-network-independent-delivery-mailbox-role.md`) — this entry is about never
   lying about delivery, whichever channels exist.

## Evidence / references

- `peer/posting.py:88-112` (fallback path) · `core/ipexing.py` (legacy `SendGrantDoer` tail)
- `ui/onboarding/request_flow.py:384-401` (the loud contract the admin path lacks)
- Live test 2026-07-29: apply arrived (VM→Mac outbound through NAT), grant lost (Mac→VM inbound
  blocked), zero errors surfaced.
