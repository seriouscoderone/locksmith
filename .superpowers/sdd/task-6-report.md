# Task 6 report — rebuild the form page

**Status: DONE_WITH_CONCERNS.** The form is built, all six controls come from the
schema, the read-back gates the anchor, and every gate is green. Three things need
the reviewer's eye: two brief defects I corrected rather than transcribed, and one
copy gap the copy module does not cover.

(No stale content was overwritten — `.superpowers/sdd/task-6-report.md` did not
exist. Note `.superpowers/sdd/.gitignore` is `*`, so this report is not committed.)

**Commits** (branch `claude/cuo-mandate-form`, three rather than the brief's one so
each finding is revertible on its own):

| SHA | what |
|---|---|
| `dbc14e6c` | feat(cuo): rebuild the mandate form on the schema, with review before anchor |
| `99574b01` | fix(cuo): set_field on coverages must replace, and the roles pages need their brand |
| `378d8ca1` | fix(cuo): the help text was painted over the control above it |

Files: `src/locksmith/plugins/cuo/page.py` (rewritten, 1030 lines),
`tests/plugins/cuo/test_page_form.py` (new, 22 tests),
`tests/plugins/roles/conftest.py` (new, 1 fixture — see Finding 5).

---

## 1. Test command and output

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
........................................................................ [ 73%]
..........................                                               [100%]
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/pysodium/__init__.py:299
  ...DeprecationWarning: Due to '_pack_', the 'CryptoSignState' Structure will use
  memory layout compatible with MSVC (Windows)...
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
98 passed, 1 warning in 2.07s
```

76 pre-existing (Tasks 1-5) + 22 new. The single warning is pre-existing and comes
from `pysodium`, not this work.

Wider runs, because this task touched a page other suites construct:

```
$ ... -m pytest tests/plugins/ -q --import-mode=importlib
254 passed, 1 skipped, 1 warning in 10.90s          # was 251 passed + 2 failed + 1 skipped

$ ... -m pytest tests/ui/ tests/unit/ tests/test_undefined_names.py -q --import-mode=importlib
535 passed, 2 skipped, 1 warning in 32.24s

$ .venv/bin/ruff check --select F,E9 <the three files>
All checks passed!
```

Task 7's two guards do not exist yet, so I ran their logic by hand against the real
bundle: **zero** hits for `^US-[A-Z]{2}$`, `^[A-Z0-9][A-Z0-9-]*$`, and every
`line_of_business` enum member across `src/locksmith/plugins/cuo/*.py`. See
Finding 3 — my first draft failed that scan.

The whole suite was never run (pre-existing collection errors, per the brief).

---

## 2. What I implemented

`CuoMandatePage(LocksmithFormPage)`, `copy.H1` as the title, `copy.PAGE_INTRO` as
two wrapped paragraphs, one bounded 640px column, and per field a vertical group:
**label above** (with `" *"` and a tooltip when required), control, help, error
label hidden until it has text. No `QFormLayout` anywhere.

**Controls come from constraints, never from field names.** `enum` → `QComboBox`;
`type: array` → `LocksmithTextListWidget`; `fmt == "date"` → `MandateDateField`;
a string the schema constrains by neither pattern, enum nor format → 3-row
`LocksmithPlainTextEdit`; otherwise `LocksmithLineEdit`. The brief said
`name == "thesis"` for the prose box in the same breath as "never by field name";
I used the constraint shape, which resolves to `thesis` today and survives a rename.

Every control is a `_Control` record of callables (`read` / `write` / `clear` /
`paint` / `flush` / `changed`), so `build_payload`, `set_field`, `blur_field`,
`reset_form` and the error painting are each written **once**, generically. This is
deliberate given `feedback_checks_stop_tracking_the_model`: a new control type is
one record to fill, not five branch lists to remember.

**Timing.** `submit()` sets `_submitted`, validates via `validate_payload` only,
paints every field's messages, shows `copy.error_summary(len(errors))` in the base
banner, focuses the first invalid control and scrolls it into view. `blur_field`
re-runs the same validator and keeps only that field's messages, and returns
immediately when `_submitted` is False. An edit clears that field's error and the
declared banner. The page contains no rule of its own — no date comparison, no
pattern, no enum.

**Nothing is signed before the read-back.** `submit()` opens
`MandateReviewDialog(payload, signer_name=…)`, stores it as `self.review_dialog`
and connects `confirm` once. `_confirm_review` holds a one-shot `_anchoring` guard,
enters the in-flight state (the primary disabled, text `copy.IN_FLIGHT` — the one
reason it ever disables) and calls `_anchor`. Success → `_show_declared` with the
**full** SAID and a copy button; failure → `_fail_anchor` closes the modal,
re-arms the primary, keeps the typed values and reports why (design §4.3).

**Preserved verbatim:** `_cuo_hab`, `_ensure_mandate_schema_pinned`, and the
`ServiceaidIssueDoer` machinery including the one-shot `doer_event` listener keyed
to `"IssueCredentialDoer"`. The only change is that the machinery now lives in
`_anchor` (called from the confirmed read-back) instead of `submit`, and its
failure path calls `_fail_anchor` instead of `_show_error`.

`build_payload()` returns canonical values in `copy.FIELD_ORDER` key order — the
same order the old `_build_payload` produced, so the ACDC attribute serialization
is unchanged.

---

## 3. Findings — where the brief was wrong, ambiguous, or silent

### Finding 1 (**Critical**, brief defect): the combo prompt makes `count()` 9, and the test demands 8

Step 3 says `insertItem(0, copy.FIELD_PLACEHOLDER[name])` "as a non-selectable
prompt". The enum has 8 members (Task 1 pins that), so an inserted prompt gives
`count() == 9` and
`test_the_line_of_business_control_is_a_combo_from_the_schema` fails on
`assert combo.count() == 8`. Measured on real PySide6 6.10.3:

```
P1  setPlaceholderText + addItems(8):  count=8  idx=-1  text=''      <- what I did
P1b addItems(8) + insertItem(0,...):   count=9                        <- the brief
```

**Resolved:** `setPlaceholderText()` before `addItems()`. Qt then leaves
`currentIndex` at -1 by itself (probed, not assumed), the prompt shows, it is not
selectable, and the control claims exactly as many options as the schema has.

### Finding 2 (**Critical**, brief defect): the one-shot guard cannot live in the dialog

Step 3: "The one-shot guard lives in the dialog (`_on_confirm` disables its own
primary), and Task 6's test asserts it." The dialog's guard is a *disabled button*,
which only stops a second **click** — and Task 5 pinned exactly that with a real
double click. Task 6's test calls `dialog._on_confirm()` twice **directly**, which
re-emits `confirm` because `_on_confirm` has no re-entry check. Left as briefed, the
test fails with `len(anchored) == 2` and the real hazard (a duplicate immutable
mandate) is unguarded on any path that is not a mouse click.

**Resolved:** the guard is on the page, at the point where the irreversible thing
happens — `_confirm_review` returns early while `_anchoring`. Task 5's dialog is
untouched. `_fail_anchor` and `_show_declared` re-arm it so a retry works.

### Finding 3 (**High**, my own defect, caught before Task 7 could): comments count as source

My first draft explained `_pattern_prefix` by quoting `^US-[A-Z]{2}$`, and
`write_combo` by saying `"Auto"` and `"auto"` both select. Task 7's guards
`read_text()` whole files, so **both** would have failed — a comment is source to a
grep. Rewritten to name the constraint without quoting its value, and re-scanned
clean. Worth carrying into Task 7's own report: the guard's discriminating power
comes from reading whole files, and that cuts both ways.

### Finding 4 (**High**, brief defect in the test file): the fixture destroys the page before teardown

The given fixture ends `return p`, so the only reference to `parent` dies with the
fixture frame; the parent is collected and takes the child page's C++ object with
it. Every one of the 11 tests then errors in pytest-qt's teardown:

```
11 failed, 11 errors      # RuntimeError: Internal C++ object (CuoMandatePage) already deleted
```

**Resolved:** `yield p` (the generator frame holds `parent` through teardown) →
`11 failed, 0 errors` before the implementation, all green after. One-word change,
documented in the fixture so nobody "tidies" it back.

### Finding 5 (**High**, consequence the brief did not mention): two roles tests built the page with no brand

The page reads the EGF while constructing, and refuses to open without it
(`schema_source`'s fails-LOUD rule). Two pre-existing tests build every bundled
role page with no brand active and started failing:

* `tests/plugins/roles/test_role_plugins.py::test_page_key_equals_plugin_id_and_menu_label[CuoPlugin-cuo-Underwriting]`
* `tests/plugins/roles/test_surface_reactivation.py::test_a_withdrawn_surface_can_be_revealed_again[cuo]`

I kept the loud failure (it is the design's own words, and `RevealBundledSurface.activate`
does not swallow it) and added `tests/plugins/roles/conftest.py`, an autouse fixture
activating the usurance brand — a true precondition for brand-bundled role plugins,
reusing `tests/plugins/cuo/conftest.py`'s bundle builder (cross-conftest import is
already this repo's pattern). `tests/plugins/` went from 251 passed / 2 failed to
254 passed.

### Finding 6 (**High**, my own defect, found by hand-driving): `set_field("coverages", …)` appended

`write` routed through the append path, so a second `set_field` merged into the
first and `reset_form()` cleared nothing at all (measured: `['BI']` survived a
cancel). Split into `_write_tokens` (replace — the write and clear paths) and
`_commit_tokens` (append — the typing path). Regression test added.

### Finding 7 (**High**, the brief asked me to verify this): a comma does **not** commit a token

`LocksmithTextListWidget` commits on `returnPressed` or the add button and contains
no comma handling whatsoever — so `type "BI,PD"`, which Task 8's helper depends on,
would have left one uncommitted string and published nothing. Worse, devctl's `type`
on the container fails outright: it looks for `.line_edit` / `.text_edit` /
`.plain_text_edit` or `setText`, and the container has none of them.

**Resolved, inside `plugins/cuo/` only** (Global Constraint 5 forbids touching the
toolkit):

1. the objectName `cuoMandatePage.coverages` rides on the widget's **input**
   (`text_input`), which devctl unwraps via `.line_edit`; the container is
   `…coveragesList`;
2. a `textChanged` hook commits each comma-terminated token live (`BI,PD` → chip
   `BI`, `PD` still being typed);
3. `read()` includes whatever is still in the input box, split on commas, so a
   token the CUO typed is never silently dropped from a permanent record; and
4. `submit()` flushes the pending token into a chip first, so the screen and the
   payload agree.

Driving the whole form exactly as Task 8's helper will (`select` + four `type`s, in
process, through devctl's own resolution logic) produced:

```
typed cuoMandatePage.jurisdiction -> LocksmithLineEdit
typed cuoMandatePage.coverages    -> QLineEdit
typed cuoMandatePage.windowOpens  -> QLineEdit
typed cuoMandatePage.windowCloses -> QLineEdit
typed cuoMandatePage.thesis       -> LocksmithPlainTextEdit
payload == {'line_of_business': 'auto', 'jurisdiction': 'US-UT',
            'coverages': ['BI', 'PD'], 'window_opens': '2027-01-01',
            'window_closes': '2027-12-31', 'thesis': 'Rate adequacy restoration.'}
```

**This also closes Task 8's flagged risk about `QDateEdit`.** `QDateEdit` has no
`setText`, so `.windowOpens` / `.windowCloses` name the QDateEdit's **internal
QLineEdit** — writing that field's text really does move the date, and it fires
`dateChanged` (probed: `le.setText("01/01/2027")` → `iso_value() == '2027-01-01'`,
`changed` emitted). Task 8 needs no devctl change and no `set_iso` op; its helper
as written in the plan works. The wrapper is `…windowOpensField` if it is ever
needed.

### Finding 8 (**High**, my own defect, found by LOOKING at the render): help text painted over its control

98 green tests, and the form was visibly broken. A word-wrapped `QLabel` reports a
**one-line minimum height** however many lines it will paint, so the layout allotted
each field group ~40px less than it needed, and Qt honoured each control's own
`setMinimumHeight(50)` anyway — the control overlapped the help beneath it. Measured
across window sizes, with and without errors, before the fix:

```
1100x980  pump=0ms    errors=False  worst_squeeze=43px  overlaps=[jurisdiction 14, thesis 37]
1100x980  pump=500ms  errors=False  worst_squeeze=43px  overlaps=[jurisdiction 14, thesis 37]
1280x700  pump=50ms   errors=True   worst_squeeze=43px  overlaps=[jurisdiction 14, thesis 37, thesis 1]
1280x1024 pump=50ms   errors=True   worst_squeeze=43px  overlaps=[jurisdiction 14, thesis 37, thesis 1]
```
and after: `worst_squeeze=0px overlaps=[]` in all four. Persistent, not a transient
un-settled layout — I checked that specifically by pumping 500ms.

Fixed by `_fit(label)` (copy `sizeHint().height()` into the **minimum** height, on
every text change since error labels grow) plus explicit widths on the column, the
groups and every wrapping label so `sizeHint` is deterministic. That also made the
"bounded 640px column" of design §3.1 actually 640 — it was 546, varying with the
longest label.

While in there, the window pair now shares one row with its help written **once**
beneath it: `copy` gives both dates the same sentence, and printing it twice side by
side reads as a mistake.

### Smaller resolutions of brief silence

* **`US-` prefix.** Step 3 says "`US-`-prefixed when absent", i.e. it asks for a
  fragment of `^US-[A-Z]{2}$` in Python. Task 7's guard would not catch it, but the
  design principle would. I derive the prefix and the case-folding from the field's
  own `pattern` (`_pattern_prefix` / `_pattern_case`), which also gives coverage
  codes their upper-casing from the same code path. The enum control needs no
  canonicalisation at all — a dropdown can only emit a member verbatim, which is
  the point of it being a dropdown.
* **`show_declared` vs `_show_declared`.** The brief names the public method, but
  `tests/integration/roles/_bootstrap/sitecustomize.py:315` wraps
  `CuoMandatePage._show_declared` at class level to export the delivery artifact, and
  I may not edit that file. `show_declared` is therefore a thin front door onto
  `_show_declared`, so every declaration still passes through the wrapped method.
  Renaming it outright would have broken the four-window arc with an
  `AttributeError` at import, far from the change.
* **`declaredBanner` is NOT the base page's success banner.** The base collapses it
  to zero height without hiding, so `isVisible()` stays true — and
  `tests/integration/roles/conftest.py:882` waits on
  `cuoMandatePage.declaredBanner condition=visible` to know the issuance finished.
  Using the base banner would have made that wait a no-op. It is a dedicated label,
  hidden until declared, mirroring `ProductDesignerPage.bundleSaid`'s documented
  reasoning. `errorBanner` **is** the base's `error_label`, renamed — nothing waits
  on its visibility.
* **Cancel.** Design §3.1 asks for it in the footer; the brief's Step 3 never
  mentions it and nothing defines what it does. I made it clear the form, its
  errors and the declared banner, and forget the submit attempt. Flagged below.
* **Error painting survives focus.** `LocksmithLineEdit` / `LocksmithPlainTextEdit`
  / `FloatingLabelLineEdit` rebuild their entire stylesheet on focus in and out, so
  a red border set with `setStyleSheet` is erased by the next click. I set the
  `_border_color` / `_focused_border_color` they read and ask them to repaint.
* **The unrenderable-field guard.** If the schema grows a field `FIELD_ORDER` does
  not carry, the page raises rather than silently dropping it from every payload.
* **`submit()` refuses while an anchor is in flight**, mirroring the one reason the
  primary is disabled.

---

## 4. Verification beyond the suite

A 30-check harness drove the built page (devctl-shaped typing, real focus changes,
a fake registry, the failure path, the objectName contract) — **all pass**. The five
most valuable checks were folded into the committed suite as regression tests, and
each was confirmed to go **red** when its behaviour is reverted:

| gate | corrupted | result |
|---|---|---|
| comma commits a token | `textChanged` hook disconnected | FAILED |
| invalid border survives focus | paint via `setStyleSheet` | FAILED |
| focus-out drives the blur check | event filter not installed | FAILED |
| declared banner hidden until declared | row always visible | FAILED |
| overlap gate reads this vault's mandates | `existing_mandates()` not passed | FAILED |
| no help painted over its control | `_fit` removed | FAILED |
| the column is 640 wide | all three width pins removed | FAILED |

One caution for the reviewer's own method: my first discrimination run for the
layout gate showed red for the wrong reason (a missing `QVBoxLayout` import), and
the first version of that gate was vacuous because **the `page` fixture's parent
has no layout — the page never gets a real geometry through it**. Any
position/size assertion written on that fixture is meaningless; the gate builds its
own shell.

I also read the rendered page (empty, errored, filled, review modal, declared) —
`form-*.png` in this session's scratchpad. One near-miss worth recording: I read a
downscaled screenshot as showing jurisdiction's red border missing, then sampled
the pixels and found `#dc2626` exactly where it should be. Sample, do not squint.

---

## 5. Concerns for the reviewer

1. **The declared/failed states have no ratified copy.** `mandate_copy` covers every
   field, error and button but has no string for "Mandate declared. <SAID>" or for
   the anchor-failure banner, so those two strings are literals in `page.py` — the
   one place this page holds user-visible text that the copy module does not own. A
   Task 3 follow-up should adopt them.
2. **`REVIEW_SIGNER`'s `{cuo_name}` has no source.** The `cuo_role` credential
   carries protocol fields only (`d`, `i`, `dt`) — there is no personal name
   anywhere in the ecosystem. I fall back to the identifier's local alias, then its
   prefix, then `"this identifier"`, so the live demo will read "Signing as cuo,
   Chief Underwriting Officer, …". Honest, but the copy was written expecting a
   human name.
3. **The read-back shows raw enum tokens** (`workers_compensation`). The combo's item
   text is the enum value verbatim, which keeps `select value="auto"` working for
   Task 8 and keeps the payload trivially honest, but a CUO reads a snake_case
   token. Humanising the labels means putting the value in a data role and changing
   Task 8's `select` value — a deliberate trade I did not make unilaterally.
4. **Cancel's behaviour is my invention** (clear the form). The spec asks only that
   the button exist. If the owner wants it to navigate away or to be dropped, it is
   one method.
5. **`blur_field` reads the credential registry on every focus change**
   (`existing_mandates()` inside the validator call). Correct and cheap on LMDB, but
   it is a disk read per blur; a cache with an invalidation story would be premature
   now and easy later.
6. **A duplicate coverage typed with a comma is silently de-duplicated** by the
   widget's own duplicate prevention, so `COVERAGE_DUPLICATE` is only reachable via
   the still-being-typed token. The validator's rule stays correct for payloads from
   any source; the UI just cannot usually produce that state.
7. **Task 8 needs no devctl change** (Finding 7). Its plan's step 3 hedge about
   `QDateEdit` can be resolved to "works", but the helper must use
   `cuoMandatePage.windowOpens` (the internal line edit) exactly as written, and
   must not target the `…Field` wrapper.

---

# Round two — the review's 12 items

**Status: DONE_WITH_CONCERNS.** All twelve addressed. Four items were live defects
I reproduced before fixing; one item's fix uncovered a *thirteenth* defect (the
scroll to the first invalid field had never worked at all); one item's prescribed
mechanics did not work when measured and I used a different one; and one item's
"hole" turned out to be redundant source rather than a missing test, so I deleted
the redundancy.

**Commits** (on top of `378d8ca1`), grouped so each area reverts alone:

| SHA | scope |
|---|---|
| `bc10182b` | `date_field.py` + its tests — item 2 |
| `7e837fc3` | `review_dialog.py` + its tests — items 3, 4, 6 |
| `2769b2e0` | `page.py`, `mandate_copy.py`, `test_page_form.py` — items 1, 5, 7-12 and the mutation holes |

## Test output

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
137 passed, 1 warning in 3.44s
```

136 → 137 after the last gate was parametrized. Was 98 at the end of round one:
**+39 tests**. Wider runs, because this round edited three shared-ish modules:

```
tests/plugins/                                         293 passed, 1 skipped
tests/ui/ tests/unit/ test_undefined_names test_text_list_widget   537 passed, 2 skipped
ruff --select F,E9 (cuo src + tests)   only the pre-existing unused `re` in Task 3's test_mandate_copy.py
```

## Reproduced first, as instructed

| item | measured BEFORE the fix | measured AFTER |
|---|---|---|
| 2 date typing | focus lands on `_SentinelGuardedDateEdit` (the line edit's focus proxy); keying `03152028` → line edit `MM/DD/YYYY3152028`, `iso_value()` `""` | line edit `03/15/2028`, `iso_value()` `2028-03-15`; a field that already held a date gives the same |
| 3 one Enter signs | `confirm.isDefault()` True, `hasFocus()` True, `dialog.focusWidget()` is the primary; one `Key_Return` → `anchored == 1` | confirm `isDefault()` False / `autoDefault()` False, focus is on back, one `Key_Return` → `anchored == 0` |
| 4 poisoned dialogs | after Keep editing, `_current_dialog` still the destroyed dialog; the next `open()` raised `RuntimeError: Internal C++ object (MandateReviewDialog) already deleted` | `_current_dialog is None`; the second read-back opens and is visible |
| 5 dangling handle | `page.review_dialog is None` False while `Shiboken.isValid` False | `is None` True, and a second submit opens a fresh one |
| 1 read-back ≠ anchored | a divergent dict handed to the dialog: **all 98 tests green** | the new gate fails on it (mutation 1 below) |
| 7 name on the wrapper | `.windowOpens` moved onto the `MandateDateField`: `findChild(QWidget, …)` still resolves, **all 98 green** | the new gate fails on it (mutation 2 below) |
| 6 back enabled mid-flight | `back.isEnabled()` True after confirm | False, and `fail()` re-arms it |

## Where I did not follow the instruction, and why

**Item 2's prescribed mechanics do not work.** The brief said "seed
`QDate.currentDate()`, clear the line edit, then delegate". Measured on PySide6
6.10.3, `03152028` into an empty field:

```
seed only                      -> 2026-08-08 (today; the keystrokes vanished)
seed + line.clear()            -> 2026-08-08 (same)
seed + setSelectedSection(0)   -> 2028-03-15  <- and the non-empty CONTROL gives exactly this
non-empty control, no select   -> 2027-05-05 (unchanged; selection is what admits typing)
```
The gate is `QDateTimeEdit`'s validator, not the placeholder text: an insertion is
only valid when a section is selected, which is what focus-in does to a filled
field. So the fix seeds **and** selects the first section. Both halves are
load-bearing and the docstring says so, with the numbers.

**Item 18/O5 was not a test hole.** `column.setFixedWidth(_COLUMN_WIDTH)` and the
column's `Fixed` size policy were both measured **inert** once `_fit` made the
labels' minimums honest: removing either, or both, changed nothing — zero squeeze,
zero overlap, identical widths, 136/136 green, at five window sizes. A mutation of
dead code cannot be killed by a test, so I deleted the two lines instead of
inventing an assertion about which setter was called. The outcome stays pinned:
`test_the_column_keeps_its_measure_in_a_narrow_window` (500px window) and the
geometry gate, which goes red when the *group* widths are removed (the column
collapses to 315px).

**Two mutations remain, and they are equivalent, not survivors.**
`setFixedWidth` → `setMaximumWidth` on the groups and on the wrapping labels is
undetectable because `QLabel.sizeHint()` clamps to `maximumWidth` when `wordWrap`
is set, so the wrap measurement is identical either way. I checked this was not the
"640 == QWidget's default width" coincidence by parametrizing the geometry gate at
a **480** column measure too; both mutations still survive at 480, which is what
equivalence looks like. `setFixedWidth` stays because it also pins the minimum.

## Item 8: what remains, precisely

The page's own dedupe is gone — it hands `set_items` every token, pinned by
`test_the_page_does_not_de_duplicate_coverage_tokens`. But
`COVERAGE_DUPLICATE` is still not reachable from this form, and removing my filter
did not change that: `LocksmithTextListWidget` keys `_items` by text, so
`set_items(["BI", "BI"])` yields one chip, and `submit()` flushes the pending token
through the same widget. Making it reachable means either the page keeping its own
token list (duplicated state, and the screen would stop matching the payload) or
changing the toolkit widget, which is outside this plan. Recorded as a follow-up;
the validator keeps the rule for payloads from any other source.

## Mutation testing: 21 run, 19 killed

Every mutation applied to `src/`, `__pycache__` cleared, `tests/plugins/cuo/` run
with `-p no:randomly`, then reverted.

| # | mutation | killed by |
|---|---|---|
| 1 | divergent payload handed to the read-back | `test_the_read_back_shows_the_payload_that_gets_anchored` |
| 2 | driven name moved onto the date wrapper | `test_every_driven_name_is_on_a_widget_devctl_can_write_to` |
| 3 | a digit no longer leaves the empty state | 3 date-typing tests |
| 4 | the primary is default + focused again | `test_the_irreversible_primary_is_neither_the_default_nor_focused` |
| 5 | Keep editing routes to `reject()` | `test_keep_editing_does_not_poison_every_later_dialog` |
| 6 | Keep editing stays enabled mid-flight | `test_keep_editing_is_refused_once_signing_has_started` |
| 7 | the dialog handle is never dropped | `test_keep_editing_drops_the_dialog_handle` |
| 8 | the page de-duplicates tokens again | `test_the_page_does_not_de_duplicate_coverage_tokens` |
| 9 | blur reports required errors again | `test_blurring_an_emptied_field_does_not_accuse_the_cuo` |
| 10 | `clear_error` keeps its text | `test_the_error_banner_stops_offering_a_stale_message` |
| 11 | the reveal is not deferred | `test_a_failed_submit_focuses_and_scrolls_to_the_first_invalid_field` |
| 12 | the field label placed below its error | `test_no_help_text_is_painted_over_its_own_control` |
| 13 | error labels always visible | `test_an_error_label_is_hidden_until_it_has_something_to_say` |
| 14 | the date control's `changed` unwired | `test_editing_any_control_clears_its_error_and_the_stale_said[window_opens]` |
| 15 | the combo's `paint` a no-op | `test_every_control_is_marked_when_its_field_is_wrong[line_of_business]` |
| 16 | the date control's `clear` a no-op | `test_cancel_empties_every_control` |
| 17 | `schema.order` drives the form | `test_field_order_not_the_schema_decides_the_sequence` |
| 18 | group width capped, not fixed | **equivalent** (see above) |
| 18b | label width capped, not fixed | **equivalent** (see above) |
| 18c | label minimum not fitted to its text | `test_no_help_text_is_painted_over_its_own_control` |
| 19 | submit allowed mid-flight | `test_submit_is_refused_while_an_anchor_is_in_flight` |
| 20 | the primary disables while invalid | `test_the_primary_stays_enabled_through_editing_and_a_failed_submit` |

Two process notes, since a red run is only evidence if it is red for the right
reason. Mutation 5 first showed up as **two teardown ERRORS rather than a clean
FAIL**: with `reject()` restored, an earlier test's Return keystroke destroyed a
dialog that `qtbot` still held, and pytest's "previous item was not torn down
properly" pre-empted my gate before it ran. Run in isolation the gate failed on
exactly the right assertion. Fixed by having that earlier test own its dialog
through a host widget instead of registering the dialog itself — mutation 5 now
dies as `1 failed`. And mutation 12 initially survived because I had *planned* the
labels-above assertion and not written it; it is now asserted on position
(`heading.y() + heading.height() <= control.y()`), not on the order things were
added.

## The thirteenth defect, found by fixing item 7's hole

`ux-patterns.md:192`'s scroll had **never worked**. `ensureWidgetVisible` ran
inside `submit()`, before the error labels that just appeared had grown the column,
so it scrolled a viewport that still believed everything fitted: measured, the
first invalid field sat at **y=648 in a 590px viewport**. Deferred by one
event-loop tick (`QTimer.singleShot(0, …)`, guarded against the page being torn
down first), and pinned by a test that leaves only the LAST field invalid at the
window's own minimum height, so the scroll is load-bearing rather than incidental.

## Concerns for the reviewer

1. **The `LocksmithDialog` base-class fix is still owed** (item 4). `reject()` and
   `accept()` bypass `closeEvent`, and `closeEvent` is the only place
   `_current_dialog` is cleared, so *any* dialog in the app that rejects leaves the
   same dangling class attribute. My change routes this one dialog around it.
   The base-class fix is to clear the pointer in `reject`/`accept` too (or track it
   with `destroyed`), plus `showEvent` should tolerate an invalid pointer. Two
   lines in a file shared by the whole app, and outside this plan.
2. **A stray digit now seeds today's date.** Typing `03` and tabbing away leaves
   `03/<today's day>/<today's year>` — a date the CUO did not fully choose. It is
   inherent to section-based date editing (any seed has it), and the read-back
   showing ISO is the mitigation. Worth an owner ruling if partially-typed dates
   are considered a record risk.
3. **`Return` now activates "Keep editing"** — the safe default, but it means Enter
   closes the modal rather than doing nothing. That is Qt's default-button
   behaviour; the alternative is no default button at all, which loses keyboard
   dismissal. Called out because it is a behaviour change a reviewer might not
   expect from "make the primary not default".
4. **`COVERAGE_DUPLICATE` is unreachable from this form** (item 8 above), one layer
   below the page.
5. **The `page` fixture still lays out nothing**, so geometry-shaped tests must
   build their own shell. Three of the new tests do; anyone adding a fourth should
   know why.
