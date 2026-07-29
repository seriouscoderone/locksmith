# CI runs no tests at all — a red suite cannot fail anything

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** high (this is why two release-gate tests stayed red through a six-release series without anyone noticing)

## What we saw

Asked whether a red publisher round-trip test would fail a release build loudly. The answer is
broader than the question:

```
$ ls .github/workflows/
release.ci.yml

$ grep -rn 'pytest' .github/
  NONE
```

There is exactly **one** workflow, `release.ci.yml`, triggered on GitHub Release creation. It
checks out, builds, signs, notarizes and uploads per brand. It runs **no tests** — not the unit
suite, not integration. There is also no push/PR workflow, so nothing runs the suite on a
branch or a merge either.

The only automated gates in CI are three preflight scripts:
`scripts/check-version.py`, `scripts/check-brand-complete.py`,
`scripts/check-anchor-present.py` (`release.ci.yml:71, 173-174, 268, 382-383`).

## Why it matters

This is the mechanism behind `2026-07-28-publisher-roundtrip-tests-broken.md`: the two tests
that constitute the *only* automated coverage of the release anchor/verify path were red on
`development`, and nothing anywhere reported it. They were found by a human running the suite
by hand. The same blind spot applies to every other test in the repo — ~1300 unit tests that
gate nothing.

Note the asymmetry: the release pipeline is otherwise well guarded (signed-tag verification,
version/pyproject match, brand completeness, anchor presence). Tests are the one class of
check absent from it.

## The actual work

Not cheap — deliberately not done as a drive-by. Getting a test job green in CI needs:

1. **A push/PR workflow** running the unit suite (`pytest tests -q --import-mode=importlib
   --ignore=tests/integration`). `--import-mode=importlib` is mandatory (top-level
   `packaging/` shadows the `packaging` library).
2. **Install cost**: the pinned `keri` fork is a git dependency, so a cold install is slow.
   Needs dependency caching to be tolerable.
3. **Headless Qt**: parts of the suite use `pytest-qt`; CI needs an offscreen platform
   (`QT_QPA_PLATFORM=offscreen`) and the runner must tolerate it.
4. **Pre-existing red tests must be resolved or explicitly excluded first**, or the job is red
   on day one and gets ignored — the exact failure mode this item is about. Known-red today:
   - the six `tests/plugins` failures from a worktree
     (`2026-07-28-plugin-entry-point-tests-fail-from-a-worktree.md`)
   - `tests/integration/peer/*` (2 tests) and, until this branch, the 2 publisher round-trip
     tests
5. **Decide integration-test policy.** The publisher round-trip tests need a `kli` binary and
   spawn subprocesses + an in-process witness; they take ~10-20s each and are marked
   `integration`. Either run them in a separate (allowed-to-be-slow) job or keep them opt-in
   and accept that they are gated by humans. If they stay opt-in, say so explicitly somewhere,
   because "we have a test for that" is currently doing no work.
6. **Consider gating the release workflow on the test job** so a red suite blocks a cut, which
   is the actual value being asked for here.

## Evidence / references

- `.github/workflows/release.ci.yml` — sole workflow; `on: release: [created]`
- `grep -rn 'pytest' .github/` → no matches (verified 2026-07-28 on `development` `3693a927`)
- `2026-07-28-publisher-roundtrip-tests-broken.md` — the failure this gap allowed to persist
- `2026-07-28-plugin-entry-point-tests-fail-from-a-worktree.md`,
  `2026-07-28-peer-endpoint-not-a-real-eid.md` — other currently-red areas that a naive CI
  addition would trip over
