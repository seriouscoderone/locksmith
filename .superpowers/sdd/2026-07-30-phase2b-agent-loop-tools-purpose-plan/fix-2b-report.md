# Fix 2B report — whole-branch security review findings

Working directory: `/Users/seriouscoderone/code/locksmith/.claude/worktrees/assistant-2b/packages/keri-assistant`

## Status: complete

All items applied. Baseline was 232 passing; suite is now **242 passing** (10 new tests, 0
existing tests deleted; 2 existing tests edited per explicit permission — m1, A3).

## C1 (Critical)

`build_tool_registry` (`src/keri_assistant/tools.py`) now computes `exchange_ids` from the
surface and raises `ValueError` if any tool spec id collides with an exchange verb id, and
separately raises if any spec id starts with `__` (reserved escape-hatch namespace). Checked
before the pre-existing duplicate-id check.

Reproduced the reviewer's exact scenario after the fix:
```
verbs: [('grant', 'exchange'), ('grant', 'query')]
raised: tool id 'grant' names an exchange verb; an exchange verb cannot be a tool
```

Tests added (`tests/test_tools.py`): colliding-id template raises; `__clarify__`-named projection
raises; normal disjoint case still builds; never-verb projection yields an empty registry (A1
companion). `tests/test_surface.py` also gained a projections[]-specific never-verb pin (A1).

## I1 (Important)

`AgentLoop.run` (`src/keri_assistant/loop.py`) now checks `spec.input_schema.get("properties")`
before calling `_ask`; when empty/absent it uses `args = {}` directly, skipping the backend call.
Verified via a read tool (`board`, from `projections[]`) driven through the full loop: exactly 2
backend calls (decide, decide again), not 3, and the executor received `{}`.

## I5

`AgentLoop.__init__` now does `self._registry = registry.filtered_for(role)`. Test constructs the
loop with an *unfiltered* registry and a narrow role, runs it, and inspects the actual decide-pass
request sent to the `ScriptedBinding` (`b.requests[0].schema`) — confirms only the role's tools are
offered, without touching loop internals.

## I4

`audit_schema.py`'s SAID-claim detector is now split: `_SAID_ACRONYM_CLAIM = re.compile(r"\bSAID\b")`
(case-sensitive) plus `_SAID_PHRASE_CLAIM` (case-insensitive, phrases only). Verified unchanged
results on the vendored corpus: carrier 2, actuary 0 (matches reviewer's numbers). New tests: "the
said applicant filed the request" is not reported; "SAID of the prior record" is.

## Cheap correctness items (m1, m2, m3, m6)

- **m3**: `read_tools_from_surface` now uses `copy.deepcopy(_NO_ARGS)` instead of `dict(_NO_ARGS)`.
- **m1**: `test_purpose_cannot_widen_the_tool_set_only_narrow_it` rewritten with a role whose tags
  are disjoint from the tagged tool (was a superset before — tautological). Now strict-subset
  assertion (`filtered < unfiltered`) that fails against a no-op filter stub.
- **m2**: `audit_schema.py` docstring corrected — no longer claims the `ref` shape is asserted by
  any test; states instead that those fields are plain locators per their own descriptions (verified
  against `tests/fixtures/real/actuary_attests_product_rating.json`).
- **m6**: covered by C1's `__`-prefix rejection.

## Pinned guarantees (A1, A2, A3)

- **A1**: new test proves `projections: [{"id": "rotate"}, {"id": "passcode"}]` yields no verbs
  (`test_surface.py`) and an empty registry (`test_tools.py`).
- **A2**: new test in `test_loop_invariants.py` scripts a tool call whose output is hostile, then
  ends on `PROPOSE`. Asserts the *last* request is the shape pass (its schema's `verb_id` consts
  include `submit_report`), the hostile text is in `data_context`, and absent from `instruction`.
- **A3**: `test_a_soft_binding_is_FINE_for_reads_and_answers` now scripts a `CALL_TOOL` step before
  `ANSWER` and asserts the executor actually ran — the "reads" half of its name is now backed.

## Deliberately out of scope

I2, I3, m4, m5, m7, m8 — not touched, as instructed.

## Worktree/venv note

No `pip install`/`pip uninstall` run against the shared venv. Tests run via the worktree's own
`.venv/bin/python` with `--import-mode=importlib`; `__pycache__` cleared before each verification
run per the stale-`.pyc` warning.
