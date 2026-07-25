# Replace the per-version /tmp promote script with a committed `scripts/promote-release.sh`

**Filed:** 2026-07-25 (after the v0.3.2 cut)
**Domain:** release tooling (off-CI publish path; `tools/publisher/` + `scripts/`)
**Severity:** process. Nothing is broken, but the current shape has already caused one
mis-publish and a per-version script exists *so that the version can be wrong*.

## Symptom
Every cut hand-copies a new `/tmp/promote-<version>/promote.sh` (0.2.21 → 0.3.0 → 0.3.1 →
0.3.2), each produced by `sed`-ing the previous version's copy. During the 0.3.1 cut the
**wrong script was run** — `/tmp/promote-0.3.0/promote.sh` instead of `…-0.3.1/…` — which
re-anchored 0.3.0 and added two junk entries to the publisher KEL (sn=9, sn=10). Recoverable
(the appcast still advertised the right version, and the anchors are idempotent in content),
but it is permanent KEL growth for zero value.

## Root cause
The version is *typed into a copy of the script* instead of being passed in and derived. The
script is a thin wrapper over `locksmith-publisher anchor` + `publish` and only does four
things — read the version, hash the two artifacts, loop the two brands, pass the passphrase
through. **None of those need to be per-version.** Being in `/tmp` also means it is
regenerated from memory each time: never reviewed, never tested, never versioned alongside
the publisher it drives.

## Fix — one committed `scripts/promote-release.sh <version>`
- Takes the version as an **argument** (single source of truth; no `sed`, no stale copy to
  grab by mistake).
- Reads artifact names from the **brand manifests** (`[identity] artifact_prefix`) instead of
  hardcoding `Locksmith-` / `Usurance-`, so a new brand needs no script edit.
- **Downloads the artifacts from S3 itself** rather than trusting whatever is staged in
  `/tmp` — this closes the "did I verify the bytes I'm actually anchoring?" gap.
- Runs the guard (`scripts/verify-release-artifact.py`) **before and after** publishing and
  refuses to proceed on failure.
- **Asserts** `pyproject` version == the tag == the argument, so it cannot anchor a version
  that was never cut.
- Preflights the environment: `locksmith-publisher` present in the venv (see CLAUDE.md ›
  restoring it after a venv rebuild) and the artifact's **baked** anchor matches the live
  feed's `publisher_aid`.
- Still takes the bran from `$LOCKSMITH_PUBLISHER_BRAN` or a **silent prompt** — that part
  stays interactive by design.

## Explicitly NOT automated (deliberate, keep it that way)
- **Publishing stays off-CI.** The publisher keystore and passphrase never touch a runner.
- **Promote-to-latest stays a conscious decision** after verification passes.

The goal is not "one button ships it." The goal is **the version and the artifact digests are
derived, not retyped.**

## Honest scope caveat
Some of the v0.3.x ceremony was not the script's fault: the venv losing
`locksmith-publisher`, the stale `LOCKSMITH_PUBLISHER_ANCHOR` secret, and the keri
DB-version trap. A wrapper would have *surfaced* those faster but would not have prevented
them — the **preflight checks** (CLI present, baked anchor matches the live feed) are what
actually catch that class of failure. Prioritize those checks over shell ergonomics.

## Verify
1. `scripts/promote-release.sh 0.3.3` performs a full both-brand cut with no `/tmp` script.
2. Negative: `scripts/promote-release.sh 9.9.9` fails fast on the version assertion without
   touching the KEL.
3. Negative: with a deliberately mismatched baked anchor, the preflight refuses to publish.
4. A unit/integration test covers the version-assertion and artifact-name derivation logic
   (the S3/KEL parts stay manual).

## Related
- `scripts/verify-release-artifact.py` — the guard this should invoke (added 2026-07-25,
  commit `c9a5472`; hardened in `b9b81838`).
- CLAUDE.md › *Release publisher + update verification* — the anchor-secret and
  never-relabel-`keri.__version__` traps, plus restoring the publisher CLI.
- The last hand-rolled scripts, for reference while writing this:
  `/tmp/promote-0.3.1/promote.sh`, `/tmp/promote-0.3.2/promote.sh`.
