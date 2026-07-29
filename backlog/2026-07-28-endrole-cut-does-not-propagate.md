# An /end/role/cut never reaches anyone — revocation doesn't propagate over OOBI

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** high (peer-mode revocation is not effective for already-paired peers)

## What we saw

`Hab.replyEndRole` — the thing behind `replyToOobi`, which builds both the offline
pairing blob and the bundled brand artifact — exports only records that are *currently
authorized*:

```python
# keripy/src/keri/app/habbing.py:2480-2483
for (_, erole, eid), end in self.db.ends.getTopItemIter(keys=(cid,)):
    if (end.enabled or end.allowed) and ...:
        msgs.extend(self.loadLocScheme(eid=eid, scheme=scheme))
        msgs.extend(self.loadEndRole(cid=cid, eid=eid, role=erole))
```

`loadEndRole` has the same guard. A cut record has `enabled`/`allowed` false, so it is
skipped — **a `/end/role/cut` is structurally unable to appear in an exported OOBI
stream.** Confirmed against real keripy: after retiring an endpoint, the re-exported
blob contains no `/end/role/cut` at all (pinned in
`tests/core/test_oobi_import.py::test_an_install_on_the_old_shape_upgrades_to_the_new_one`).

Two consequences, one of which is a live correctness problem:

1. **Endpoint retirement doesn't reach peers.** When a controller moves its endpoint and
   cuts the old authorization, an install that already learned the old one keeps it
   forever and now holds two routes. Mitigated in `peer/resolution.py` by preferring the
   most recently authorized route (using keripy's own `db.eans` → `db.sdts` datestamps,
   the same pair BADA compares), so the current address wins and the stale one degrades
   to a fallback. That is a mitigation, not a fix.

2. **Turning "Expose over peer mode" OFF does not revoke for anyone already paired.**
   `PublishPeerRoleDoer(allow=False)` publishes the cut locally and to the AID's
   witnesses, so a *witness-served* OOBI stops serving the role. But every already-paired
   peer holds a `PeerRecord` with a cached `endpoint_url` and dials it directly, and no
   re-exported blob can tell them otherwise. For a witness-less peer pairing — the
   offline blob and the HOA's bundled artifact, i.e. how peer mode is actually used —
   revocation is currently unobservable to the counterparty.

That second point deserves emphasis: the exposure toggle reads as a security control and
does not behave like one for the population that matters.

## The actual work

1. Decide what revocation *means* for a direct peer channel and make the UI honest about
   it. Turning exposure off stops the listener from accepting (there is a
   `is_destination_exposed` gate in `PeerDoer`), which is the real enforcement — the
   endpoint record is only discovery metadata. If enforcement is local, the toggle's
   copy should say so rather than implying the peer is told.
2. For endpoint *movement*, the recency preference in `peer/resolution.py` is probably
   enough and needs no protocol change. Confirm that judgement before building anything
   heavier.
3. If cuts genuinely need to travel, the mechanism has to be something other than
   `replyToOobi` — an explicit exn to known peers, or a nullifying `/loc/scheme` (which
   *does* export, since the loc record still exists with an empty url). Worth checking
   whether upstream keripy considers the `replyEndRole` filter intentional; a cut is a
   signed statement and there is an argument it should be disseminable.
4. Relatedly: `db.locs` nullification (`url=""`) does export. Whether an empty url
   arriving for a still-authorized EID should clear a cached `PeerRecord.endpoint_url` is
   unspecified today.

## Evidence / references

- `keripy/src/keri/app/habbing.py:2480-2483` (`replyEndRole`), `:2256-2257`
  (`loadEndRole` guard)
- `src/locksmith/peer/resolution.py` (`peer_role_eids` recency sort — the mitigation)
- `src/locksmith/peer/publishing.py` (`allow=False` path)
- `src/locksmith/peer/doer.py` (`is_destination_exposed` — where enforcement actually is)
- `tests/core/test_oobi_import.py::test_an_install_on_the_old_shape_upgrades_to_the_new_one`
- Surfaced by `2026-07-28-peer-endpoint-not-a-real-eid.md`
