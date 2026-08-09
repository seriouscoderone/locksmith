# Task 5 report: the mandate review (read-back) dialog

**Note:** this file previously held an unrelated stale report (a different task
about selectable `QMessageBox` alerts / `message_box.py`). It has been overwritten
with the correct report for Task 5 (the CUO mandate review dialog).

## What was implemented

Followed the brief's TDD order exactly, with a verification pass against real
PySide6/locksmith code before trusting any of the brief's assumptions (per the
instruction to probe Qt behaviour rather than reason about it).

1. **Verified every interface the brief relies on, against the actual source, before
   writing anything:**
   - `LocksmithDialog.__init__` (`src/locksmith/ui/toolkit/widgets/dialogs.py`) —
     confirmed keyword args `parent`, `title`, `content`, `buttons` all exist;
     `buttons` is consumed as a `QHBoxLayout` and reparented via
     `button_container.addLayout(buttons)` (`dialogs.py:455`), and `content` is
     reparented into the scroll area's `content_layout`
     (`dialogs.py:414-441`, `content_layout.addWidget(content)`) — so anything nested
     inside the `body`/`buttons` widgets the review dialog builds is a real descendant
     of the dialog, reachable by `findChildren`/`findChild`. Confirmed
     `WA_DeleteOnClose` is set (`dialogs.py:127`) and that `reject()`
     (`dialogs.py:544`) calls `super().reject()`, which defers actual C++ deletion to
     the event loop (`QEvent::DeferredDelete`), so calling `dialog.confirmed()`
     immediately after a `.click()` that triggers `reject` is safe.
     `show_error`/`show_warning`/`show_success` all exist (`dialogs.py:590/670/726`).
   - `colors.py` — confirmed `BORDER`, `DANGER`, `TEXT_PRIMARY`, `TEXT_SECONDARY`,
     `WARNING_TEXT`, `BACKGROUND_HIGHLIGHT` all exist; confirmed `BACKGROUND_INPUT`,
     `BACKGROUND_WARNING`, `BACKGROUND_SECONDARY` do **not** exist (grep came back
     empty) — did not reach for them.
   - `mandate_copy.py` — confirmed `REVIEW_TITLE`, `REVIEW_SIGNER` (with the
     `{cuo_name}` token), `REVIEW_CAUTION`, `REVIEW_CONFIRM`, `REVIEW_BACK`,
     `IN_FLIGHT`, `FIELD_LABEL` all exist with the exact names/shapes the brief
     assumes.
   - `buttons.py` — confirmed `LocksmithButton(text, icon_path=None, parent=None)`
     and `LocksmithInvertedButton(text, parent=None)` exist and both expose the
     standard `QPushButton.clicked` signal.
   - **Ran a live probe** of `widget.findChild(object, name)` (the pattern
     `test_the_devctl_object_names_are_present` uses to look up a plain `QWidget` by
     name, not a `QPushButton`/`QLabel`) against a throwaway PySide6 script under
     `QT_QPA_PLATFORM=offscreen`. It resolved correctly and returned the concrete
     `QLabel` instance — confirming PySide6's `findChild` accepts `object` as a type
     filter and matches any `QObject` subclass. This is the exact kind of "Qt
     behaviour the brief assumes" the task called out to verify directly rather than
     reason about; it checked out.

2. **Wrote the failing test** exactly as specified in
   `tests/plugins/cuo/test_review_dialog.py`, then ran it and confirmed the expected
   failure:
   ```
   ModuleNotFoundError: No module named 'locksmith.plugins.cuo.review_dialog'
   ```

3. **Implemented** `src/locksmith/plugins/cuo/review_dialog.py` as specified — the
   `MandateReviewDialog(LocksmithDialog)` class with:
   - Signer line (`REVIEW_SIGNER.format(cuo_name=signer_name)`), objectName
     `mandateReviewDialog.signer`.
   - A canonical-payload summary block (`mandateReviewDialog.summary`) with rows for
     line of business, jurisdiction, coverages (joined with `, ` when a list), and an
     "In force" row built from the raw ISO `window_opens`/`window_closes` strings —
     never reformatted to MM/DD/YYYY.
   - A verbatim thesis block, `mandateReviewDialog.thesis`.
   - The caution block (`mandateReviewDialog.caution`) using `copy.REVIEW_CAUTION`
     verbatim, styled with `WARNING_TEXT` on `BACKGROUND_HIGHLIGHT` (no danger tint,
     no invented background token).
   - Back (`mandateReviewDialog.back`, `LocksmithInvertedButton`) wired to
     `self.reject`, and Confirm (`mandateReviewDialog.confirm`, `LocksmithButton`)
     wired to `_on_confirm`, which sets `_confirmed = True`, disables the button,
     swaps its text to `copy.IN_FLIGHT`, and emits the `confirm` signal — one-shot,
     so a second click cannot fire (the button is disabled) and cannot mint a
     duplicate credential.
   - `confirmed() -> bool` and a `fail(message)` convenience method (re-enables the
     primary and shows an error banner after a failed anchor attempt — not exercised
     by this task's tests, but part of the brief's spec and harmless: it adds no
     validation/business rule, just UI recovery).
   - `self.setObjectName("mandateReviewDialog")` on the dialog itself.
   - The dialog owns no rules: it only renders `payload.get(...)` values handed to
     it; no validation, no reformatting beyond the two joins the brief specifies
     (list-join for coverages, the "In force ... through ..., inclusive" string).

   One small deviation from the brief's literal code block: I dropped the unused
   `Qt` import from `PySide6.QtCore` (the brief's snippet imported `Qt, Signal` but
   never referenced `Qt` anywhere in the class body). No-op simplification, not a
   behaviour change — flagged here since I did not reproduce the brief verbatim on
   this one line.

4. **Ran the test again** — 7 passed.

5. **Ran the full `tests/plugins/cuo/` directory** to confirm no regressions against
   the pre-existing 65 tests.

6. **Committed** with the exact message the brief specified, staging only the two
   files for this task (the working tree had unrelated pre-existing modifications to
   `.superpowers/sdd/.gitignore`, an EGF OOBI `.cesr` file, and the plan doc, which
   were left untouched).

## Exact test commands and full output

Step 2 (verify failure):
```
$ cd /Users/seriouscoderone/code/locksmith && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_review_dialog.py -q --import-mode=importlib
==================================== ERRORS ====================================
___________ ERROR collecting tests/plugins/cuo/test_review_dialog.py ___________
ImportError while importing test module '/Users/seriouscoderone/code/locksmith/tests/plugins/cuo/test_review_dialog.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
tests/plugins/cuo/test_review_dialog.py:11: in <module>
    from locksmith.plugins.cuo.review_dialog import MandateReviewDialog
E   ModuleNotFoundError: No module named 'locksmith.plugins.cuo.review_dialog'
=========================== short test summary info ============================
ERROR tests/plugins/cuo/test_review_dialog.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.07s
```

Step 4 (verify pass, after implementation):
```
$ cd /Users/seriouscoderone/code/locksmith && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_review_dialog.py -q --import-mode=importlib
.......                                                                  [100%]
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/pysodium/__init__.py:299
  .../pysodium/__init__.py:299: DeprecationWarning: Due to '_pack_', the 'CryptoSignState' Structure will use memory layout compatible with MSVC (Windows). ...
    class CryptoSignState(ctypes.Structure):
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
7 passed, 1 warning in 0.34s
```

Full-package regression check:
```
$ cd /Users/seriouscoderone/code/locksmith && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
........................................................................ [100%]
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/pysodium/__init__.py:299
  ... (same pysodium DeprecationWarning)
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
72 passed, 1 warning in 0.82s
```
72 = the 65 pre-existing tests + the 7 new ones. No regressions.

The pysodium `DeprecationWarning` is pre-existing library noise unrelated to this
change (comes from `pysodium/__init__.py`, not from anything touched here).

## Commit

```
7e18ab3c feat(cuo): read-back dialog showing the canonical payload before signing
 2 files changed, 208 insertions(+)
 create mode 100644 src/locksmith/plugins/cuo/review_dialog.py
 create mode 100644 tests/plugins/cuo/test_review_dialog.py
```
Branch: `claude/cuo-mandate-form`.

## What was wrong or ambiguous in the brief, and how it was resolved

Nothing was wrong. Everything the brief asserted as "verified" — the
`LocksmithDialog` keyword signature, the six colour tokens (and the three absent
ones), the seven `mandate_copy` names, the button classes, `show_error` et al., and
the `WA_DeleteOnClose` behaviour — checked out exactly against the real source and a
live PySide6 probe. The only change from the brief's literal code was dropping the
unused `Qt` import, a no-op.

The brief's own docstring anticipates the one interesting design question up front
(why show canonical, ISO-formatted values instead of the raw typed input), and the
task instructions supplied the same rationale independently, so there was no
remaining ambiguity to resolve.

## Concerns for the reviewer

- `fail()` is implemented per the brief's spec but has no test coverage in this
  task (the brief's test list doesn't exercise it). It's presumably exercised by
  whichever later task wires this dialog to the actual anchor/sign call — worth
  confirming that wiring task does cover the retry path (disabled→re-enabled
  button, error banner) since this task cannot.
- The one-shot confirm behaviour (`setEnabled(False)` + label swap on first click)
  is enforced by the dialog UI only — it prevents a second *click*, not a second
  *call* to `_on_confirm` or a second `confirm.emit()` triggered some other way
  (e.g. a caller invoking `_on_confirm()` directly, or Enter-key activation racing
  the disable). Qt normally routes both mouse and default-button Enter-key
  activation through the same disabled-button guard, so this should be safe in
  practice, but the real backstop against a duplicate immutable mandate should
  still be server/anchor-side idempotency, not this dialog's button state — worth
  confirming that exists downstream, since per the brief this dialog is
  intentionally rules-free.
- Only manual/visual review confirms the "In force ... through ..., inclusive"
  row and the two-QLabel-per-row layout look right in the actual running app; the
  tests only check that the substrings appear, not layout/visual correctness.

---

## Addendum: code-review fixes (round 2)

The coordinator's review found one Critical and three Important defects. All four
are fixed, each with a new regression test, and the Critical and the confirm-guard
fix were both proven with a live mutation-and-revert (not just reasoned about).

### CRITICAL — thesis rendered as rich text

**Defect:** `thesis` (`review_dialog.py`) was left at Qt's default `AutoText`
format. A thesis containing anything that looks like markup (`<b>...</b>`, a bare
`<`, `&`) is auto-detected by Qt as rich text and rendered as HTML — tags vanish,
styling changes — while the *label's own `text()`* still returns the raw string
untouched. `text()`-only assertions (the whole original test suite) could not have
caught this; only geometry/rendering comparisons can.

**Fix:** `thesis.setTextFormat(Qt.TextFormat.PlainText)`, plus a comment recording
why (`review_dialog.py:88-94`).

**Direct proof, before writing the test**, measuring the exact reviewer-reported
mechanism on this codebase's actual stylesheet:
```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import Qt
app = QApplication.instance() or QApplication([])
thesis = 'Grow <b>teen-driver</b> share & focus on loss ratio <60% in Utah.'
style = 'color: #2D2F33; font-size: 15px; padding: 10px 12px; background: #DCDDE5; border-radius: 4px;'
autotext = QLabel(thesis); autotext.setWordWrap(True); autotext.setStyleSheet(style)
print('AutoText (no fix) sizeHint:', autotext.sizeHint())
plain = QLabel(thesis); plain.setWordWrap(True); plain.setStyleSheet(style); plain.setTextFormat(Qt.TextFormat.PlainText)
print('PlainText (fixed) sizeHint:', plain.sizeHint())
rich = QLabel(thesis); rich.setWordWrap(True); rich.setStyleSheet(style); rich.setTextFormat(Qt.TextFormat.RichText)
print('RichText sizeHint:', rich.sizeHint())
"
AutoText (no fix) sizeHint: PySide6.QtCore.QSize(156, 74)
PlainText (fixed) sizeHint: PySide6.QtCore.QSize(359, 56)
RichText sizeHint: PySide6.QtCore.QSize(156, 74)
```
`AutoText` matches `RichText` exactly (156×74) and disagrees with `PlainText`
(359×56) — confirming the exposure is real on this exact string/stylesheet, in
this exact codebase, not hypothetical.

**New test:** `test_thesis_with_markup_renders_literally_not_as_richtext` — builds
`PlainText`/`RichText` twins from the *actual* label's own `styleSheet()`, asserts
the dialog's thesis label agrees with the `PlainText` twin's `sizeHint()`, and
separately asserts the `PlainText`/`RichText` twins disagree with each other (proof
the test can actually discriminate for this string).

**Mutation proof (regression-sensitivity):** removed line 94
(`thesis.setTextFormat(Qt.TextFormat.PlainText)`), cleared
`src/locksmith/plugins/cuo/__pycache__` and `tests/plugins/cuo/__pycache__`, reran:
```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_review_dialog.py::test_thesis_with_markup_renders_literally_not_as_richtext -v --import-mode=importlib
...
E       assert PySide6.QtCore.QSize(156, 74) == PySide6.QtCore.QSize(359, 56)
FAILED tests/plugins/cuo/test_review_dialog.py::test_thesis_with_markup_renders_literally_not_as_richtext
1 failed, 1 warning in 0.19s
```
Failed exactly as expected — the mutated label's sizeHint (156, 74) is the
`RichText` value, not the `PlainText` one. Restored the file from a pre-mutation
copy, cleared `__pycache__` again, confirmed `diff` against the backup was empty,
then reran the full `tests/plugins/cuo/` suite green (76 passed) before proceeding.

### IMPORTANT — same exposure on the generic value row

**Defect:** `_row()`'s `shown` `QLabel` (line 34, used for line of business,
jurisdiction, coverages, and the "In force" row) had the identical `AutoText`
exposure. Masked today because upstream schema patterns for those fields exclude
`<`/`>`, but this module owns no rules and must not depend on that holding.

**Fix:** `shown.setTextFormat(Qt.TextFormat.PlainText)` with a comment stating
explicitly that this is defensive, not reactive to an observed bug in this field
today (`review_dialog.py:36-40`).

**New test:**
`test_row_values_render_literally_even_if_upstream_patterns_ever_allow_markup` —
same `PlainText`/`RichText`-twin `sizeHint()` technique, applied to a row value
(`line_of_business="<b>auto</b>"`) rather than the thesis.

### IMPORTANT — two hardcoded strings

**Defect:** `"In force"` and `"Thesis, published in full"` were inline literals in
`review_dialog.py` instead of living in `mandate_copy`.

**Fix:** added `REVIEW_IN_FORCE_LABEL = "In force"` and
`REVIEW_THESIS_LABEL = "Thesis, published in full"` to
`src/locksmith/plugins/cuo/mandate_copy.py` (next to the other `REVIEW_*`
constants); `review_dialog.py` now references `copy.REVIEW_IN_FORCE_LABEL` and
`copy.REVIEW_THESIS_LABEL`. Neither string has an interpolation token, so
`TOKENS`/`test_tokens_is_exactly_the_set_of_tokens_actually_used` needed no
change. Confirmed the full `mandate_copy` policy suite still passes with the two
new module-level strings in scope (they're picked up automatically by
`_all_strings()` since they're not underscore-prefixed):
```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_mandate_copy.py -q --import-mode=importlib
...............                                                          [100%]
15 passed in 0.08s
```

### IMPORTANT — one-shot confirm had no regression test

**Defect:** the existing test only fired one click and checked its outcome; the
reviewer showed that deleting `self._confirm_button.setEnabled(False)` from
`_on_confirm` left all 72 prior tests green, meaning the actual anti-duplicate
mechanism was untested. `fail()` also had zero test coverage.

**New tests (both added verbatim/near-verbatim to spec):**
- `test_a_second_click_cannot_emit_confirm_again` — fires two real `button.click()`
  calls (not a second call to the private handler), asserts `confirm` fired
  exactly once, the button is disabled, and its text is `copy.IN_FLIGHT`.
- `test_fail_reenables_the_primary_for_a_retry` — after one confirm click then
  `dialog.fail("boom")`, asserts `confirmed()` is back to `False`, the button is
  re-enabled, and its text is back to `copy.REVIEW_CONFIRM`.

**Mutation proof (regression-sensitivity):** removed
`self._confirm_button.setEnabled(False)` from `_on_confirm`, cleared both
`__pycache__` directories, reran the new second-click test:
```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/test_review_dialog.py::test_a_second_click_cannot_emit_confirm_again -v --import-mode=importlib
...
E       assert [1, 1] == [1]
FAILED tests/plugins/cuo/test_review_dialog.py::test_a_second_click_cannot_emit_confirm_again
1 failed, 1 warning in 0.21s
```
Failed exactly as expected — `confirm` fired twice with the guard removed. Diffed
the mutated file against the pre-mutation backup (`diff` showed only the one
deleted line), restored it, cleared `__pycache__` again, and reran the full
`tests/plugins/cuo/` suite green (76 passed) before committing.

### Final verification

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
........................................................................ [ 94%]
....                                                                     [100%]
76 passed, 1 warning in 0.77s
```
76 = 72 previously-passing + 4 new tests (thesis-plaintext, row-plaintext,
second-click, fail-retry). No regressions.

### Coordinator's two deferred/settled points — acknowledged

- One-shot confirm being UI-only, with real duplicate-mandate protection
  belonging to anchor-side idempotency in `keri_serviceaid` (out of this plan's
  scope) — recorded as a deferred risk by the coordinator, not something fixed
  here. Agreed; no action taken in this repo.
- `fail()` untested — now covered by `test_fail_reenables_the_primary_for_a_retry`
  as requested.

### Commit (round 2)

```
909ce6b4 fix(cuo): render thesis and row values as plain text, not rich text
 3 files changed, 112 insertions(+), 4 deletions(-)
```
Branch: `claude/cuo-mandate-form`. Files: `src/locksmith/plugins/cuo/review_dialog.py`,
`src/locksmith/plugins/cuo/mandate_copy.py`, `tests/plugins/cuo/test_review_dialog.py`.

### Concerns for the reviewer (round 2)

- The `sizeHint()`-comparison technique is robust for this codebase's fonts/
  stylesheet but is inherently a rendering-behavior proxy, not a direct assertion
  on "did this get interpreted as HTML" — it's what PySide6 exposes, and it did
  discriminate correctly in both mutation tests, but a future Qt/font change that
  altered `PlainText` and `RichText` layout metrics to coincidentally match could
  in principle produce a false green. No cheaper reliable signal was found;
  flagging for awareness rather than as an open defect.
- The two new `mandate_copy` constants sit next to the other `REVIEW_*` strings
  but were not run through the "three independent drafts judged against brand
  voice pillars" process the module's docstring describes for the rest of its
  copy — they're short structural labels ("In force", "Thesis, published in
  full") rather than reader-facing prose, but worth a second look if brand-voice
  review is meant to cover every string unconditionally.
