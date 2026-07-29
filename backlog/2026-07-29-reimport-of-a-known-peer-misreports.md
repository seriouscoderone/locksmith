# Re-pasting a known peer's OOBI blob reports "no peer-role endpoint" — the one self-serve repair a user can attempt, misdiagnosed

**Status:** backlog · **Raised:** 2026-07-29 · **Priority:** medium (blames the wrong operator; the user's only workaround looks like the peer's misconfiguration)

## What we saw

Found while building the two-wallet regression for
`2026-07-29-peer-record-endpoint-never-refreshes.md`
(`tests/integration/peer/test_route_refresh_e2e.py`). A peer moves address and
re-publishes; the user pastes that peer's freshly-exported
`locksmith-peer-oobi:v1:` blob into **Add Peer** to pick up the new address —
the only self-serve repair available, since there is no unpair/edit UI
(`2026-07-28-paired-peers-cannot-be-unpaired.md`). The dialog answers:

> The blob parsed but no AID inside it published a peer-role tcp endpoint.
> Either the peer doesn't have 'Expose over peer mode' enabled on any
> identifier, or the token was damaged in transit — …

Every clause is false. The peer *is* exposed, the token is *intact*, and the
newer `/loc/scheme` **did** land (BADA accepted it — the parse happens before
any of this). The user is told to go re-check the other operator's settings.

## Why

`peer/oobi_import.py:import_peer_blob` builds its candidate list from AIDs that
became newly known by this parse:

```python
pre_kevers = set(hby.kevers.keys())
parser.parse(...)                       # rpys land here — including the newer loc
new_kevers = [p for p in hby.kevers.keys() if p not in pre_kevers]
candidates = [expect] if expect is not None else new_kevers   # <-- empty on re-import
for pre in candidates: ...              # never runs
```

For an already-known AID `new_kevers` is empty, so the success branch is
unreachable and control falls through to the `no_peer_role` raise. The
already-paired check in `AddPeerDialog._on_pair` sits *after* the
`import_peer_blob` call, so it never gets to answer either. `expect=` is
supplied only by the HOA bundled-authority path (`core/direct_transport.py`),
which is why this never showed up there.

Note the parse side effect is genuinely useful and worth preserving: it is what
lets the admin-side route refresh pick the new address up. The bug is purely in
what the function *reports*.

## The actual work

1. Candidates should be "the AIDs this blob is about", not "the AIDs this parse
   newly taught us" — e.g. every controller AID with a peer-role authorization
   found in the parsed stream, or track the CIDs seen in the accepted
   `/end/role` rpys. Then a re-import of a good blob resolves and returns
   normally.
2. Let `AddPeerDialog` distinguish the cases it actually has: already-paired
   (and, once (1) lands, "already paired — endpoint updated to <url>") versus a
   genuinely unexposed peer versus a damaged token.
3. Regression test: import a blob for an already-known AID and assert it
   resolves rather than raising `no_peer_role`.

## Evidence / references

- `peer/oobi_import.py:70-103` (`new_kevers` → `candidates`)
- `ui/vault/peers/add_dialog.py:182-207` (`import_peer_blob` before the
  already-paired check)
- Reproduced by `tests/integration/peer/test_route_refresh_e2e.py`, which
  asserts only that pairing was *refused* and documents the wrong message
- Siblings: `2026-07-28-paired-peers-cannot-be-unpaired.md`,
  `2026-07-29-peer-record-endpoint-never-refreshes.md`,
  `2026-07-29-address-change-never-republished.md`
