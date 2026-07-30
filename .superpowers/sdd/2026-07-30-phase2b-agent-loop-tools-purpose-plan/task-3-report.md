# Task 3 report — decide pass

**Status:** Complete.

**Files created:**
- `packages/keri-assistant/src/keri_assistant/decide.py`
- `packages/keri-assistant/tests/test_decide.py`

**TDD flow followed:**
1. Wrote `tests/test_decide.py` verbatim from the brief.
2. Ran it: failed with `ModuleNotFoundError: No module named 'keri_assistant.decide'`, as expected.
3. Wrote `decide.py` verbatim from the brief (constants `CALL_TOOL`/`PROPOSE`/`ANSWER`, frozen
   `Decision` dataclass, `build_decide_schema`, `parse_decision`; reuses `GrammarViolation` from
   `keri_assistant.proposal`, `MAX_TEXT` from `keri_assistant.actionschema`, and `ToolRegistry` from
   `keri_assistant.tools`).
4. Verified `tests/test_decide.py`: 14/14 passed.
5. Ran the full suite from `packages/keri-assistant/`: **173 passed**, no failures/errors/skips
   (baseline was 159; 159 + 14 new decide tests = 173, exact match).

**Two specifics from the brief, confirmed in the code:**
- `GrammarViolation` is imported from `.proposal`, not redefined.
- When `registry.ids()` is empty, the `call_tool` alternative is omitted from `oneOf` entirely
  (never an empty `enum`) — mirrors `build_proposal_schema`'s existing rule.

**Commit:** `8dc73a01` — "feat(keri-assistant): decide pass — a choice-only schema, no argument
shaping" (message exactly as specified in the brief, including the `Co-Authored-By` trailer).
Only the two target files are in this commit; an unrelated pre-existing modification to
`docs/superpowers/plans/2026-07-30-phase2b-agent-loop-tools-purpose-plan.md` was left untouched/unstaged.

**Concerns:** None. No existing test was touched or broken. No `pip install`/`pip uninstall` was
run; used the shared worktree venv's Python only for running pytest.
