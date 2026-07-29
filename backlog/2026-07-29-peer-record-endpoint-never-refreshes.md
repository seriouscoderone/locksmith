# A known peer's cached endpoint never refreshes — an address change is permanent until unpair (and there is no unpair)

**Status:** backlog · **Raised:** 2026-07-29 · **Priority:** high (blocks the live-test retest after any requester address change)

## What we saw

Planning the bridged-networking retest after the first live test: the admin's allowlist already
holds a `PeerRecord` for the requester with the Parallels NAT address (`tcp://10.211.55.x:…`),
auto-registered at first contact. After the VM switches to bridged networking it gets a new
LAN address — and nothing on the admin side will ever pick it up:

- `_register_first_contact_peer` fires **only for unknown senders** (`peer/shim.py` gate 1 →
  `_first_contact_accepted` is reached only when `allowlist.contains(sender)` is false). A
  known sender's fresh in-band `/loc/scheme` rpy lands in `db.locs` via BADA (newer datestamp
  wins) — the *data* updates, but
- `peer_send` dials `PeerRecord.endpoint_url` — the cached pairing state — not `db.locs`
  (deliberately not converted in the EID work; see the status note in
  `2026-07-28-peer-endpoint-not-a-real-eid.md`). The route cache is stale forever.
- There is no unpair/edit UI to fix it by hand
  (`2026-07-28-paired-peers-cannot-be-unpaired.md`), so a poisoned record is permanent
  short of a DB script.

Net: any requester address change (VM re-network, DHCP renewal, laptop moves desks) silently
re-breaks the return leg even when the new address is perfectly reachable, and the failure
mode is the same silent mailbox-fallback loss as
`2026-07-29-grant-send-reports-success-while-undeliverable.md`.

## The actual work

This is the concrete, already-bitten slice of `2026-07-28-single-route-per-peer.md`:

1. On send (or on health-probe failure), re-resolve the recipient's current routes from the
   KERI state (`db.ends`/`db.locs` via `peer/resolution.py` — authorization-recency ordered)
   and prefer them over / refresh the cached `PeerRecord.endpoint_url`. BADA already
   guarantees the newer signed rpy wins in the data layer; the route cache just has to stop
   ignoring it.
2. A known sender's in-band rpys arriving with a NEWER loc than the cached record should
   update the record (label and paired_at preserved) — the same recency logic
   `ensure_direct_transport` already applies to bundled-authority re-pins.
3. Regression test: pair at address A, deliver a newer signed `/loc/scheme` for address B,
   assert the next send dials B.

## Evidence / references

- `peer/sending.py` (dials the cache) · `peer/shim.py` (`_first_contact_accepted` known-sender
  gap) · `core/vaulting.py` (`_register_first_contact_peer`)
- `peer/resolution.py` (recency-ordered native resolution, built by the EID work)
- Siblings: `2026-07-28-single-route-per-peer.md` (the general fix),
  `2026-07-28-paired-peers-cannot-be-unpaired.md`,
  `2026-07-29-grant-send-reports-success-while-undeliverable.md`
- Live context: first two-machine test 2026-07-29; admin holds `10.211.55.x` for the requester.
