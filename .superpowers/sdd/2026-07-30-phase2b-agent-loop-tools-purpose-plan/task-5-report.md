# Task 5 report — AgentLoop

**Status:** Complete. Commit `03077066`.

## Files
- Created `packages/keri-assistant/src/keri_assistant/loop.py` — `LoopBudget`, `LoopOutcome`,
  `AgentLoop` (`.run(utterance) -> LoopOutcome`), exactly as specified in the brief's code block.
- Created `packages/keri-assistant/tests/fixtures/loop_fixtures.py` — verbatim from the brief.
- Appended `ScriptedBinding` to `packages/keri-assistant/tests/fakes.py` — verbatim from the brief;
  diff is purely additive (confirmed via `git diff`), the five existing fakes are byte-identical.
- Created `packages/keri-assistant/tests/test_loop.py` — from the brief, with one fix (below).

## Deviation from the brief, and why
`test_the_standing_instruction_carries_the_role_purpose` in the brief asserted `"Clerk"` /
`"file records"` in the standing instruction, but the `ROLE` fixture it exercises (via `_loop`,
from `loop_fixtures.py`) is `display_name="Reporter"`, `responsibility="submit reports"`. Those
strings can never appear together — `RoleContext.standing_instruction()` emits the role's own
`display_name`/`responsibility` verbatim. Grepping the repo found the source of the mismatch:
`tests/test_role.py` has a same-shaped test using a literal `Clerk`/`file records` `RoleContext`
it constructs itself, and the brief's test appears to have been adapted from that test without
updating the strings for the `Reporter` fixture actually in scope. I changed the two assertions
to `"Reporter"` and `"submit reports"` — matching the fixture the test itself uses (also
matching `tests/test_tools.py`'s `PARSING_ROLE`, which uses the same role). No other test or
fixture content was changed from the brief.

## TDD sequence followed
1. Wrote fixtures + `ScriptedBinding` + `test_loop.py`.
2. Ran `pytest tests/test_loop.py -q` → confirmed failure: `ModuleNotFoundError: No module named
   'keri_assistant.loop'`.
3. Wrote `loop.py` verbatim from the brief.
4. Ran `pytest tests/test_loop.py -q` → 14 passed.
5. Ran full suite `pytest -q` → 197 passed (baseline 183 + 14 new = 197 exactly; no failures, no
   new skips).

## Invariant checks
- `loop.py` imports: `dataclasses`, and from `.actionschema`, `.binding`, `.decide`,
  `.enforcement`, `.grounding`, `.loopstate`, `.proposal`, `.role`, `.surface`, `.tools`. Nothing
  from `.seams`; no `Confirmer`/`Dispatcher` anywhere. The AST-based
  `test_the_loop_NEVER_confirms_or_dispatches_anything` passes.
- `require_hard` is called only on the `PROPOSE` branch, right before the shape-pass `_ask` for
  the proposal schema — reads/answers never touch it (`test_a_soft_binding_is_FINE_for_reads_and_answers`
  passes on a SOFT binding; `test_a_soft_binding_is_refused_for_the_shape_pass` proves SOFT raises
  for a proposal).
- Tool output only ever reaches `ProposalRequest.data_context` via `state.observations`
  (`observation_for`), never concatenated into `instruction`
  (`test_tool_output_reaches_the_model_as_DATA_never_as_instruction` passes).
- Budget exhaustion returns `status="budget_exhausted"` with a `reason` naming which budget
  (`"iteration"` / `"tool"`), distinct from `"answer"`/`"proposal"`.

## Commit
`03077066` — includes all four files (the brief's own `git add` line only named two, but the
other two are load-bearing for `test_loop.py` to even import, so all four are in one commit).
Message matches the brief's, with the co-author line the team lead specified
(`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`).

## Environment
No `pip install`/`pip uninstall` run. No new dependencies. Pure stdlib in shipped code. Ran tests
via `<worktree>/.venv/bin/python -m pytest` from `packages/keri-assistant/`, exactly as instructed.
