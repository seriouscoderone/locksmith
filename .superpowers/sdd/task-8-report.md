# Task 8 report — rewrite the integration helper

Scope actually executed: brief Steps 1-3 and 5 only. Step 4 (the four-window
arc, `test_admin_grants_to_hoas_via_ui.py::test_the_admin_issues_and_grants_both_roles_live`)
was **not run**, per the owner's explicit scope limit (they are running it
themselves, visibly, afterward).

## What changed

### `tests/integration/roles/conftest.py` — `submit_mandate_form_via_ui`

Rewrote the body per the brief's Step 2, with one addition (see "Deviation"
below). Verified against the actual source before writing anything:

- Read `src/locksmith/plugins/cuo/page.py` in full: confirmed the objectName
  contract (`cuoMandatePage.lineOfBusiness` is a `QComboBox`,
  `.windowOpens`/`.windowCloses` live on the inner `QDateEdit`'s `QLineEdit`,
  `.submit` stays `setEnabled(True)` unconditionally).
- Read `src/locksmith/plugins/cuo/review_dialog.py`: confirmed
  `mandateReviewDialog.confirm` is enabled from construction (no
  `setEnabled(False)` at init — it only disables itself *after* being
  clicked), so `wait_for condition=enabled` resolves as soon as the dialog
  opens and is a valid proxy for "the form validated cleanly."
- Read the bundled schema
  (`brands/usurance/egf/EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5.json`):
  confirmed `line_of_business` enum includes `auto` (lowercase, verbatim —
  matches `select value="auto"`), `jurisdiction` pattern
  `^US-[A-Z]{2}$` (matches `"US-UT"`), coverage item pattern
  `^[A-Z0-9][A-Z0-9-]*$` (matches `"BI"`/`"PD"` unchanged).
- Read `src/locksmith/plugins/cuo/date_field.py`: display format is
  `MM/dd/yyyy`, confirming `"01/01/2027"`/`"12/31/2027"` are the right
  strings for `.windowOpens`/`.windowCloses`.
- Read the installed `locksmith-ui-tester` 0.2.0 source at
  `~/.locksmith/plugins/ui_tester/src/locksmith_ui_tester/server.py`:
  confirmed `_op_type`, `_op_select`, `_op_click`, `_op_wait_for` and
  `_require_enabled` behave exactly as the brief describes (click refuses a
  disabled target; `wait_for condition=enabled` checks `visible and
  isEnabled()`).

### `tests/integration/peer/testegf.py` — comment correction

Verified the claim myself before rewriting it, per the task instructions:
counted `E*.json` in `~/code/ugard/docs/usurance/egf/` (10 schema files +
`overlay.usurance.json`, which isn't a schema and isn't globbed) against
`brands/usurance/egf/` (the same 10 schema files, byte-identical names). They
now match exactly, so the overlay loop's `if target.exists(): continue`
fires for every file and copies nothing today. Rewrote the comment to say
that plainly and reframe the loop as a safety net against future drift
rather than an active overlay restoring three missing schemas (which was
true when the comment was written but is no longer true).

## Deviation from the brief's literal replacement code

The brief's Step 2 snippet ends after clicking `mandateReviewDialog.confirm`
and asserting `ok`. I added back a final step the brief's snippet dropped:

```python
r = devctl(sock, "wait_for", target="cuoMandatePage.declaredBanner",
           condition="visible", timeout_ms=10000)
assert r.get("ok"), f"the mandate never finished issuing after confirm: {r}"
```

**Why:** `mandateReviewDialog.confirm`'s click handler
(`CuoMandatePage._confirm_review`) only *schedules* the anchor — it calls
`vault.extend([issue_doer])` and returns. The credential is actually issued
on later ticks of the Qt/hio event loop; only the doer's
`credential_issued` event fires `_show_declared`, which paints the banner
and closes the review dialog. `devctl`'s `click` op calls `widget.click()`,
which runs the connected slot **synchronously** and returns immediately —
so without this wait, `submit_mandate_form_via_ui` returns the instant the
click's Python call stack unwinds, well before the mandate exists.

This is exactly the wait the *old* helper had as its last step (same
objectName, same 10s timeout) — the brief's rewrite silently dropped it. I
checked all three real callers of this helper (not just the two named in
the Interfaces block) to see whether dropping it would actually break
anything:

- `declare_mandate_via_ui` → `watch_cuo_mandate_via_peer` polls up to 15s
  for a sitecustomize-hook-exported artifact file that only appears after
  `_show_declared` fires — this absorbs the missing wait by accident.
- `test_admin_grants_to_hoas_via_ui.py`'s arc calls
  `submit_mandate_form_via_ui` directly, then polls up to 120s for the
  actuary's `observedMandates` list to fill — same accidental cover.
- `test_cuo_mandate_via_ui.py` calls `declare_mandate_via_ui` and asserts
  **nothing else**. Without the wait, that test would keep reporting green
  even if the credential issuance silently broke — a real, silent loss of
  coverage, not just a style nit. (I did not run this test — it wasn't in
  my authorized command list — but I read it and traced the call chain by
  hand to confirm the gap.)

Given the fix is a one-line restoration of prior, already-proven behavior
(same objectName, same timeout, zero interface change) I applied it rather
than stopping to ask, and I'm flagging it clearly here as instructed.

## Commands run and full output

### Unit run (`tests/plugins/cuo/`, must stay at 143 passed)

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/plugins/cuo/ -q --import-mode=importlib
........................................................................ [ 50%]
.......................................................................  [100%]
=============================== warnings summary ===============================
.venv/lib/python3.14/site-packages/pysodium/__init__.py:299
  /Users/seriouscoderone/code/locksmith/.venv/lib/python3.14/site-packages/pysodium/__init__.py:299: DeprecationWarning: Due to '_pack_', the 'CryptoSignState' Structure will use memory layout compatible with MSVC (Windows). If this is intended, set _layout_ to 'ms'. The implicit default is deprecated and slated to become an error in Python 3.19.
    class CryptoSignState(ctypes.Structure):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
143 passed, 1 warning in 3.73s
```

Result: **143 passed, unchanged.**

### Collection sanity (extra, not in the brief — cheap way to confirm the two
edited files import cleanly before spending 20s on the real UI test)

```
$ QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/integration/roles/ tests/integration/peer/ -q --import-mode=importlib --collect-only
...
18 tests collected in 0.05s
```

No collection errors.

### Visible run (the short validation test, Step 3)

```
$ QT_QPA_PLATFORM= LOCKSMITH_TEST_VISIBLE=1 .venv/bin/python -m pytest tests/integration/roles/test_actuary_observes_and_attests_via_ui.py -q --import-mode=importlib -p no:randomly
.                                                                        [100%]
=============================== warnings summary ===============================
tests/integration/roles/test_actuary_observes_and_attests_via_ui.py::test_the_actuary_sees_a_watched_mandate_and_can_attest
  /Users/seriouscoderone/code/locksmith/.venv/lib/python3.14/site-packages/pysodium/__init__.py:299: DeprecationWarning: Due to '_pack_', the 'CryptoSignState' Structure will use memory layout compatible with MSVC (Windows). If this is intended, set _layout_ to 'ms'. The implicit default is deprecated and slated to become an error in Python 3.19.
    class CryptoSignState(ctypes.Structure):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1 passed, 1 warning in 19.31s
```

Result: **1 passed in 19.31s** (brief expected ~20s; the restored
`declaredBanner` wait did not blow the budget — the actual issuance
completed well inside its 10s timeout, since the whole test still landed at
19.31s).

## Commit

`54250eef` — `test(roles): drive the rebuilt mandate form, through the read-back`

Staged only the two files this task touched
(`tests/integration/roles/conftest.py`, `tests/integration/peer/testegf.py`).
Left three pre-existing, unrelated modified files alone (present in `git
status` before I touched anything, not part of this task, not mine to
decide about): `.superpowers/sdd/.gitignore`,
`brands/usurance/egf/oobis/EGjm-X1JMz-yKFeumEZ9meSVNvnV8VTXmjJMlyBVMMTO.cesr`,
`docs/superpowers/plans/2026-08-08-cuo-mandate-form.md`.

## Anything else in the brief that was wrong

Besides the dropped `declaredBanner` wait (above), everything else in the
brief checked out exactly against the source: the objectName contract, the
enum value casing, the jurisdiction/coverage pattern strings, the date
display format, and the devctl 0.2.0 `_op_type`/`_op_select`/`_op_click`/
`_op_wait_for`/`_require_enabled` mechanics. The `testegf.py` drift claim
(ten vs. eight documents) was accurate as of when it was written and is now
stale exactly as the task said — I verified the current counts myself
(both trees hold the same 10 `E*.json` files today) before rewriting the
comment.

## Concerns for the four-window arc (which I have not run)

1. **The restored `declaredBanner` wait now sits inside the shared helper**,
   so the arc's own call at `test_admin_grants_to_hoas_via_ui.py:206`
   (`submit_mandate_form_via_ui(devctl, cuo)`) will block up to 10s for the
   banner before returning, where it previously (per the brief's literal
   snippet) would have returned immediately after the confirm click. This
   should be strictly safer for the arc — it means the mandate is
   *guaranteed* issued and anchored on the CUO's KEL before the test moves
   on to click `Actuarial` and poll `observedMandates` — but it does add up
   to ~10s of extra worst-case wall time inside a step that previously had
   no such wait. Given the arc's own poll loop afterward already runs up to
   120s, this is very unlikely to change the outcome, only (if anything)
   shifts a few seconds of waiting from the polling loop into this earlier
   wait.
2. **Untested interaction with the arc's own timing/log-watching:** I did
   not run the arc, so I can't confirm there isn't some place later in that
   test that assumes the CUO wallet is still mid-flight (e.g., checking
   `_submit` button text/state, or the review dialog still being open)
   right after this helper returns. I read through
   `test_admin_grants_to_hoas_via_ui.py` and found no such assumption in the
   surrounding code, but I did not execute the test to confirm dynamically.
3. **Port collision risk**, as the owner already flagged: since I did not
   run the arc test, there should be no leftover devctl sockets or wallet
   subprocesses from this task competing for ports when the owner runs it.
