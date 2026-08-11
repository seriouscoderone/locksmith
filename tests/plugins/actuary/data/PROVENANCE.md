# Vendored `ipd-parse` output — where it came from and when to refresh it

This directory is a **snapshot** of real `ipd-parse` output, vendored so the
actuary tests are hermetic. `ipd` is under active development and out of scope
for this page's work; nothing here imports it, adds it to `sys.path`, or needs
the sibling `ugard` checkout to be present.

## Source

| | |
|---|---|
| repo | `ugard` |
| shard trees | `insurance-product/parser/tests/golden/<Workbook>/` |
| workbooks | `insurance-product/parser/tests/fixtures/<Workbook>` |
| commit | `0e0cad4c7a4adef2eeafffd861f1aea3eaaefac3` (2026-08-10) |

`ExampleIssue/` and `RiskProfileTest/` are the parser's own pre-verified golden
output, copied verbatim. Each pays for itself:

- **`ExampleIssue`** — its `coverages.jsonl` is genuinely **0 bytes**. That is the
  case `_digest`'s docstring is about: keripy's `Diger.__init__` ser-fallback
  re-raises on a falsy `ser`, so the obvious `Diger(ser=raw)` implementation makes
  a *clean* parse the one that cannot be attested. The empty shard here is the
  parser's, not one this repo made up to prove a point.
- **`RiskProfileTest`** — `mappings/`, `matrices/` and `risk-value-tables/`, so the
  manifest's `rglob` walk and its posix-relative names are exercised over three
  nested directories rather than a flat listing.

## What is NOT theirs

- **`index.json`** is written by us. The parser deliberately excludes it from its
  own golden comparison because its `product` block comes from the `ipd-parse`
  caller (`--line-of-business`, `--jurisdiction`, `--product-mandate`,
  `--filing-date`, `--action`), not from the workbook. Its bytes are fixed here so
  the manifest SAID is deterministic. The *shape* mirrors
  `ipd/emit.py::write_index`.
- **`.workbook_source.json`** is not checked in at all. It holds an absolute path
  to the workbook, which differs per machine, so the tests write it into a copy
  under `tmp_path`. `ipd-parse` does not write this sidecar — see the page's own
  `_WORKBOOK_SIDECAR_NAME` comment.
- **`parse-golden.json`** is the frozen answer: the manifest and its SAID for each
  tree above.

## What `parse-golden.json` does and does not prove

It **freezes** the manifest this page computes over a real parse tree, so any
change to `_build_manifest` — shard ordering, `ensure_ascii`, the sidecar
exclusion, the digest code, the walk — is caught locally. The SAID is
independently checked against `keri.core.sealing.verifySealedBody`, the consumer's
own verifier, so it is not merely this page agreeing with itself.

It does **not** prove the page still agrees with `ipd.manifest`. That differential
used to run by putting the parser's `src` on `sys.path` and importing it; it is
removed while `ipd` moves. Two consequences worth knowing:

1. If the parser changes its manifest algorithm, this suite stays green and the
   page is wrong. The page's docstrings no longer claim byte-identity as a tested
   fact.
2. There is a **known, measured divergence already**: `_build_manifest` excludes
   `.workbook_source.json` from the shard walk and `ipd/manifest.py` does not, so
   the same directory yields two different SAIDs whenever the sidecar is present —
   which the sidecar convention guarantees. Recorded in
   `ugard/backlog/2026-08-09-actuary-page-remaining.md`; it is an owner decision,
   not a defect in this snapshot.

## Refreshing, when `ipd` is solid

`test_manifest.py::test_the_vendored_snapshot_still_matches_the_parsers_golden`
compares these trees byte-for-byte against the parser's golden **when the `ugard`
checkout is present** (`UGARD_ROOT`, default `~/code/ugard`), and skips otherwise.
It is a file comparison, not an import, so parser internals churning does not
break it — only its *output* moving does, which is exactly the signal for when to
come back here.

To refresh: re-copy the trees and workbooks, re-run the generator in
`test_manifest.py`'s module docstring, update the commit above, and re-instate the
live differential against `ipd.manifest`.
