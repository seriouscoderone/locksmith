# Peer integration tests can't run from worktrees — and would test the wrong tree if they could

**Status:** DONE · **Raised:** 2026-07-28 · **Priority:** high (step 0 of the EID endpoint work — it needs these tests runnable)

## What we saw

Running the suite from a task worktree: `tests/integration/peer/*` → 5 errors,
`FileNotFoundError: …/<worktree>/.venv/bin/python`. The fixture hardcodes a repo-root venv:

```python
# tests/integration/peer/conftest.py:29
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
```

`REPO_ROOT` resolves to the *worktree* root when run from a worktree, and worktrees have no venv
(there is exactly one, at the main checkout — see CLAUDE.md "Worktree venv isolation"). Under
that policy these five tests are permanently unrunnable outside the main checkout — and they are
the only end-to-end peer-transport coverage, exactly where peer regressions would show.

## The subtlety — `sys.executable` alone is NOT the fix

The obvious patch (`sys.executable` — the interpreter running pytest *is* the venv python in both
contexts) fixes the `FileNotFoundError` but silently tests the **wrong tree**: the editable
`.pth` in the shared venv holds an absolute path to the MAIN checkout's `src/`, so a spawned
`python -m locksmith.main` bare-imports the MAIN tree's code, not the worktree's changes
(CLAUDE.md "Worktree caveat"). Green tests, untested diff.

## The actual work

1. `VENV_PYTHON` → `sys.executable`.
2. The fixture's spawn env must prepend `PYTHONPATH=<repo_root>/src` (the *worktree's* src) so the
   subprocess imports the tree under test, mirroring what pytest's `pythonpath` already does for
   in-process tests.
3. Verify from a worktree that (a) all five tests run, and (b) a worktree-only sentinel change is
   actually visible to the spawned wallet — proving the right tree is under test, not just that
   the process starts.

## Evidence / references

- `tests/integration/peer/conftest.py:9,29`
- CLAUDE.md: "Worktree venv isolation", "Worktree caveat"
- Surfaced by the loopback-fix task (merged `38d1aea3`), which could not run these tests from its
  worktree; consumed as step 0 of `2026-07-28-peer-endpoint-not-a-real-eid.md`.
