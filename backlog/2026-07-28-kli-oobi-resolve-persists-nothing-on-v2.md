# `kli oobi resolve` exits 0 but persists nothing on the v2 base — and `Receiptor` swallows the consequence

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** medium (root cause of the dark release gate; the *tests* are fixed, the underlying trap is not)

## What we saw

While fixing `tests/integration/test_publisher_roundtrip.py`
(`2026-07-28-publisher-roundtrip-tests-broken.md`), both tests turned out to share **one**
root cause, not two. Instrumented evidence from the test harness, immediately after a
`kli oobi resolve` that exited **0**:

```
DIAG after oobi resolve      alive=True
DIAG fetchUrls(http)  = Mict([])
DIAG fetchUrls(https) = Mict([])
DIAG httpClient RAISED MissingEntryError: unable to query witness BJQ9…, no http endpoint
DIAG db.locs http = None
DIAG db.ends wit  = None
DIAG ICP  sn=0 wigs=0 toad=1 wits=['BJQ9…']
DIAG Receiptor pass returned cleanly       <-- 0.1s, contacted nobody
DIAG IXN  sn=1 wigs=0
```

Two separate defects compound here:

**1. `kli oobi resolve` is a silent no-op for persistence on v2.** It exits 0, prints nothing
alarming, and leaves the keystore with **no** loc-scheme and **no** end-role record for the
resolved AID. This is already known folklore — memory `project_publisher_v2_reset_shipped`
records "v2 kli-oobi-resolve persists nothing (seed witness discovery into fresh v2
keystores)" — but nothing in the repo enforces or documents it, so a test and a CLI hook were
both written against the assumption that it works.

**2. `Receiptor` converts a missing endpoint into silence.** `keri/app/agenting.py:96-100`:

```python
for wit in wits:
    try:
        client, clientDoer = httpClient(hab, wit)
        ...
    except (MissingEntryError, gaierror) as e:
        logger.error(f"unable to create http client for witness {wit}: {e}")
```

`httpClient` raises `MissingEntryError` when `hab.fetchUrls(eid=wit)` is empty
(`agenting.py:1070-1072`). The exception is caught and only **logged**, so `clients` stays
empty, the receipt loop is skipped, and the generator returns *cleanly* having contacted zero
witnesses. Callers cannot distinguish "no witness had a receipt yet" from "I never asked
anybody". `publish._wait_for_receipts` then burns its full 120s and reports
`only 0/1 witness receipts` — a timeout message for what is actually a configuration error.

## Why it matters

The publisher's own `anchor` path depends on exactly this: `Receiptor` reaching each witness
in `hab.kever.wits`. Off-CI publishing has worked only because the real publisher keystore was
seeded by hand at some point. Any freshly created v2 keystore — a new publisher, a new
machine, a recovery — silently produces **0-receipt** anchors and a 120s stall, and the error
text points at witnesses/timeouts rather than at the missing `locs` record.

## The actual work

1. **Decide whether `kli oobi resolve` should be fixed upstream in the fork** (persist the
   loc/end records on v2) or formally declared non-persisting. Right now it is neither: it
   looks like it works.
2. **Make the publisher fail loudly instead of timing out.** Before waiting for receipts,
   assert every AID in `hab.kever.wits` resolves via `hab.fetchUrls` and raise a
   configuration error naming the unreachable witness. A 120s timeout for a missing db record
   is a bad diagnostic; this is cheap and turns it into an immediate, specific failure.
3. Consider whether `Receiptor` swallowing `MissingEntryError` warrants an upstream change
   (or a wrapper in `agenting`-using code) so "contacted nobody" is distinguishable from
   "nobody receipted".
4. Document the trap in CLAUDE.md next to the existing `Receiptor` / `WitnessReceiptor` rule.

## Evidence / references

- `keri/app/agenting.py:96-100` (swallowed `MissingEntryError`), `:1070-1072` (`httpClient`
  raise), `:108` (`streamCESRRequests(..., path="/receipts")`)
- `keri/app/habbing.py:2021-2037` (`fetchUrls` reads `db.locs.getTopItemIter`)
- `tools/publisher/src/locksmith_publisher/publish.py:74-90` (`_wait_for_receipts`),
  `:118-141` (the `Receiptor` recollect pass)
- Fix applied in the tests: `_seed_witness_into_keystore` in
  `tests/integration/test_publisher_roundtrip.py` — writes the `locs` record directly and
  takes ICP/IXN from 0 wigs to 1
- memory `project_publisher_v2_reset_shipped` (the pre-existing folklore)
