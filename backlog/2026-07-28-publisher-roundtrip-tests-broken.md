# The publisher round-trip tests are broken — the release gate has been dark

**Status:** RESOLVED 2026-07-28 — both tests green (fixed by the PUBLISHER agent, merged as
`d0d953c3`). One root cause, not two: `kli oobi resolve` exits 0 but persists nothing on the v2
base, and `Receiptor` swallows the resulting `MissingEntryError` — the receipt "timeout" was a
config error. Four further stale-signature breaks fixed behind it. The underlying trap and the
CI gap are filed separately: `2026-07-28-kli-oobi-resolve-persists-nothing-on-v2.md`,
`2026-07-28-ci-runs-no-tests-at-all.md`.

**Raised:** 2026-07-28 · **Priority:** ~~high~~

## What we saw

Both tests in `tests/integration/test_publisher_roundtrip.py` fail on `development`
(`6e43fc6e`), and fail identically from a worktree — so this is not worktree fallout. Found
while establishing a full-suite baseline for
`2026-07-28-peer-endpoint-not-a-real-eid.md`; unrelated to that change.

**1. `test_publisher_kel_cesr_verifies_against_existing_verifier` — stale call signature.**

```
TypeError: anchor_release() missing 1 required keyword-only argument: 'brand'
tests/integration/test_publisher_roundtrip.py:234
```

`publish.anchor_release` grew a required keyword-only `brand` parameter with the
multi-brand work (`tools/publisher/src/…/publish.py:92`) and the test was never updated.
It has therefore not exercised the verifier since that change landed. This one is a
one-line fix, but note what it means: the test that proves a published `kel.cesr` verifies
against `update/verify.py` has been failing silently through the whole multi-brand release
series.

**2. `test_cli_roundtrip_verifies` — no witness receipts.**

```
TimeoutError('only 0/1 witness receipts for sn=1 after 120.0s')
tests/integration/test_publisher_roundtrip.py:370
```

`kli incept` succeeds, then `anchor` times out collecting receipts. Needs triage to tell
apart:
- a test-local witness that is not actually being started (or is started on a port the
  publisher's config does not point at), versus
- reaching for a **live** witness from the federation, which would make this test
  network-dependent and not something the suite should rely on.

Worth checking against `2026-07-28`-era memory `project_witness_receipt_race_bug` and the
`Receiptor`-vs-`WitnessReceiptor` rule in CLAUDE.md — a 120s timeout with 0 receipts is the
signature of the direct-mode receipt model being used over HTTP.

## Why it matters beyond the two tests

CLAUDE.md notes the in-app updater verify gate is deliberately dark until a real publisher
anchor is injected. That is fine as a product posture, but it means these two tests are the
main automated evidence that the anchor/verify path works at all. With both red, a break in
`publish.anchor_release` or the KEL export would surface for the first time during a
release cut.

## The actual work

1. Pass `brand=` in the test (pick whichever brand the fixture's config represents; the
   assertion should then confirm the seal's `brand` field matches, since brand-mismatched
   seals are exactly what `2026-07-28`-era multi-brand verification had to fix).
2. Triage the receipt timeout; if the test needs a live witness, either stand up a local one
   in the fixture or mark it clearly as network-dependent and keep it out of the default run.
3. Consider making a red publisher test fail CI loudly — the value here is catching this
   *before* a cut, which requires someone to notice.

## Evidence / references

- `tests/integration/test_publisher_roundtrip.py:234`, `:370`
- `tools/publisher/src/…/publish.py:92` (`anchor_release(*, name, alias, bran, base,
  version, brand, artifacts, out_dir)`)
- CLAUDE.md "Release publisher + update verification"; memory
  `project_v020_release_v2base_state`, `project_witness_receipt_race_bug`
- Baseline confirmed on `development` in the main checkout, not only in a worktree
