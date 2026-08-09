# Task 2 report: pure validation of the mandate payload

**Note:** this file previously held a report for an unrelated task (a `keripy`
`WebRegBaser` land) that happened to reuse this same filename/task number in a
different project. That content has been fully replaced below with the report
for *this* task (CUO product-mandate form, `locksmith` repo, Task 2 of 8).

## What was implemented

- `src/locksmith/plugins/cuo/validation.py` — new module, verbatim from the brief's
  Step 3, unmodified. Exports:
  - `FieldError` (`@dataclass(frozen=True)`, `field: str`, `message: str`)
  - `validate_payload(payload, schema, existing=()) -> list[FieldError]`
  - `windows_overlap(a_opens, a_closes, b_opens, b_closes) -> bool`
  - Private helpers `_is_iso_date`, `_empty`, `_scalar_errors`, `_array_errors`.
  - Imports no Qt. Confirmed with `grep -ni "qt\|pyside" validation.py` — the only
    hit is the word "Qt-free" in the module docstring, no actual import.
- `tests/plugins/cuo/test_validation.py` — new test file, verbatim from the brief's
  Step 1, unmodified. 17 test functions (3 of them parametrized into the 17 total
  collected items).

Both files consume Task 1's `schema_source.load_mandate_schema` /
`MandateSchema` / `FieldConstraints` and Task 3's `mandate_copy` message
constants and helpers, exactly as the brief specified. Neither dependency
needed any change — both were already landed and matched the interfaces the
brief assumed (`FieldConstraints.fmt`, not `.format`; `mandate_copy.FIELD_ORDER`
as the field-order authority, not `schema.order`).

Followed TDD order per the brief: wrote the test file first, ran it and watched
it fail with `ModuleNotFoundError: No module named
'locksmith.plugins.cuo.validation'` (expected, since Task 3's `mandate_copy` was
already present, the only missing piece was this module), then wrote the
implementation, ran it again and watched it pass, then committed.

## Exact test commands and full output

Baseline, before adding anything (confirms the pre-existing 25):

```
$ cd /Users/seriouscoderone/code/locksmith
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
.........................                                                [100%]
25 passed in 0.12s
```

Step 2 (watch it fail), after creating the test file only:

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_validation.py -q --import-mode=importlib
==================================== ERRORS ====================================
____________ ERROR collecting tests/plugins/cuo/test_validation.py _____________
ImportError while importing test module '/Users/seriouscoderone/code/locksmith/tests/plugins/cuo/test_validation.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
tests/plugins/cuo/test_validation.py:13: in <module>
    from locksmith.plugins.cuo.validation import (
E   ModuleNotFoundError: No module named 'locksmith.plugins.cuo.validation'
=========================== short test summary info ============================
ERROR tests/plugins/cuo/test_validation.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.06s
```

Step 4 (watch it pass), after creating the implementation:

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_validation.py -v --import-mode=importlib
============================= test session starts ==============================
platform darwin -- Python 3.14.1, pytest-9.1.1, pluggy-1.6.0 -- /Users/seriouscoderone/code/locksmith/.venv/bin/python
cachedir: .pytest_cache
PySide6 6.10.3 -- Qt runtime 6.10.3 -- Qt compiled 6.10.3
rootdir: /Users/seriouscoderone/code/locksmith
configfile: pyproject.toml
plugins: cov-7.1.0, qt-4.5.0
collecting ... collected 17 items

tests/plugins/cuo/test_validation.py::test_a_good_payload_has_no_errors PASSED [  5%]
tests/plugins/cuo/test_validation.py::test_every_missing_required_field_is_reported_at_once PASSED [ 11%]
tests/plugins/cuo/test_validation.py::test_a_value_outside_the_enum_is_rejected PASSED [ 17%]
tests/plugins/cuo/test_validation.py::test_a_jurisdiction_that_fails_the_pattern_is_rejected PASSED [ 23%]
tests/plugins/cuo/test_validation.py::test_a_structurally_valid_but_fictional_jurisdiction_passes PASSED [ 29%]
tests/plugins/cuo/test_validation.py::test_a_lowercase_coverage_is_rejected PASSED [ 35%]
tests/plugins/cuo/test_validation.py::test_a_duplicate_coverage_is_rejected PASSED [ 41%]
tests/plugins/cuo/test_validation.py::test_an_empty_coverage_list_is_rejected PASSED [ 47%]
tests/plugins/cuo/test_validation.py::test_a_non_date_is_rejected PASSED [ 52%]
tests/plugins/cuo/test_validation.py::test_a_window_that_closes_before_it_opens_is_rejected PASSED [ 58%]
tests/plugins/cuo/test_validation.py::test_a_single_day_window_is_rejected_because_the_gate_is_strict PASSED [ 64%]
tests/plugins/cuo/test_validation.py::test_an_overlapping_mandate_for_the_same_scope_is_rejected PASSED [ 70%]
tests/plugins/cuo/test_validation.py::test_a_different_line_or_jurisdiction_is_not_an_overlap PASSED [ 76%]
tests/plugins/cuo/test_validation.py::test_a_non_overlapping_window_for_the_same_scope_is_accepted PASSED [ 82%]
tests/plugins/cuo/test_validation.py::test_overlap_is_the_standard_inclusive_interval_test[a0-b0-True] PASSED [ 88%]
tests/plugins/cuo/test_validation.py::test_overlap_is_the_standard_inclusive_interval_test[a1-b1-True] PASSED [ 94%]
tests/plugins/cuo/test_validation.py::test_overlap_is_the_standard_inclusive_interval_test[a2-b2-False] PASSED [100%]

============================== 17 passed in 0.10s ==============================
```

Full `tests/plugins/cuo/` package after landing (confirms all 25 pre-existing
tests still pass, plus the 17 new ones, 42 total, no regressions):

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
..........................................                               [100%]
42 passed in 0.19s
```

## Commit

```
$ git add src/locksmith/plugins/cuo/validation.py tests/plugins/cuo/test_validation.py
$ git commit -m "feat(cuo): pure validation of a mandate payload, with both pre-mint gates"
[claude/cuo-mandate-form 9c7b148e] feat(cuo): pure validation of a mandate payload, with both pre-mint gates
 2 files changed, 292 insertions(+)
 create mode 100644 src/locksmith/plugins/cuo/validation.py
 create mode 100644 tests/plugins/cuo/test_validation.py
```

Commit SHA: `9c7b148e5bebf1019fac2ea9fdfc033219885364`

Note: the working tree had two pre-existing unrelated modifications
(`.superpowers/sdd/.gitignore`, `brands/usurance/egf/oobis/EGjm-....cesr`) and an
untracked `.playwright-mcp/` directory before this task started (visible in the
initial `git status`). None of these were touched, staged, or committed by this
task — only the two files the brief named.

## Where the brief was wrong or ambiguous, and how it was resolved

1. **Step 4's expected count is off.** The brief says "Expected: PASS — 20
   passed." Counting the test functions in the brief's own Step-1 code block
   gives 14 plain `def test_...` functions plus one `@pytest.mark.parametrize`
   test with 3 cases = 17 collected items, not 20. The actual run above
   confirms 17. This looks like a stale count left over from an earlier draft
   of the test file (perhaps one with 3 more cases that got trimmed). It does
   not affect correctness — I did not add or remove any test to force a
   particular number, since the brief said to use its test code "verbatim."
   Flagging it here rather than treating it as license to edit the test file.

2. **Everything else matched.** Task 1's `schema_source` and Task 3's
   `mandate_copy` were already present in the repo exactly as the brief's
   "Context the parent agent cannot know" section described (`.fmt` not
   `.format`; `FIELD_ORDER` present with the six expected keys; `required_error`,
   `enum_error`, `pattern_error`, `date_error`, `COVERAGE_PATTERN`,
   `COVERAGE_DUPLICATE`, `WINDOW_ORDER`, `WINDOW_OVERLAP` all present with
   signatures matching how `validation.py` calls them). No adaptation was
   needed; both modules were used as-is.

3. No other discrepancies found between the brief's described interfaces and
   the actual Task 1 / Task 3 code.

## Concerns for the reviewer

- **The pre-mint ordering gate (highest-stakes rule in this task).** The gate
  is `if not opens < closes:` inside `validate_payload`, guarded by
  `both_are_dates` (both `window_opens` and `window_closes` parse via
  `date.fromisoformat`) and by `"window_closes" not in already` (skipped if
  `window_closes` already failed its own scalar checks, e.g. bad format). I
  verified by hand that this guard cannot be bypassed into a false pass: if
  either date is malformed, `both_are_dates` is `False` and the ordering/overlap
  branch is skipped entirely — the field-level date-format error (from
  `_scalar_errors`'s `c.fmt == "date"` check) is what surfaces instead, and the
  payload is still rejected (just for a different, correct reason: a malformed
  date can't be sequenced). I don't see a path where a `window_opens >=
  window_closes` payload validates clean. Worth an independent look given the
  brief's own framing that this is "the only point at which refusing costs
  nothing."

- **String comparison for date ordering/overlap.** Both the ordering gate and
  `windows_overlap` compare ISO-8601 date strings lexicographically rather than
  parsing to `date` objects for the comparison itself (parsing is only used to
  confirm the strings *are* valid ISO dates, via `_is_iso_date`). This is
  correct because ISO-8601's y-m-d ordering is lexicographic by construction,
  and the brief's own docstring on `windows_overlap` calls this out
  deliberately. Flagging only so the reviewer confirms they're comfortable with
  string comparison as the actual check rather than seeing it as an oversight.

- **`_scalar_errors`'s `text = value if isinstance(value, str) else str(value)`.**
  For every field in the current schema (`line_of_business`, `jurisdiction`,
  `window_opens`, `window_closes`, `thesis`) the payload value is expected to
  already be a string, so this coercion is inert today. It only matters if a
  future schema field is a non-string scalar with an enum/pattern/format
  constraint — worth knowing about but not a defect against the current schema
  or test suite, and I did not add a test for it since the brief didn't ask for
  one and the current schema never exercises that path.

- **Duplicate/pattern coverage-item messages report only the first offending
  item, not all of them** (`break` after appending in both loops of
  `_array_errors`). The brief's own test
  (`test_a_duplicate_coverage_is_rejected`) only checks the first duplicate is
  named, so this matches spec, but a coverages list with e.g. two independent
  duplicates or a mix of a duplicate and a bad-pattern item will only ever
  surface one message per array-level rule per validation pass. Matches the
  brief exactly; noting it in case the reviewer wants that revisited in a later
  task.

No other concerns. All 25 pre-existing `tests/plugins/cuo/` tests still pass
unchanged; the 17 new tests all pass; no Qt import anywhere in
`validation.py`.

---

## Round 2: reviewer-found defects (CRITICAL 1/2, IMPORTANT 3/4/5, MINOR 6/7/9)

The coordinator relayed a review that found two Critical defects in the code
above -- both from the brief's own verbatim implementation, not something I
introduced -- plus three Important test gaps and three Minor robustness/copy
issues. This section documents the fixes, applied directly to
`src/locksmith/plugins/cuo/validation.py` and
`tests/plugins/cuo/test_validation.py` (same two files; no new files).

### What changed, and why

**CRITICAL 1 -- mixed ISO-8601 forms invert a string compare.**
`date.fromisoformat` has accepted every ISO 8601 date form since Python 3.11
(`"20270101"`, `"2027-W01-1"`, not just `"2027-01-01"`), and the schema puts no
`pattern` on `window_opens`/`window_closes` -- only `format: "date"`. The old
code compared the raw strings (`opens < closes`), which is only chronologically
faithful within one fixed form: `'-'` is `0x2D`, `'0'` is `0x30`, so
`"2027-12-31" < "20270101"` is `True` even though 2027-12-31 is later.

**CRITICAL 2 -- `str()` coercion hid non-strings from the gate entirely.**
`_scalar_errors` computed `text = value if isinstance(value, str) else
str(value)` and format-checked `text`, so `str(date(2027, 12, 31)) ==
"2027-12-31"` parsed cleanly and reported no field error. The ordering gate
then tested `isinstance(opens, str)`, which was `False` for the original
`date` object, so the entire ordering/overlap block was skipped -- an inverted
window validated with zero errors.

**Fix (both):** added `_as_date(value) -> date | None`, which returns `None`
for anything that isn't a `str`, and otherwise `date.fromisoformat(value)` or
`None` on failure -- no coercion. `_scalar_errors`'s date check now calls
`_as_date(value)` on the **raw** value, not `text`. The ordering gate now
parses `opens`/`closes` via `_as_date` and compares the resulting `date`
objects (`opens_d < closes_d`), not the raw strings. `windows_overlap` does
the same internally (parses all four arguments, returns `False` if any fails
to parse) -- its docstring is corrected in place rather than deleted, per the
coordinator's instruction, since the lexicographic-sort reasoning was nearly
right and the correction (only true within one fixed form) is the valuable
part.

**IMPORTANT 3 -- half the interval test was untested.** Added a fourth
parametrized case to `test_overlap_is_the_standard_inclusive_interval_test`:
an existing mandate ending exactly the day the new one opens
(`("2027-06-01","2027-06-30")` vs `("2027-05-01","2027-06-01")` → `True`). The
original three cases only exercised the `a_opens <= b_closes` half.

**IMPORTANT 4 -- error sequence was asserted by nothing.** Renamed and
rewrote `test_missing_required_fields_are_reported_in_copy_field_order` (now
`..._not_schema_order`) to assert the reported field list, not a set.
Discovered while proving this myself: asserting the list against the real
`schema` fixture does **not** catch mutating `copy.FIELD_ORDER` to
`schema.order` in `validate_payload`, because on the actual bundled EGF,
`schema.order` already equals `copy.FIELD_ORDER` byte-for-byte (confirmed by
loading the real schema and comparing the two tuples directly -- both are
`('line_of_business', 'jurisdiction', 'coverages', 'window_opens',
'window_closes', 'thesis')`). `schema_source.py`'s own docstring already flags
this as a coincidence of the current bundle, not a guarantee. Fixed the test to
build a `MandateSchema` with the same `.fields` but a deliberately reversed
`.order`, then assert the reported sequence still follows `copy.FIELD_ORDER`.
Verified this version actually kills the mutation (see mutation-testing
section below) where the first version did not.

**IMPORTANT 5 -- `min_length`/`min_items` were dead branches.** The real
schema's floors (`minLength: 1` on `thesis`, `minItems: 1` on `coverages`) are
both already caught by `_empty()` before either branch runs, so no test in the
schema-driven suite could tell `if False:` apart from the real check. Added
two tests that synthesize a `FieldConstraints`/`MandateSchema` with a tighter
floor (`min_length=5`, `min_items=2`) and a value that is non-empty but still
under it, so the branch is genuinely exercised.

**MINOR 6 -- unhashable coverage item crashed the uniqueness check.**
`{"coverages": [["BI"]]}` raised `TypeError: unhashable type: 'list'` out of
`item in seen` / `seen.add(item)`. Fixed by keying membership on `str(item)`,
matching the pattern loop just below it in the same function. Added a
regression test with two identical nested-list items.

**MINOR 7 -- the `already`-errors guard was scoped too broadly.** The old
gate skipped the ordering/overlap check whenever `"window_closes" in already`
(i.e. `window_closes` had **any** field-level error). That's fine today
(`window_closes` has no `pattern`), but would silently suppress the ordering
check the day `window_closes` gains a `pattern` and a value fails it while
still parsing as a valid date -- contradicting the function's own "returns ALL
errors" docstring. Rescoped the guard to `opens_d is not None and closes_d is
not None` (i.e. "did this parse as a date"), which is exactly the condition
the gate actually needs and cannot be broadened by an unrelated future
constraint on the same field.

**MINOR 9 -- non-list `coverages` misdiagnosed as empty.** `{"coverages":
"BI"}` reported "Add at least one coverage code," which is wrong: the user did
supply something, just in the wrong shape. Changed `_array_errors`'s non-list
branch to return `copy.pattern_error(c.name)` instead of
`copy.required_error(c.name)` -- reusing existing `mandate_copy` text ("Coverages
is not in the required format.") rather than inventing new copy in this module,
keeping `mandate_copy.py` (Task 3, separately reviewed) as the sole owner of
user-visible strings. Added a regression test asserting the message no longer
contains "at least one."

**Not changed, per the coordinator's explicit instruction:** the `import
mandate_copy as copy` shadowing of the stdlib `copy` module (harmless here;
renaming it would be inconsistent with Tasks 3 and 6), and array checks
reporting only the first offender per rule (matches the brief's intent).

### Proof that Critical 1 and 2 are closed, the way the reviewer found them

Ran all four vectors against the fixed code (fresh brand/EGF load,
`__pycache__` cleared first):

```
mixed-form (dash vs compact): REJECTED -> [('window_closes', 'In force through must fall after in force from, and a window')]
mixed-form (dash vs iso-week): REJECTED -> [('window_closes', 'In force through must fall after in force from, and a window')]
date objects: REJECTED -> [('window_opens', 'Enter in force from as a date.'), ('window_closes', 'Enter in force through as a date.')]
ints: REJECTED -> [('window_opens', 'Enter in force from as a date.'), ('window_closes', 'Enter in force through as a date.')]
```

All four are now rejected (previously all four validated clean, per the
review). The mixed-form vectors are caught by the ordering gate (`WINDOW_ORDER`
on `window_closes`, because parsing now precedes comparison); the
non-string vectors are caught earlier, at the field-level date-format check on
**both** fields (since neither is a string), which is the correct behaviour --
a non-string never reaches the ordering gate at all.

Also ran the same four vectors **against the original vulnerable code**
(`git show 9c7b148e:src/locksmith/plugins/cuo/validation.py`, restored
temporarily, `__pycache__` cleared, then reverted) with the new test suite, to
prove the new regression tests actually catch what the reviewer found rather
than merely asserting something true by coincidence:

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_validation.py -v --import-mode=importlib
...
FAILED tests/plugins/cuo/test_validation.py::test_an_unhashable_coverage_item_does_not_crash_the_duplicate_check
FAILED tests/plugins/cuo/test_validation.py::test_a_non_list_coverages_reports_a_shape_problem_not_add_a_code
FAILED tests/plugins/cuo/test_validation.py::test_a_non_dash_iso_form_that_inverts_the_window_is_still_rejected
FAILED tests/plugins/cuo/test_validation.py::test_an_iso_week_form_that_inverts_the_window_is_still_rejected
FAILED tests/plugins/cuo/test_validation.py::test_a_python_date_object_is_rejected_by_the_field_check_not_silently_accepted
FAILED tests/plugins/cuo/test_validation.py::test_an_int_window_value_is_rejected_by_the_field_check_not_silently_accepted
========================= 6 failed, 21 passed in 0.24s =========================
```

Exactly the 6 tests tied to Critical 1 (2 tests), Critical 2 (2 tests), Minor 6
(1 test), and Minor 9 (1 test) fail against the vulnerable code; the other 21
(including the Important 3/4/5 tests, which target different, unrelated
branches) pass on both versions, as expected. Restored the fixed
`validation.py` immediately after.

### Mutation-testing proof for IMPORTANT 3, 4, 5 (`__pycache__` cleared before every run)

For each mutation: applied it to a temp copy of the fixed
`validation.py`, cleared `find . -path "*/cuo/__pycache__" -exec rm -rf {} +`,
ran `tests/plugins/cuo/test_validation.py`, then reverted from a saved-off
known-good copy and re-cleared `__pycache__` before the next mutation.

- **Finding 3** (`windows_overlap`'s `a_opens_d <= b_closes_d` mutated to
  `a_opens_d < b_closes_d`): FAILED, caught by the new fourth parametrized
  case --
  `AssertionError: assert False is True` on
  `windows_overlap('2027-06-01', '2027-06-30', '2027-05-01', '2027-06-01')`.

- **Finding 4** (`for name in copy.FIELD_ORDER:` mutated to `for name in
  schema.order:`): survived against my FIRST draft of the order test (which
  used the real `schema` fixture directly) -- 27/27 still passed, because
  `schema.order` already equals `copy.FIELD_ORDER` on the real bundled EGF (I
  confirmed this by loading the schema and printing both tuples: identical).
  Rewrote the test per the "Important 4" section above to use a scrambled
  `.order` on a synthesized schema; re-ran the same mutation, now FAILED as
  expected:
  `AssertionError: assert ['thesis', ...] == ['line_of_bus...', ..., 'thesis']`.
  Re-verified the fixed test passes against the correct implementation before
  moving on.

- **Finding 5a** (`min_length` branch mutated to `if False:`): FAILED, caught
  by `test_min_length_is_enforced_above_the_floor_the_real_schema_uses` --
  `AssertionError: assert set() == {'thesis'}`.

- **Finding 5b** (`min_items` branch mutated to `if False:`): FAILED, caught
  by `test_min_items_is_enforced_above_the_floor_the_real_schema_uses` --
  `AssertionError: assert set() == {'coverages'}`.

All four mutations killed after the fixes (Finding 4 only after correcting my
own first attempt at that test -- see above). This is the same failure mode
the coordinator warned about ("the reviewer mis-attributed two results to
bytecode staleness before doing that") -- clearing `__pycache__` between every
mutation and every revert was necessary in practice; I did it before every run
in this section.

### Final verification

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_validation.py -v --import-mode=importlib
============================= test session starts ==============================
platform darwin -- Python 3.14.1, pytest-9.1.1, pluggy-1.6.0 -- /Users/seriouscoderone/code/locksmith/.venv/bin/python
...
collecting ... collected 27 items

tests/plugins/cuo/test_validation.py::test_a_good_payload_has_no_errors PASSED
tests/plugins/cuo/test_validation.py::test_every_missing_required_field_is_reported_at_once PASSED
tests/plugins/cuo/test_validation.py::test_missing_required_fields_are_reported_in_copy_field_order_not_schema_order PASSED
tests/plugins/cuo/test_validation.py::test_a_value_outside_the_enum_is_rejected PASSED
tests/plugins/cuo/test_validation.py::test_a_jurisdiction_that_fails_the_pattern_is_rejected PASSED
tests/plugins/cuo/test_validation.py::test_a_structurally_valid_but_fictional_jurisdiction_passes PASSED
tests/plugins/cuo/test_validation.py::test_a_lowercase_coverage_is_rejected PASSED
tests/plugins/cuo/test_validation.py::test_a_duplicate_coverage_is_rejected PASSED
tests/plugins/cuo/test_validation.py::test_an_empty_coverage_list_is_rejected PASSED
tests/plugins/cuo/test_validation.py::test_an_unhashable_coverage_item_does_not_crash_the_duplicate_check PASSED
tests/plugins/cuo/test_validation.py::test_a_non_list_coverages_reports_a_shape_problem_not_add_a_code PASSED
tests/plugins/cuo/test_validation.py::test_a_non_date_is_rejected PASSED
tests/plugins/cuo/test_validation.py::test_a_window_that_closes_before_it_opens_is_rejected PASSED
tests/plugins/cuo/test_validation.py::test_a_single_day_window_is_rejected_because_the_gate_is_strict PASSED
tests/plugins/cuo/test_validation.py::test_a_non_dash_iso_form_that_inverts_the_window_is_still_rejected PASSED
tests/plugins/cuo/test_validation.py::test_an_iso_week_form_that_inverts_the_window_is_still_rejected PASSED
tests/plugins/cuo/test_validation.py::test_a_python_date_object_is_rejected_by_the_field_check_not_silently_accepted PASSED
tests/plugins/cuo/test_validation.py::test_an_int_window_value_is_rejected_by_the_field_check_not_silently_accepted PASSED
tests/plugins/cuo/test_validation.py::test_an_overlapping_mandate_for_the_same_scope_is_rejected PASSED
tests/plugins/cuo/test_validation.py::test_a_different_line_or_jurisdiction_is_not_an_overlap PASSED
tests/plugins/cuo/test_validation.py::test_a_non_overlapping_window_for_the_same_scope_is_accepted PASSED
tests/plugins/cuo/test_validation.py::test_overlap_is_the_standard_inclusive_interval_test[a0-b0-True] PASSED
tests/plugins/cuo/test_validation.py::test_overlap_is_the_standard_inclusive_interval_test[a1-b1-True] PASSED
tests/plugins/cuo/test_validation.py::test_overlap_is_the_standard_inclusive_interval_test[a2-b2-False] PASSED
tests/plugins/cuo/test_validation.py::test_overlap_is_the_standard_inclusive_interval_test[a3-b3-True] PASSED
tests/plugins/cuo/test_validation.py::test_min_length_is_enforced_above_the_floor_the_real_schema_uses PASSED
tests/plugins/cuo/test_validation.py::test_min_items_is_enforced_above_the_floor_the_real_schema_uses PASSED

============================== 27 passed in 0.16s ==============================
```

Full package (confirms the other 25 pre-existing `tests/plugins/cuo/` tests
are still unaffected):

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
....................................................                     [100%]
52 passed in 0.30s
```

`grep -ni "qt\|pyside" src/locksmith/plugins/cuo/validation.py` still shows
only the docstring's "Qt-free," no actual import.

### Where my own Round-1 concern turned out to be wrong

My Round-1 report flagged `_scalar_errors`'s `str()` coercion as "inert
today" against the current schema. That was wrong, and wrong in the
load-bearing direction: the coercion was not inert on the *date* fields
specifically (it made non-string dates pass silently, which is Critical 2),
even though the schema has no non-string enum/pattern field today. I
conflated "no non-string field exists among enum/pattern-constrained fields"
with "no non-string value can reach a `format: date` field," which are
different claims -- the second is false because `validate_payload` never
type-checks the payload before dispatch. Lesson taken: "the schema doesn't
model this shape" is not the same guarantee as "the function can't receive
this shape."

### Commit (round 2)

Second commit, on top of `9c7b148e`, touching only the same two files.

