# Task 4 Report: A nullable date field

## Status: DONE_WITH_CONCERNS

## Commit
`828946588c855d8d2ddb611d30d982cec4e448a4` on branch `claude/cuo-mandate-form`:
```
feat(cuo): a nullable date field, MM/DD/YYYY on screen and ISO in the payload
 src/locksmith/plugins/cuo/date_field.py | 93 +++++++++++++++++++++++++++++++++
 tests/plugins/cuo/test_date_field.py    | 78 +++++++++++++++++++++++++++
 2 files changed, 171 insertions(+)
```

## What was implemented

`src/locksmith/plugins/cuo/date_field.py` — `MandateDateField(QWidget)`, a nullable
date control wrapping `QDateEdit`:

- `iso_value() -> str` — `""` when unset, else `yyyy-MM-dd`.
- `set_iso(value: str) -> None` — parses `yyyy-MM-dd`; anything unparseable (or
  falsy) resets to empty. No range/ordering/correction logic — `validation.py`
  owns rules, this widget only round-trips a value or reports empty.
- `clear() -> None`, `is_empty() -> bool`, `display_format() -> str`,
  `set_invalid(bool) -> None` (repaints the border red via `colors.DANGER`,
  matching `LocksmithLineEdit`'s look — no `background-color` set, by design, so
  the control inherits the parent's background).
- `changed = Signal()`, emitted via the underlying `QDateEdit.dateChanged`.

Empty-state mechanism: Qt's `specialValueText`-on-`minimumDate` idiom, sentinel
`_EMPTY = QDate(1, 1, 1)` (year 1, Qt's earliest representable date) — see "brief
defects" below for why this needed two rounds of correction and a different Qt
call than the one the brief specified.

`tests/plugins/cuo/test_date_field.py` — the brief's 7 tests plus 1 added test (8
total), transcribed verbatim except for the two changes the coordinator
specified: an added line in `test_the_empty_sentinel_is_not_a_date_a_user_could_pick`'s
docstring naming it as the clamping regression test, and a new
`test_the_sentinel_is_the_minimum_so_no_real_date_can_be_clamped_onto_it` that
round-trips five dates (`0001-01-02`, `1000-06-15`, `1752-09-14`, `1900-01-01`,
`2027-01-01`) through `set_iso`/`iso_value` and asserts none clamp or read as
empty.

## Test commands and output

Step 2 (brief), before the implementation existed:
```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_date_field.py -q --import-mode=importlib
ERROR collecting tests/plugins/cuo/test_date_field.py
ModuleNotFoundError: No module named 'locksmith.plugins.cuo.date_field'
1 error in 0.06s
```

Step 4 (brief), final implementation:
```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_date_field.py -q --import-mode=importlib
........                                                                 [100%]
8 passed in 0.16s
```

Full `tests/plugins/cuo/` regression check (52 pre-existing + 8 new):
```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
............................................................             [100%]
60 passed in 0.38s
```

## What was wrong in the brief, and how it was resolved

Two real defects were found by direct probing against real PySide6 (6.10.3), not
by reasoning about Qt's docs. Both concern the empty-sentinel mechanism only —
nothing about the widget's public contract, its tests' intent, or the
"not a validation gate" constraint changed.

**1. Sentinel value collided with a legitimate date (caught before implementing,
fixed with the coordinator's sign-off).** The brief's implementation used
`_EMPTY = QDate(1900, 1, 1)` together with `setMinimumDate(_EMPTY)`. `QDateEdit`
does not just mark the minimum — it **clamps**: `setDate()` on anything earlier
than `minimumDate()` is silently pulled up to it. The brief's own regression test
sets `1752-09-14` (earlier than 1900-01-01) and asserts it reads back unchanged —
which is impossible under that sentinel, since `setDate(1752-09-14)` becomes
`1900-01-01`, which then equals the sentinel and reads as empty. Confirmed with a
throwaway script against the real widget before touching any file. Resolved by
moving the sentinel to `QDate(1, 1, 1)` (year 1, Qt's earliest representable
date), per the coordinator's explicit instruction, plus their two follow-on asks:
the clamping explanation baked into the `_EMPTY` comment, and the existing
regression test's docstring naming the failure mode it guards against.

**2. The year-1 fix didn't work with the literal Qt call the brief/coordinator
named, and a second Qt quirk was needed (found while implementing the
coordinator's fix, not flagged back before proceeding — see concern below).**
After switching to `_EMPTY = QDate(1, 1, 1)`, four tests still failed, including
the brief's own three original passing tests (`test_a_fresh_field_is_empty...`,
`test_clearing_returns_it_to_empty`, `test_an_unparseable_value_leaves_the_field_empty`).
Root cause, again confirmed by direct probe: `QDateEdit.setMinimumDate()` called
on its own is silently re-clamped by Qt to a *built-in floor of 1752-09-14* — the
call raises no error and no warning, but `minimumDate()` read back afterward is
still `1752-09-14`, not the year-1 value that was set. That made `1752-09-14`
itself the real (accidental) sentinel, reproducing defect #1 one layer down.
Verified: `setMinimumDate(QDate(1,1,1))` followed by a *separate*
`setMaximumDate(...)` call still clamps to `1752-09-14`; only
`setDateRange(QDate(1,1,1), QDate(9999,12,31))` — setting both bounds in one
call — actually honors year 1. Switching the widget's setup from
`setMinimumDate(_EMPTY)` to `setDateRange(_EMPTY, QDate(9999, 12, 31))` fixed all
8 tests with no other code changes. This is documented in a code comment at the
call site in `date_field.py` so a future reader doesn't "simplify" it back to
`setMinimumDate` and silently reintroduce the bug.

## Concern for the reviewer

I did not go back to ask before applying fix #2 (the `setDateRange` vs
`setMinimumDate` finding). My reasoning: the coordinator's design decision — sentinel
= `QDate(1, 1, 1)` — was already explicitly approved; what I found next was purely
*which Qt call actually delivers that already-approved value*, not a new design
question, and I had a green 8/8 test run as evidence before moving on. But the
coordinator's message did also say "keep the `specialValueText`-on-`minimumDate`
idiom" by name, and my final code does not literally do that — it uses
`setDateRange` instead, because `setMinimumDate` measurably doesn't work for this
sentinel on this Qt version. If the coordinator wants to weigh in on that
substitution specifically (e.g. in case a different Qt/PySide6 version on some
other machine behaves differently), that's the one open thread from this task.
Everything else — the widget's contract, the "not a validation gate" boundary,
the colour tokens, the geometry, the commit message — matches the brief exactly.

No other concerns. `validation.py` was not touched. No hex colors were
hardcoded; only `colors.BORDER`, `colors.DANGER`, and `colors.TEXT_PRIMARY` are
used, matching what's verified to exist in `locksmith.ui.colors`.

## Note: pre-existing stale report file

This file (`task-4-report.md`) previously contained a report from an unrelated
prior task (a `keri-web`/FortWeb C2 acceptance-gate task, dated Jul 26) — it has
been fully overwritten with this task's report.

---

## Review round 2: Critical fix — stepping/wheel could defeat the empty state

### The defect

Reviewed and independently re-verified: both prior deviations (`QDate(1,1,1)`
sentinel, `setDateRange` instead of `setMinimumDate`) were confirmed necessary,
not liberties. One new **Critical** surfaced that neither the brief nor my first
pass had probed for: interactive input.

`specialValueText` only changes what is *painted* at the minimum — Qt still
treats the minimum as a real, steppable value. Reproduced exactly as the
coordinator described, before making any change:

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -c "... QTest.keyClick(field._edit, Qt.Key_Up) ..."
fresh is_empty: True iso: ''
after Up: is_empty: False iso: '0001-02-01'
```

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -c "... app.sendEvent(field._edit, QWheelEvent(...)) ..."
fresh is_empty: True iso: ''
after wheel: is_empty: False iso: '0001-02-01'
```

One Up-arrow or one wheel-scroll on a freshly-opened, untouched field silently
produced a date (`0001-02-01`) the user never chose — exactly the class of defect
this whole widget exists to prevent, now reachable without even touching the
keyboard's digit keys.

### The fix

Before writing the fix, confirmed by direct probe that `QAbstractSpinBox`'s wheel
handling dispatches through `stepBy()` on this Qt version — so a single `stepBy`
override closes both the arrow-key and the wheel path; no separate `wheelEvent`
override is needed:

```
fresh date: 0001-01-01
after Up: 0001-01-01      (unchanged — guard worked)
after wheel: 0001-01-01   (unchanged — guard worked, same override)
after set + Up: 2027-07-15  (stepping still works once a date is chosen)
```

Added `_SentinelGuardedDateEdit(QDateEdit)` to `date_field.py`, a private
subclass whose only override is:

```python
def stepBy(self, steps: int) -> None:
    if self.date() == _EMPTY:
        return
    super().stepBy(steps)
```

with the docstring the coordinator specified, plus a class-level docstring
recording what was measured and why no `wheelEvent` override was needed.
`MandateDateField.__init__` now instantiates `_SentinelGuardedDateEdit(self)`
instead of a bare `QDateEdit(self)`. Nothing else in the class changed.

### Non-vacuity proof (reproduced the Critical exists, then confirmed the fix closes it)

1. Reproduced the bug against the pre-fix code (bare `QDateEdit`) via direct
   `QTest.keyClick`/`QWheelEvent` probes — shown above.
2. Implemented the `stepBy` guard.
3. Temporarily reverted the guard in-place (`self._edit = QDateEdit(self)  #
   TEMP-REVERT-FOR-PROOF`), cleared `tests/plugins/cuo/__pycache__` and
   `src/locksmith/plugins/cuo/__pycache__`, and reran only the three new
   interactive tests:
   ```
   $ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_date_field.py -q --import-mode=importlib -k "up_arrow or wheel_scroll or stepping_still"
   FF.
   2 failed, 1 passed, 10 deselected in 0.14s
   ```
   Confirmed the failures were exactly the two guard tests
   (`test_an_up_arrow_on_an_empty_field_does_not_invent_a_date`,
   `test_a_wheel_scroll_on_an_empty_field_does_not_invent_a_date`), and that
   `test_stepping_still_works_once_a_date_is_chosen` passed regardless (it
   doesn't depend on the guard, since it only steps a field that already has a
   date set) — so the non-vacuity check is clean, not a false positive from an
   unrelated failure.
4. Restored the guard, cleared `__pycache__` again, reran the full suite:
   ```
   $ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
   .................................................................        [100%]
   65 passed in 0.43s
   ```
5. Ran one more direct real-input probe (outside pytest, matching the
   coordinator's own verification method) against the fixed code as a final
   sanity check:
   ```
   fresh: True ''
   after Up on empty: True ''
   after wheel on empty: True ''
   after set + Up: False '2027-07-15'
   ```

### New tests added (5, on top of the prior 8 — 13 total in `test_date_field.py`)

- `test_an_up_arrow_on_an_empty_field_does_not_invent_a_date` — real
  `QTest.keyClick(field._edit, Qt.Key_Up)` on an empty, shown/exposed field.
- `test_a_wheel_scroll_on_an_empty_field_does_not_invent_a_date` — a real
  `QWheelEvent` dispatched via `QApplication.sendEvent`, same shape.
- `test_stepping_still_works_once_a_date_is_chosen` — proves the guard is not a
  read-only trap: after `set_iso`, an Up-arrow must change the value away from
  what was set.
- `test_setting_the_same_iso_value_does_not_emit_changed` — `qtbot.assertNotEmitted`
  around `set_iso` called twice with the identical value.
- `test_clearing_an_already_empty_field_does_not_emit_changed` — same, around
  `clear()` on a field that is already empty.

Both zero-emission tests close the "IMPORTANT" gap the coordinator flagged:
verified-by-probe-but-untested behavior that a spurious `changed` emit would
break the project's "no errors before the first submit" rule.

### Minor fixed: comment overclaim

Reworded both the `_EMPTY` sentinel comment and the matching claim in the module
docstring. `QDate(-1, 1, 1)` is valid (`isValid() == True`) — `QDate` supports
BCE years — so year 1 is not actually "Qt's earliest representable date". The
comments now say what's true and load-bearing instead: the sentinel sits below
every date a mandate could plausibly carry, and `setDateRange`'s floor makes
anything earlier than it unreachable through this widget, so nothing enterable
can ever collide with it.

### Final full-suite run (post-fix, pycache cleared immediately before)

```
$ find . -name "__pycache__" -path "*cuo*" -exec rm -rf {} +
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
.................................................................        [100%]
65 passed in 0.43s
```

65 = 52 pre-existing (untouched, still green) + 13 in `test_date_field.py` (7
from the brief + 1 sentinel-relationship test from round 1 + 5 from this round).

### Concerns for the reviewer (round 2)

None blocking. Two small things worth a second set of eyes:

1. The non-vacuity proof reverted the fix **in-place** in the working file
   (`self._edit = QDateEdit(self)  # TEMP-REVERT-FOR-PROOF`) rather than via a
   git stash/worktree, then edited it back to `_SentinelGuardedDateEdit(self)`.
   The final committed file has no trace of the revert, and the diff was
   re-inspected after restoring to confirm it matches the pre-revert version
   exactly — but flagging the method since it touched the file on disk mid-proof
   rather than using an isolated copy.
2. The guard relies on `QAbstractSpinBox.wheelEvent` dispatching through
   `stepBy()` on this Qt/PySide6 version (6.10.3) rather than handling the wheel
   independently. Confirmed by direct probe, and the class docstring records
   that measurement, but if a future Qt version changes that internal wiring,
   the wheel path could reopen without `stepBy` itself being touched. Worth a
   note-to-self for whoever next upgrades PySide6 on this project.

### Commit

Second commit on this task, on top of `828946588c855d8d2ddb611d30d982cec4e448a4`
(see the top of this file for that commit's message/diff). SHA and summary line
below once committed — filled in immediately after `git commit`.
