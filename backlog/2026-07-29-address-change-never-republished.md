# A changed advertised address is never re-published — the wallet's own announcement stays stale forever

**Status:** backlog · **Raised:** 2026-07-29 · **Priority:** high (ROOT CAUSE of both live delivery failures; the admin-side refresh does not fix it alone)

## What we saw

Two live two-machine tests, two lost grants, one root cause. `ensure_direct_transport`
(`core/direct_transport.py`) is **asymmetric** between its own steps:

```python
# step (1): re-pins settings whenever the resolved address MOVED  ✅
if (settings is None or not settings.enabled
        or settings.advertised_host != advertised):
    ...pin(PeerModeSettings(advertised_host=advertised, ...))

# step (2): publishes the signed rpy ONLY on first exposure       ❌
if hab.pre not in vault._peer_exposed_aids:      # rehydrated from db.ends on open
    vault.extend([PublishPeerRoleDoer(..., url=f"tcp://{settings.advertised_host}:{port}")])
```

`_peer_exposed_aids` is rehydrated from persisted end records at vault open, so once an AID has
*ever* been exposed, `PublishPeerRoleDoer` never runs again. The wallet therefore re-detects its
new address, updates settings, renders the new address on the Connection page — and keeps
serving a **signed `/loc/scheme` rpy carrying the OLD one**, indefinitely.

Live evidence (2026-07-29, second test — a real co-worker's laptop, `ECi0wVTxNIQT…`):

```
requester's Connection page:   tcp://192.168.1.237:5622      (settings — correct)
admin's db.locs for that AID:  tcp://127.0.0.1:5622          (the signed rpy — stale)
admin's PeerRecord:            tcp://127.0.0.1:5622          (cached from the rpy)
```

The requester's app had first opened before its network was up, so auto-detect fell back to
loopback, published *that*, and never corrected it. Every grant dialed the admin's own loopback
and died silently.

## Why the sibling fix is not sufficient

`2026-07-29-peer-record-endpoint-never-refreshes.md` makes the admin **re-resolve from KERI state**
(`db.ends`/`db.locs`) instead of trusting a cached `PeerRecord`. Correct and necessary — but on
2026-07-29 the admin's `db.locs` *also* held `127.0.0.1`, because no newer rpy ever arrived. The
full chain needs three links, and only two are in flight:

1. **Requester re-publishes when its address changes** ← MISSING (this entry)
2. Admin picks up the newer announcement ← `…-peer-record-endpoint-never-refreshes.md`
3. Undeliverable sends fail loudly ← `…-grant-send-reports-success-while-undeliverable.md`

Note the in-band OOBI path (`_inband_oobi_msgs`) builds its rpy **fresh from settings** at send
time, so a *new* apply does carry the current address — which is why "ask the user to request
again" happens to work as a manual workaround, and why this stayed invisible until a request was
sent before the network settled.

## Also affected: OOBI export

`generate_oobi(role="peer")` and the offline `locksmith-peer-oobi:v1:` blob export the **stored**
rpys, so both carry the stale address too. Anyone pairing from a copied blob after an address
change gets a dead endpoint.

## The actual work

1. Re-publish on change, not on first exposure: when step (1) re-pins a *different*
   `advertised_host` (or port), run `PublishPeerRoleDoer` again so a later-dated `/loc/scheme`
   supersedes the old one via BADA. Decouple "is exposed" from "is published at the current
   address" — `_peer_exposed_aids` answers the wrong question for this guard.
2. Same treatment for the non-HOA path: the per-AID *Expose over peer mode* toggle
   (`ui/vault/identifiers/identifier_sections.py`) publishes at toggle time only; a stock-wallet
   AID has the identical staleness after a network change.
3. **Prevention — block the foot-gun at the source.** Both incidents shipped a request that
   advertised an unroutable address. A request whose advertised host is loopback/unspecified
   should warn (or refuse) at send time: *"this workspace can't be reached at 127.0.0.1 — check
   your network connection"*. Cheap, and it would have prevented **both** live failures rather
   than merely repairing them afterwards.
4. Consider whether an address change should proactively re-announce to already-paired peers
   (an exn to known peers) rather than waiting for the next apply. Relates to
   `2026-07-28-endrole-cut-does-not-propagate.md` — the same "our announcements don't travel
   after the fact" family.

## Evidence / references

- `core/direct_transport.py` steps (1) vs (2); `core/vaulting.py` (`_peer_exposed_aids`
  rehydration from `peer_exposure.exposed_pres`)
- `core/serviceaid_bridge.py` `_inband_oobi_msgs` (builds fresh from settings — the reason the
  manual workaround works)
- Live tests 2026-07-29: VM (`EIZ3sySCTHmJ…`, NAT address) and co-worker laptop
  (`ECi0wVTxNIQT…`, loopback). Both required hand-patching the admin's LMDB to deliver.
- Siblings: `2026-07-29-peer-record-endpoint-never-refreshes.md`,
  `2026-07-29-grant-send-reports-success-while-undeliverable.md`,
  `2026-07-28-single-route-per-peer.md`
