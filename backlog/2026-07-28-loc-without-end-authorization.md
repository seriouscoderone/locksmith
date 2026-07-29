# A location that arrived without its authorization was accepted as an endpoint

**Status:** fixed by `2026-07-28-peer-endpoint-not-a-real-eid.md` · **Raised:** 2026-07-28 · **Priority:** was medium (unauthorized-address pairing)

## What we saw

Filed for the record because the failure mode is worth knowing about even though the
same change closed it.

The old peer read path asked `db.locs.get(keys=(aid, tcp))` and treated any url it found
as the peer's endpoint, never consulting the `/end/role` record that authorizes it. A
`/loc/scheme` can land *without* its authorization — this is not theoretical. Spiking
byte corruption on a known-good peer OOBI (duplicating one character, the damage a real
re-bake hit in transit) produced exactly that:

| damage | result |
|---|---|
| duplicate a char near the front | nothing lands, no exception |
| duplicate a char in the last third | **`/loc/scheme` lands, `/end/role/add` dropped** |
| truncate to 60% | KEL lands, endpoint rpys dropped |

In the middle case the old code paired the peer at an address nothing had vouched for,
and reported success. keripy's `Parser.parse` swallows per-message framing errors, so
there was no exception to notice either.

The instance that mattered most was not the pairing dialog but the **open-inbound
first-contact gate** (`peer/shim.py` `_first_contact_accepted`). Its whole job is
deciding whether to talk to a stranger, and its stated rule is "KEL verified AND it
published a reachable tcp loc-scheme" — but it read `db.locs` directly, so the second
half of the rule was not actually being checked. Now covered by
`tests/core/test_open_inbound.py::test_first_contact_requires_the_address_to_be_authorized`.

## Resolution

`peer/resolution.py` walks `cid → ends[peer] → eid → locs[eid]` and requires both halves,
so an unauthorized location does not resolve. Pinned by
`tests/peer/test_resolution.py::test_an_unauthorized_location_is_not_resolved` and
`tests/core/test_oobi_import.py::test_a_location_without_its_authorization_is_not_accepted`.

Worth keeping in mind for any *other* code that reads `db.locs` directly: the location
store is not an authorization store. Grep before trusting it.

## Evidence / references

- `src/locksmith/peer/resolution.py`
- Former call sites: `peer/exposure.py:40`, `core/direct_transport.py:134`,
  `ui/vault/peers/add_dialog.py:333`, `peer/oobi_import.py`
- `keripy/src/keri/core/eventing.py:5063` (`processReplyLocScheme` — accepts a loc on its
  own signature alone; authorization is a separate record by design)
