# Task 6 report: Loop invariants + mutation verification

## Status: complete

- **Commit:** `da484d09` — `test(keri-assistant): agent-loop invariants, each proven to fail under mutation`
- **File created:** `packages/keri-assistant/tests/test_loop_invariants.py` (the only file created; no production code touched)
- **Suite:** 207 passed (197 baseline + 10 new tests), 0 failures/errors/skips, after every mutation was reverted. `git status` clean apart from the new test file.

## Deviation from the brief's exact code

The brief's Step 1 code imports `PARSER` from `tests.fixtures.loop_fixtures`:
```python
from tests.fixtures.loop_fixtures import COUNTERPARTY as CP, G, PARSER, REG, ROLE, SURF
```
That name does not exist there (the fixture defines `PARSER_TOOL`, not `PARSER`), so collection failed with `ImportError` on the first run. `PARSER` is never referenced in any test body, so I dropped it from the import list rather than edit the shared fixtures file (out of scope — not the file I was assigned to create, and touching it is production/fixture code, not a new test). Also collapsed the brief's duplicated `RecordingToolExecutor` import line into the single `from tests.fakes import RecordingToolExecutor, ScriptedBinding` already used elsewhere in the suite. No other changes from the brief's Step 1 code.

## Mutation table — all 11 rows produced a failure

For each row: applied the mutation, ran the named test(s), captured the assertion, then reverted before the next row. `git diff -- packages/keri-assistant/src` is empty, confirming every mutation is fully reverted.

| # | Mutation | Tests run | Result |
|---|---|---|---|
| M1 | `read_tools_from_surface` includes `kind == "exchange"` verbs | `test_authority_bearing_work_is_never_an_autonomous_tool` | **FAILED** — `assert {'board', 'grant_ok'} == {'board'}` (the open-authz `grant_ok` exchange verb leaked in as a tool) |
| M2 | dropped `if tool_ids:` guard in `build_decide_schema` | `test_call_tool_alternative_is_OMITTED_when_no_tools_exist` (test_decide.py) + `test_no_empty_enum_is_ever_emitted_by_the_decide_schema` | **BOTH FAILED** — first: `['call_tool', ...] == ['propose', 'answer']` mismatch (alternative not omitted); second: `AssertionError: an empty enum is unsatisfiable — omit the alternative instead` on `assert []` |
| M3 | deleted `require_hard(self._binding.enforcement())` in `loop.py` | `test_a_soft_binding_is_refused_for_the_shape_pass` (test_loop.py) + `test_soft_enforcement_is_refused_for_proposals_but_not_for_answers` | **BOTH FAILED** — `Failed: DID NOT RAISE SoftEnforcementError` (both) |
| M4 | `_ask` puts observations into `instruction`, empties `data_context` | `test_tool_output_reaches_the_model_as_DATA_never_as_instruction` (test_loop.py) + `test_injected_instructions_in_tool_output_stay_in_data_context` | **BOTH FAILED** — `assert False` on `any("42 rows"/"IGNORE YOUR INSTRUCTIONS" in c for c in last.data_context)` (data_context now empty) |
| M5 | removed both budget checks in `loop.py` `run` | `test_iteration_budget_exhaustion_is_explicit_not_silent` + `test_tool_call_budget_exhaustion_is_explicit` (test_loop.py) | **BOTH FAILED** — `assert 'answer' == 'budget_exhausted'` (both). No infinite loop: `ScriptedBinding` falls back to a default `answer` decision once its script is exhausted, so the run terminated normally instead of hanging. |
| M6 | budget-exhaustion branches return `status="answer"` | `test_budget_exhaustion_is_distinguishable_from_completion` | **FAILED** — `assert 'answer' == 'budget_exhausted'` |
| M7 | `filtered_for` unions `self.specs` with new role-tag-derived `ToolSpec`s (widening) | `test_purpose_cannot_widen_the_tool_set_only_narrow_it` | **FAILED** — `assert {'board', 'role-...', 'tagged-tool'} <= {'board', 'tagged-tool'}`; extras `role-anything`, `role-parsing`, `role-else` present in filtered but absent from unfiltered. (Note: I deliberately made the mutation add genuinely new ids rather than just disable filtering — disabling filtering alone would make `filtered == unfiltered`, which still satisfies `<=` and would NOT have exercised this assertion. The brief's phrasing "`self.specs` + role-tagged" pointed at this construction.) |
| M8 | dropped the duplicate-id `raise` in `build_tool_registry` | `test_duplicate_tool_ids_raise` + `test_a_compute_tool_may_not_shadow_a_read_tool` (test_tools.py) | **BOTH FAILED** — `Failed: DID NOT RAISE ValueError` (both) |
| M9 | `LoopState.advanced` mutates via `object.__setattr__` and returns `self` | `test_advanced_returns_a_new_state_and_never_mutates` (test_loopstate.py) | **FAILED** — `assert (1, 1, ('saw 42 rows',)) == (0, 0, ())` (the original state `a` was mutated in place) |
| M10 | `parse_decision` no longer checks `registry.by_id(tool_id)` for `CALL_TOOL` | `test_call_tool_naming_an_unregistered_tool_is_a_grammar_violation` (test_decide.py) | **FAILED** — `Failed: DID NOT RAISE GrammarViolation` |
| M11 | added `from .seams import Dispatcher as _D` (unused) to `loop.py` | `test_the_loop_module_cannot_confirm_or_dispatch` + `test_the_loop_NEVER_confirms_or_dispatches_anything` (test_loop.py) | **BOTH FAILED** — `assert 'Dispatcher' not in {..., 'Dispatcher', ...}`. Confirms the AST walk records the import's **original name** (`ast.alias.name`) regardless of the `asname` used at the call site, so the alias `_D` does not hide the import from the check. This is the exact case the brief flagged: a substring/`grep Dispatcher` check would have hit the docstring's mention of "Dispatcher" (false positive on prose) while a check that only looked at `asname` would have missed this aliased import (false negative on the real violation). The AST-on-`name`-not-`asname` approach here gets both right. |

Every row failed as required — no surviving mutants.

## Concerns / notes

- The `PARSER` import bug in the brief (see deviation above) means the brief's Step 1 code block, taken completely literally, does not run. Flagging in case the same bug exists in other task briefs that reused this snippet.
- No other issues. The shared venv was not touched (no `pip install`/`uninstall` run); all commands used the assigned worktree interpreter and `cd`'d with absolute paths.
