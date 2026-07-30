# Task 2 Report: ToolRegistry Implementation

## Summary

Implemented `ToolRegistry` — the assistant's autonomous action space, unifying declared READ
tools (from the micro-app template's `projections[]`) with host-registered WORKBENCH compute
tools, filtered by `RoleContext.tool_tags`. Created/modified three files:
- `packages/keri-assistant/src/keri_assistant/tools.py` (new, 90 lines)
- `packages/keri-assistant/tests/fakes.py` (appended `RecordingToolExecutor`; existing four fakes
  byte-identical — verified via `git show` diff, pure additions only)
- `packages/keri-assistant/tests/test_tools.py` (new, 14 tests)

## TDD Process

### Step 1-2: Test Failure (Confirmed)

Wrote `test_tools.py` with the 14 test cases exactly as specified in the brief.

Ran: `cd packages/keri-assistant && <worktree>/.venv/bin/python -m pytest tests/test_tools.py -q`
Result: `ModuleNotFoundError: No module named 'keri_assistant.tools'` — confirmed failing for the
right reason.

### Step 3-4: Implementation

Wrote `tools.py` and appended `RecordingToolExecutor` to `fakes.py`, both verbatim from the brief:
- `ToolSpec` (frozen, `kind ∈ {"read","compute"}`, `tags: frozenset[str] = frozenset()`)
- `ToolResult` (frozen)
- `ToolExecutor` — a `Protocol`, deliberately separate from `seams.Dispatcher`
- `ToolRegistry` (frozen) with `.by_id`, `.ids()` (sorted), `.filtered_for(role)`
- `read_tools_from_surface(surface)` — maps `kind="query"` verbs to closed, empty-schema read tools
- `build_tool_registry(surface, compute=(), *, role=None)` — merges reads + compute, raises
  `ValueError("duplicate tool id: ...")` on any id collision (including a compute tool shadowing a
  read tool), then applies `role.filtered_for` if a role is given

### Step 5: Target Test Pass

Ran: `cd packages/keri-assistant && <worktree>/.venv/bin/python -m pytest tests/test_tools.py -q`
Result: `14 passed in 0.01s`

### Step 6: Full Suite Verification

Ran: `cd packages/keri-assistant && <worktree>/.venv/bin/python -m pytest -q`
Result: `159 passed in 0.07s`
- 145 baseline tests: all green, no breakage
- 14 new tests: all green
- Total: 159 passing

(First full-suite invocation was run from the worktree root by mistake and hit the repo's PySide6
`conftest.py`, unrelated to this package — re-ran from `packages/keri-assistant/` per the brief and
got the clean 159.)

### Step 7: Commit

Commit message used verbatim from the brief (with the required trailer):

```
git add packages/keri-assistant/src/keri_assistant/tools.py packages/keri-assistant/tests/fakes.py packages/keri-assistant/tests/test_tools.py
git commit -m "feat(keri-assistant): ToolRegistry — declared reads + workbench compute tools

Reads come from the template's projections[]; compute tools are workbench tools
registered by the host (ugard 2026-07-29: the framework's peer, invoked by the
person and gated by nothing, so declaring them in a template would be a category
error). Exchange verbs are never tools. Execution uses a ToolExecutor seam that
is deliberately not Dispatcher.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

**Commit SHA:** `feb3d5fa`

## Test Coverage

All 14 test cases passing:
1. `test_read_tools_come_from_projections_only`
2. `test_exchange_verbs_are_NOT_tools`
3. `test_read_tool_input_schema_is_closed_and_empty`
4. `test_registry_unifies_reads_and_computes`
5. `test_ids_are_sorted_for_deterministic_grammars`
6. `test_unknown_tool_id_is_none`
7. `test_purpose_filters_compute_tools_by_tag`
8. `test_purpose_never_filters_out_read_tools`
9. `test_untagged_compute_tool_survives_filtering`
10. `test_no_role_means_no_filtering`
11. `test_duplicate_tool_ids_raise`
12. `test_a_compute_tool_may_not_shadow_a_read_tool`
13. `test_recording_executor_satisfies_the_protocol_and_records`
14. `test_recording_executor_defaults_to_a_failure_for_unknown_tools`

## Constraints Honored

- No `pip install`/`pip uninstall` run (shared venv untouched)
- Pure stdlib only (`dataclasses`, `typing`); no `locksmith`/`keri` imports
- No domain vocabulary anywhere in code, comments, or docstrings
- `kind == "exchange"` verbs never appear as tools — verified by
  `test_exchange_verbs_are_NOT_tools`
- `tools.py` contains **no import of, and no code reference to,** `Dispatcher` — checked via
  `grep -n "Dispatcher" src/keri_assistant/tools.py` and `grep -n "^from\|^import"`. The only hit is
  the module docstring's prose contrast ("deliberately NOT the `Dispatcher` seam"), which is
  verbatim from the brief's own template text, not a code dependency.
- Existing four fakes (`FakeConfirmer`, `RecordingDispatcher`, `RecordingAudit`, `FakeBinding`) are
  byte-identical — confirmed via `git show feb3d5fa -- packages/keri-assistant/tests/fakes.py`,
  diff is pure addition (one import line + `RecordingToolExecutor` class), no deletions.
- No existing test broken; nothing edited to force a pass.

## Nothing Surprising

Implementation matched the brief's provided code exactly; all tests passed on first run with no
adjustments needed. The only wrinkle was an initial full-suite run from the wrong directory (worktree
root instead of `packages/keri-assistant/`), which hit an unrelated PySide6 import in the repo-level
conftest — resolved by re-running from the correct directory as the brief specifies.
