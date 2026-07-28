# A corrupted OOBI stream reports "no_peer_role" — blaming the operator's config for byte damage

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** low-medium (diagnostics; fold into the EID read-side rewrite)

## What we saw

During the authority re-bake (loopback-fix task, merged `38d1aea3`), a peer-OOBI blob was
corrupted in transit — three CESR couples gained one duplicated character each
(`0A…A` sn field, 25 chars instead of 24). keripy's `Parser.parse` swallows per-message framing
errors, so the stream desynchronized and **nothing landed, with no exception**. The error surfaced
to the operator was `no_peer_role` — *"The peer may not have 'Expose over peer mode' enabled"* —
i.e. stream corruption reported as a configuration mistake on the other person's wallet.

That is the most misleading possible message: it sends the operator to toggle settings on a
machine that did nothing wrong.

The incident also proved the guard half works: `scripts/bake_authority_oobi.py`'s re-verify
refused to write the corrupted artifact. Detection is fine; *attribution* is the bug.

## The actual work

In `parse_oobi_cesr` (`src/locksmith/peer/oobi_import.py`), distinguish three outcomes instead of
two:

1. **Stream consumed nothing / desynchronized** (parser advanced but no kevers, locs, or ends
   changed) → "this blob appears damaged — re-copy it" class of error.
2. **AID landed but no peer role/loc** → the existing `no_peer_role` message (now truthful).
3. Success.

A byte-corruption regression test exists in spirit from the incident — pin it: truncate/duplicate
a character inside a couple of a known-good blob and assert the *damaged-stream* error, not
`no_peer_role`.

## Evidence / references

- Incident: archived session "Fix HOA loopback-only peer endpoint" (2026-07-28); memory
  `feedback_never_retype_long_blobs`.
- `src/locksmith/peer/oobi_import.py` (`parse_oobi_cesr`, incl. the new `expect=` form)
- Natural home: the read-side rewrite in `2026-07-28-peer-endpoint-not-a-real-eid.md`.
