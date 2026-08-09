# Task 3 report: Copy, with a count-aware summary

(Note: this file previously held a stale report from an unrelated task -- a
`keripy` worktree build of a `keri-web` wheel. That content has been fully
replaced with this task's actual report, which covers the CUO mandate-form copy
module in this repo, `locksmith`.)

## What was implemented

- `src/locksmith/plugins/cuo/mandate_copy.py` -- pure-Python (no Qt import) module
  holding every user-visible string for the CUO product-mandate form: `H1`,
  `PAGE_INTRO`, `FIELD_ORDER` (the single authority for field sequence, kept
  deliberately independent of the schema -- see the module's own comment above the
  constant, copied verbatim from the brief and left intact), `FIELD_LABEL`,
  `FIELD_HELP`, `FIELD_PLACEHOLDER`, the review-panel strings
  (`REVIEW_TITLE`/`REVIEW_SIGNER`/`REVIEW_CAUTION`/`REVIEW_CONFIRM`/`REVIEW_BACK`),
  the form buttons (`FORM_PRIMARY`/`FORM_CANCEL`/`IN_FLIGHT`), the validation-message
  constants (`JURISDICTION_PATTERN`, `COVERAGE_PATTERN`, `COVERAGE_DUPLICATE`,
  `WINDOW_ORDER`, `WINDOW_OVERLAP`), the five error-message functions
  (`error_summary`, `required_error`, `enum_error`, `pattern_error`, `date_error`),
  and `TOKENS` (the ratified interpolation-token allowlist).
- `tests/plugins/cuo/test_mandate_copy.py` -- the contract tests: no forbidden
  words, no shouting punctuation, no unratified interpolation tokens, correct
  singular/plural counting in `error_summary` (including its `ValueError` floor at
  count < 1), every submitted field has a label/help/placeholder, the intro states
  both irreversible facts (edited + permanent, anyone/publish), the review caution
  says it is final and cannot be edited, `FIELD_ORDER` matches the schema's field
  set exactly and is not alphabetical (first field is `line_of_business`), the enum
  error lists the offending value and the allowed set, and every required-field
  message is capitalized and sentence-terminated.

Both files were copied verbatim from the brief -- no wording was altered. I did not
open the referenced spec asset
(`docs/superpowers/specs/assets/2026-08-08-cuo-mandate-copy.json`) since the brief
states it already contains the complete, ready-to-use text; re-deriving strings
from it independently would have risked introducing a divergence the brief was
explicit about avoiding ("the strings are not yours to improve").

TDD order followed: wrote the test file, ran it and watched it fail on the missing
module, wrote the implementation, ran the test file alone (12 passed), then ran the
whole `tests/plugins/cuo/` package (22 passed: 10 pre-existing from Task 1's
`test_schema_source.py` + 12 new), then committed.

## Test commands and full output

### Step 2 -- confirm the test fails first

```
cd /Users/seriouscoderone/code/locksmith
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_mandate_copy.py -q --import-mode=importlib
```

Output:

```
==================================== ERRORS ====================================
___________ ERROR collecting tests/plugins/cuo/test_mandate_copy.py ____________
ImportError while importing test module '/Users/seriouscoderone/code/locksmith/tests/plugins/cuo/test_mandate_copy.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
tests/plugins/cuo/test_mandate_copy.py:12: in <module>
    from locksmith.plugins.cuo import mandate_copy as copy
E   ImportError: cannot import name 'mandate_copy' from 'locksmith.plugins.cuo' (/Users/seriouscoderone/code/locksmith/src/locksmith/plugins/cuo/__init__.py)
=========================== short test summary info ============================
ERROR tests/plugins/cuo/test_mandate_copy.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.05s
```

(The brief predicted `ModuleNotFoundError`; the actual exception was
`ImportError: cannot import name 'mandate_copy' ...` because `locksmith.plugins.cuo`
is a real package that already exists and imports cleanly -- the failure is on the
submodule attribute, not the parent package. Same root cause -- the module doesn't
exist yet -- different exception subclass. See "ambiguities" below.)

### After implementation -- the new module alone

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_mandate_copy.py -q --import-mode=importlib
```

Output:

```
............                                                             [100%]
12 passed in 0.07s
```

### Step 4 -- the whole `tests/plugins/cuo/` package

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
```

Output:

```
......................                                                   [100%]
22 passed in 0.11s
```

(22 = 10 from Task 1's `tests/plugins/cuo/test_schema_source.py`, verified
separately, + 12 new from this task. No Task 2 test module exists in this
worktree yet, so the brief's "Task 1, 2 and 3 modules all green" could not be
checked as literally three modules -- see "ambiguities" below.)

## Commit

SHA: `e889a2a3bd7a34fa00d881a7dff97e5291d08b97`
Message: `feat(cuo): the form's copy, with a count-aware error summary` (plus the
standard `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` trailer my
environment appends to every commit I make -- the subject line matches the brief's
Step 5 exactly).
Files: `src/locksmith/plugins/cuo/mandate_copy.py`,
`tests/plugins/cuo/test_mandate_copy.py` (only these two -- the repo had unrelated
pre-existing local modifications to `.superpowers/sdd/.gitignore` and
`brands/usurance/egf/oobis/EGjm-X1JMz-yKFeumEZ9meSVNvnV8VTXmjJMlyBVMMTO.cesr`, plus
an untracked `.playwright-mcp/` directory, none of which I created or touched; they
remain uncommitted, exactly as I found them).

## Things in the brief that turned out to be wrong or ambiguous, and how I resolved them

1. **Step 2's predicted exception type.** The brief says "Expected: FAIL --
   `ModuleNotFoundError: No module named 'locksmith.plugins.cuo.mandate_copy'`".
   The actual failure was `ImportError: cannot import name 'mandate_copy' from
   'locksmith.plugins.cuo'`. Both are `ImportError` (`ModuleNotFoundError` is a
   subclass of `ImportError`) and both mean exactly the same thing operationally --
   the module the test imports does not exist -- so I treated the test run as
   satisfying "watch it fail for the right reason" and proceeded. I did not change
   any code to force the more specific exception type; that would have meant
   deviating from the brief's own `from locksmith.plugins.cuo import mandate_copy as
   copy` import statement, which the brief's test file specifies verbatim. Flagging
   this rather than silently absorbing it, per the instruction that a
   predicted-wrong detail is worth surfacing even when it doesn't change the
   outcome.

2. **Step 4's "Task 1, 2 and 3 modules all green."** Only Task 1's
   `test_schema_source.py` existed in this worktree before this task ran; there was
   no Task 2 test module to include. This matches the top-level framing that Task 3
   "has no dependencies on other tasks" and can land in any order relative to Task 2,
   so I read Step 4 as a description of the eventual steady state once all tasks
   land, not a precondition for this task, and ran it against whatever existed
   (Task 1 + Task 3 = 22 passed). No action needed beyond noting it for whoever
   integrates the full 8-task plan.

Everything else in the brief -- the module docstring and comments, the exact string
values, the function bodies, the test assertions -- was copied and used verbatim, so
there was nothing else to resolve.

## Concerns for the reviewer

- **The module's own docstring contains the phrase "Invalid input."** as a
  quoted negative example (`never "Invalid input."`), so the raw file text of
  `mandate_copy.py` does contain the substring "invalid input" if you grep the file
  naively. This does NOT trip `test_no_forbidden_word_appears_anywhere`, because
  that test walks `dir(copy)` and skips every name starting with `_` -- and
  `__doc__` starts with `_`. I verified this directly (ran the test's own
  `_all_strings()` traversal by hand against the live module) rather than trusting
  the test to have caught it, since a forbidden-word canary that silently exempts
  docstrings is a gap worth knowing about even though it's out of scope for this
  task to close. Result: the scan over the tested string constants found zero
  matches for any forbidden word. If a future draft ever moved that quoted example
  out of the docstring and into an actual module-level string, the forbidden-word
  test would still only catch it if the resulting attribute name avoided a leading
  underscore -- this is a property of the test's own traversal (inherited from the
  brief verbatim), not something Task 3 introduced, and I did not change it without
  asking.

- **`FIELD_ORDER`'s canary test depends on the built usurance brand bundle**
  (via `tests/plugins/cuo/conftest.py`'s autouse fixture, which builds it if
  absent). It built and passed cleanly in this run; flagging only because it's the
  one test in this module with an external dependency (the schema-loading round
  trip through `egf_local_dir()` and `load_mandate_schema`), so if CI has a
  differently-provisioned or stale brand bundle, that specific test
  (`test_field_order_covers_exactly_the_schema_s_submitted_fields`) is the one to
  look at first.

- No other functional concerns. All 12 new tests pass, the full `cuo` package
  (22 tests) passes, and the module imports no Qt symbol (`from __future__ import
  annotations` plus pure string/dict/tuple/function definitions only).

---

## Addendum: review findings addressed

The coordinator's review found the `_REQUIRED` dict was invisible to the module's
own policy tests (proved by mutation: an injected `"Please choose a line of
business."` passed all 12 tests). Four changes were made in response.

### 1. (Critical) `_REQUIRED` renamed to `REQUIRED`; scan coverage made explicit

`_REQUIRED` -> `REQUIRED` in `mandate_copy.py`, `required_error()` updated to match.
Added a doc-comment above the dict explaining why the underscore was the mistake
(kept as a permanent guardrail against a future rename re-hiding it). Added two
tests to `test_mandate_copy.py`:

- `test_the_forbidden_word_scan_actually_reaches_the_required_messages` -- asserts
  `_all_strings()` actually yields `REQUIRED[<field>]` for every field in
  `FIELD_ORDER`, so a future accidental re-underscoring is caught by name rather
  than by hoping a policy test happens to notice.
- `test_there_is_a_required_message_for_every_field` -- `set(copy.REQUIRED) ==
  set(copy.FIELD_ORDER)`. (Dropped the coordinator's stray `_=None` parameter as
  instructed.)

**Mutation-testing verification (as required before commit):**

Injected the exact string the reviewer used, `"Please choose a line of
business."`, into `REQUIRED["line_of_business"]`, then ran:

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_mandate_copy.py -q --import-mode=importlib
```

Observed output (FAILS, catching the injected word):

```
F..............                                                          [100%]
=================================== FAILURES ===================================
___________________ test_no_forbidden_word_appears_anywhere ____________________

    def test_no_forbidden_word_appears_anywhere():
        for name, text in _all_strings():
            lowered = text.lower()
            for word in _FORBIDDEN:
>               assert word not in lowered, f"{name} contains {word!r}: {text!r}"
E               AssertionError: REQUIRED[line_of_business] contains 'please': 'Please choose a line of business.'
E               assert 'please' not in 'please choo...of business.'
E
E                 'please' is contained here:
E                   please choose a line of business.
E                 ? ++++++

tests/plugins/cuo/test_mandate_copy.py:38: AssertionError
=========================== short test summary info ============================
FAILED tests/plugins/cuo/test_mandate_copy.py::test_no_forbidden_word_appears_anywhere
1 failed, 14 passed in 0.08s
```

Reverted the injected string back to `"Choose a line of business."`, then ran the
same command again. Observed output (PASSES, clean):

```
...............                                                          [100%]
15 passed in 0.08s
```

This confirms the hole the reviewer found by mutation is now closed by the rename
alone (the two new tests above are belt-and-suspenders on top of that; the
mutation was caught by the pre-existing `test_no_forbidden_word_appears_anywhere`
once `REQUIRED` stopped being underscore-prefixed).

### 2. (Important) `error_summary` now rejects non-`int`

Changed the guard from `if count < 1:` to `if not isinstance(count, int) or count
< 1:`, and changed the error message to use `{count!r}` instead of `{count}` so a
non-int value's type is visible in the message. Added
`copy.error_summary(1.5)` to `test_the_summary_refuses_a_nonsense_count`, alongside
the existing `error_summary(0)` case. Did not add a `bool`-specific carve-out (e.g.
rejecting `True`/`False`) since `bool` is a subclass of `int` in Python and the
review only asked to reject non-`int` values; that was outside what was asked and I
did not add untested behavior on my own initiative.

### 3. (Minor) `TOKENS` corrected to the exact set of tokens actually used

Removed `"field"` and `"allowed"` from `TOKENS` as instructed. While verifying with
the new bidirectional test, I found `"count"` was *also* ratified-but-unused --
`error_summary` builds `"Fix {count} ... before signing."` as a computed f-string
inside the function body, not as a stored template string with a `{count}`
placeholder that `_all_strings()` ever scans, so no module-level string constant
ever contains `{count}`. The coordinator's message named only `field` and
`allowed` explicitly but described the fix as "make the ratification test
bidirectional," and the new bidirectional test would have failed with
`ratified-but-unused={'count'}` had I left it in, so I removed it too. Final
`TOKENS`:

```python
TOKENS = frozenset({
    "code", "cuo_name", "line_of_business", "jurisdiction",
    "existing_opens", "existing_closes",
})
```

Added `test_tokens_is_exactly_the_set_of_tokens_actually_used` (the coordinator's
text, verbatim) alongside the pre-existing `test_every_interpolation_token_is_ratified`
rather than replacing it -- the two check different things (per-string "used ⊆
ratified" with a precise offending-string name, vs. aggregate "used == ratified"
across the whole module) and both add distinct value. Ran it after fix 1 landed,
as instructed, so `REQUIRED`'s six strings were already inside the scan when I
verified `TOKENS`; none of them use any token, so no ratification was needed on
that side.

### 4. (Minor) `test_required_errors_exist_for_every_field_name_used` now covers all six fields

Changed the hardcoded 4-field tuple to `for field in copy.FIELD_ORDER:`, which
iterates all six fields declared for the form.

### Finding not changed (as instructed)

The jurisdiction-pattern/enum-error asymmetry (some error strings echo the
offending value, `JURISDICTION_PATTERN` does not) was left as-is per the
coordinator's explicit instruction not to change it.

### Full suite after all four fixes

```
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
```

```
.........................                                                [100%]
25 passed in 0.14s
```

(25 = 10 from Task 1's `test_schema_source.py` + 15 from `test_mandate_copy.py`,
up from 12 before this round -- 3 net new tests: the two `REQUIRED`-coverage tests
from fix 1, plus the bidirectional `TOKENS` test from fix 3.)

Grepped the repo for any other reference to `_REQUIRED` post-rename
(`grep -rn "_REQUIRED" src/ tests/`) -- the only hits are unrelated `ssl.CERT_REQUIRED`
and `PHASE_BOOTSTRAP_REQUIRED` symbols in other plugins, plus this module's own
explanatory comment mentioning the old name. No stale importers, since no
consuming task (form page, validation, review panel) has landed yet.

### Second commit

```
git add src/locksmith/plugins/cuo/mandate_copy.py tests/plugins/cuo/test_mandate_copy.py
git commit -m "fix(cuo): close the REQUIRED policy-scan blind spot, reject non-int counts, exact-match TOKENS"
```

SHA: see top-level status line returned to the coordinator.

### Concerns for the reviewer (this round)

- None beyond what's already logged above. The mutation-testing verification was
  run both ways (inject -> FAIL, revert -> PASS) exactly as required, and the
  output is reproduced verbatim above rather than asserted.
