# CUO product-mandate form — Design

**Status:** approved by the owner 2026-08-08, section by section. Ready for `superpowers:writing-plans`.
**Scope:** `src/locksmith/plugins/cuo/page.py` and its tests. **This form only, self-contained** (owner, 2026-08-08).
**Origin:** the 2026-08-08 HOA polish round. Owner request: *"lets use some best practices to build a 'good' form (validation, dropdowns, type specific controls (i.e. date fields)"*, plus a UI/UX expert review.

## Global Constraints (bind every task)

1. **Python + PySide6/Qt.** Not TypeScript, not a web view.
2. **Every constraint comes from the EGF at runtime.** No enum member, regex, date format or field
   requirement is written as a Python literal. Source: the `declare_product_mandate` command's
   `payload_schema` in the published micro-app template inside the brand's EGF bundle, which
   `egf_local_dir()` already resolves (`page.py:232`).
3. **The EGF is READ-ONLY here.** No new fields, no `context_dimensions`, no re-SAIDing, no pin
   cascade. Confirmed with the owner.
4. **Authority for layout, validation and copy is** `~/code/usurance/spec/suite/ux-patterns.md` §11
   (Form Patterns) and `design-system.md`. See §1.2 for why the brand-kit documents are not.
5. **Do not modify `ui/onboarding/form_builder.py`** or anything else shared. See §3.3.
6. **Reuse the toolkit** (§3.2). Exactly one new widget is sanctioned: a date field.
7. Sentence case everywhere. No "please", "simply", "just". Error text names the offending value
   and the next action.

---

## 1. Context

### 1.1 What is wrong today

`CuoMandatePage` is 250 lines of hand-rolled Qt using none of the toolkit's page machinery. Five
identical `LocksmithLineEdit` rows in a bare `QFormLayout`, and **the entire client-side validation
is one rule**:

```python
valid = all(f.text().strip() for f in self._fields())   # page.py:168
```

Five non-empty strings. Everything the schema actually requires is enforced for the first time by
`Credentialer.validate` on the issuing side, arriving asynchronously as a
`credential_issuance_failed` event whose raw `error` string is dumped verbatim into a page-level
banner with no field attribution (`page.py:288`).

Measured consequences, each of which a task below closes:

| # | Defect | Evidence |
|---|---|---|
| D1 | Labels sit to the LEFT, right-aligned. Not a choice — `QFormLayout()` is created and never configured, so the macOS style supplies `AlignRight` and `FieldsStayAtSizeHint`. | `page.py:120`; forbidden by `ux-patterns.md:300` |
| D2 | All five inputs render at the QLineEdit sizeHint (~17 chars) while the prose paragraph and the CTA take the full window. The widths are inverted. | `ux-patterns.md:299` forbids fixed field widths |
| D3 | `line_of_business` is free text against a **closed 8-value enum**. The placeholder suggests `prop`, which is not a member, and its comma implies multiple, which is invalid. | schema `enum`; `page.py:125` |
| D4 | One "Effective window" box holds **two** schema fields, split on `/`. `partition("/")` cannot fail, so a single date silently ships `window_closes == ""`. | `page.py:184` |
| D5 | `window_opens < window_closes` is never checked, though it is a declared pre-mint gate and **nothing re-checks it after issuance**. | template rule `mandate_window_opens_before_it_closes` |
| D6 | No overlap check, so a second mandate for a (line, jurisdiction) already in force fails only at the ledger. | template rule `no_overlapping_mandate_for_this_scope` |
| D7 | `thesis` is unpatterned prose in a single-line edit ~18 characters wide. The CUO cannot read her own sentence back before it is permanent. | `page.py:141`; `LocksmithPlainTextEdit` exists and is unused |
| D8 | The submit button is never disabled while an issuance is in flight, so a second click anchors a **duplicate immutable mandate**. | `page.py:249-305` |
| D9 | The success banner is never cleared, so a stale SAID from a previous mint sits on screen while the next is typed. Only the first 12 characters of the SAID are shown. | `page.py:317` |
| D10 | The page's only prose asserts the **opposite of the truth**: *"An untargeted declaration, addressed to nobody"* reads as private. `disclosure_mode` is `full`; it is untargeted precisely so unknown parties can consume it. The words permanent, immutable and public appear nowhere. | `page.py:92-96`; template `credentials.exports[product_mandate].envelope` |
| D11 | No read-back. `_build_payload` silently rewrites input (lowercases the line, upper-cases coverages, bolts on `US-`), so what is signed is not what was typed and the difference is never shown. | `page.py:174-195` |

### 1.2 Why the brand-kit documents do not govern this form

The owner supplied four `tools/brand-kit-gate/` files as guidance. Measured, they are not the
authority for in-app UI, and the redesign must not follow them:

- **It is not a conformance gate.** "Gate" is HTTP Basic Auth on hosting — a CloudFront function
  that 401s unauthenticated requests (`cf-basicauth.js:5-16`). No linter, no CI job, and nothing in
  usurance, ugard or locksmith reads those files. A redesign cannot pass or fail it.
- **Its own tokens forbid this use.** The embedded `tokens.json` `$description`: *"Usurance
  CORPORATE BRAND tokens (external-facing: website, marketing, presentations, collateral)… do NOT
  use these corporate tokens for in-app UI"* (`brand-kit.html:437`).
- `READ-THIS-FIRST.md`: *"not its permanent home… Do not treat this folder as the canonical brand
  location."*

The two systems disagree on nearly every value a form consumes — navy `#202B61` / gold `#D4A017` vs
slate `#0f172a` / teal `#2AABB3`; Montserrat vs Inter; ad-hoc 7/8/10/12/14/22px radii vs a scale
with inputs at 4px and buttons at 6px. Where they conflict the design system wins **by the brand
kit's own instruction**, and `brands/usurance/brand.toml` already agrees, pinning `#2AABB3` with a
comment citing `design-system.md`.

**What does carry over from the brand kit:** the tone-of-voice pillars (*"Established and
self-assured, never flashy"*, `guidelines.html:140`), Inter for body text, and the 14px body floor.

---

## 2. The schema is the specification

Both the command's `payload_schema` and the ACDC schema carry identical constraints for all six
fields. The form reads the **`payload_schema`**, because that is what the mint validates against.

| field | schema | control | derived validation |
|---|---|---|---|
| `line_of_business` | `enum` × 8 (`property, casualty, life, health, auto, workers_compensation, marine, aviation`) | select, no default selected | invalid unreachable; required = must choose |
| `jurisdiction` | `pattern ^US-[A-Z]{2}$` | validated text | pattern; auto-uppercase, `US-` prefixed on normalise |
| `coverages` | array, `minItems 1`, `uniqueItems`, item `pattern ^[A-Z0-9][A-Z0-9-]*$` | add/remove list | per-item pattern at add time, duplicate rejected, ≥1 required |
| `window_opens` | `format: date` | date field | is-a-date, required |
| `window_closes` | `format: date` | date field | is-a-date, required |
| `thesis` | `minLength 1` | multi-line text | non-empty |
| `d`, `dt` | derived / `format: date-time` | not shown | set at mint |

All six are `required`; the block is `additionalProperties: false`.

**Jurisdiction is a pattern, not an enum.** The EGF enumerates no subdivisions —
`context_dimensions` is `[]`. The owner chose a **pattern-validated text input, no list**, over
adding jurisdictions to the EGF. The consequence must be stated plainly and is load-bearing for §4:
**`US-TU` is a valid value.** The app cannot distinguish a real subdivision from a fake one, so a
transposition is caught only by the human read-back.

### 2.1 Two template rules the form enforces before anchoring

- **`mandate_window_opens_before_it_closes`** — `window_opens < window_closes`, **strict**, so a
  one-day window is rejected. Its own description: *"checked BEFORE the ACDC is anchored, which is
  the only point at which refusing costs nothing"*, and *"nothing re-checks this after issuance"*
  because ACDC cannot constrain two values inside one container. **The form is the last line of
  defence for this rule.**
- **`no_overlapping_mandate_for_this_scope`** — no existing in-window mandate for the same (line,
  jurisdiction). Stated harm: *"two overlapping mandates for one scope leave a watching actuary with
  two mandates to edge to and no ground for choosing."* Checked by enumerating this vault's own
  `product_mandate` credentials from `reger.schms`, as `product_designer/page.py` enumerates
  attestations. **Advisory:** the local view can be incomplete, and the ledger's
  `mandate_scopes_do_not_overlap` invariant is the real enforcement. Presented as a blocking error
  whose text says what this app knows.

---

## 3. Architecture

### 3.1 Layout

One bounded column, 640px, inside `LocksmithFormPage`'s scroll area. Every field is a vertical
group: **label above** (14px / Medium 500 / Gray 700), control at 100% of the column, help text
below, error below that. Required fields carry an asterisk **after** the label with a
"This field is required." tooltip. Field labels never change colour on error; the control gets a red
border and a message beneath.

`window_opens` and `window_closes` sit side by side — one decision, two controls.

Footer: `LocksmithInvertedButton` "Cancel" left, primary right, both 36px. No full-bleed button.

### 3.2 Reused, not built

`LocksmithFormPage` (sticky header, animated error/success banners with hover copy button, scroll
area, `show_error`/`clear_error`/`show_success`), `LocksmithTextListWidget` for `coverages`,
`LocksmithPlainTextEdit` for `thesis`, `LocksmithDialog` for the review modal (it has its own banner
API and, since 2026-08-08, `WA_DeleteOnClose`), `LocksmithButton` / `LocksmithInvertedButton`,
`WaitingSpinner` for the in-flight state.

**One new widget:** a date field. Nothing reusable exists — the app's only date input is a raw
`QDateTimeEdit` hand-styled inline at `ui/vault/credentials/issued/issue.py:721`, and the toolkit has
no validator beyond `QIntValidator`/`QDoubleValidator`. Build it in the CUO plugin, not the shared
toolkit, per the self-contained scope; promoting it is a follow-up.

### 3.3 Why not `SchemaFormBuilder`

`ui/onboarding/form_builder.py` (533 lines) already maps a `payload_schema` to widgets and returns
`validate()` messages. It would supply four of six fields — `enum`→`QComboBox` with
`setCurrentIndex(-1)`, `pattern`→validator, `minLength`, and `format: date-time` hidden and
auto-filled. It is **not** used, for three measured reasons:

1. **`coverages` fails outright.** Its array branch requires `items` to be a *string enum*; ours is
   a string with a `pattern`, so it emits `"unsupported array construct (items must be a string
   enum)"` (`form_builder.py:278`).
2. **No `format: date` branch exists.** Both dates fall through to a bare line edit.
3. **Its layout is the forbidden one** — `QFormLayout.addRow(label, widget)` in nine places — and
   `_label_for` does `key.replace("_"," ").title()`, producing Title Case ("Line Of Business").

Its consumers are `onboarding/home_page.py` and `onboarding/request_flow.py` — the role-request
flow. Fixing it properly means changing those, which is outside the boundary the owner set.
**Follow-up (not this project):** consolidate the CUO controls and `SchemaFormBuilder` into one
schema-driven form layer, and give it the date and pattern-item-array branches.

---

## 4. Flow, states and the read-back

Editing → validate → **review** → anchor → result.

### 4.1 Validation timing (`ux-patterns.md:190-192`)

- Required errors fire **on submit only**, never before the first attempt.
- Format errors fire **on blur, and only after the first submit attempt**.
- On a failed submit: focus and scroll to the first invalid field, and show a count banner.

**Therefore the primary button stays ENABLED while the form is invalid.** This reverses today's
behaviour and is not optional: a disabled button makes the spec's errors-on-submit unreachable —
the user could never trigger the submit that reveals what is wrong. The button disables for exactly
one reason: an issuance in flight.

### 4.2 The review modal

`ux-patterns.md:439` makes a confirmation modal the platform's own irreversibility pattern. It shows
**the canonical payload, not the raw field text** (D11), because that is where a `US-TU`
transposition is visible — and per §2 it is the only place it can be caught.

Contents: who is signing (role + identifier; today the signer appears nowhere), the six canonical
values, the window as a sentence, the thesis verbatim in its own block labelled "published in full",
and the caution.

### 4.3 States

| state | primary | closes |
|---|---|---|
| Editing | "Review mandate", enabled even when invalid | §4.1 |
| Reviewing | "Sign mandate" / secondary "Keep editing" | D11 |
| Anchoring | disabled + spinner, whole in-flight window | **D8** |
| Signed | modal closes; **full** SAID with copy affordance | D9 |
| Failed | modal closes, form editable, **typed values survive** | — |

The success banner clears when editing resumes (D9).

Mint-time errors remain possible — the issuer is the final authority. Where its message names a
field it is attributed to that field; otherwise it goes to the banner, never as a raw exception
string.

---

## 5. Copy

Produced by three independent drafts judged against the voice rules; full set in
`docs/superpowers/specs/assets/2026-08-08-cuo-mandate-copy.json`. The load-bearing lines:

**Page intro** (replaces D10):

> Submitting signs this mandate with your chief underwriting authority and adds it permanently to
> your own published record.
>
> You are publishing, not filing: nothing here can be edited afterwards, and anyone who asks reads
> all of it, your thesis word for word.

**Review caution:**

> Signing is final. These values can never be edited, and the whole mandate, thesis included, goes
> to anyone who asks for it. To correct a mandate, declare a new one. Withdrawing later records that
> you stopped pursuing it and leaves what you declared readable.

**Jurisdiction help** — the honest limit, converted into an instruction:

> Format US-UT, one jurisdiction per mandate. Only the format is checked; the app cannot tell US-UT
> from US-TU, so read your code back before you sign.

**Thesis help:**

> One sentence of business intent, in your own words. It publishes verbatim, so write it for a
> reader outside the company.

### 5.1 Three owner decisions, recorded so they are not "fixed" later

- **Verb: "sign", not "declare".** The commit button is "Sign mandate" and the caution is "Signing
  is final", even though the page title, the button today, and the command `declare_product_mandate`
  all say *declare*. The owner chose this knowingly over a single-vocabulary alternative: signing is
  what irreversibly happens, and the stronger word belongs at the point of no return. **The H1 stays
  "Declare a product mandate"** — the page is named for the act, the button for the commitment.

  Consequence, applied: the form's pre-commit primary is **"Review mandate"**, not "Review
  declaration" as first mocked. The mockup predated this decision; "declaration" would reintroduce
  the vocabulary the owner rejected, one control before the button that rejects it. The modal title
  is "Review this mandate before signing", so the two read as one sequence.
- **Withdrawal is named without a route.** The caution mentions withdrawal; nothing on this screen
  links to it. Deliberate: a CUO should know the remedy exists even though she reaches it elsewhere.
  Adding the route was offered and declined, twice.
- **Two date formats, deliberately.** `MM/DD/YYYY` in the form (per the suite's §12 date standard);
  **ISO in the read-back**, so the read-back shows byte-for-byte what is signed. The stored value is
  always ISO — `format: date`.

### 5.2 Copy still to write (gaps the editor caught)

- `"Fix {count} errors before signing."` does not pluralise — renders "Fix 1 errors". Needs a
  count-aware string.
- **Required-field messages do not exist.** Empty line of business, empty coverage list, empty
  thesis, either date blank — the four most common failures. §11 puts required errors on submit, so
  without them the banner can count errors that have no message beneath them.
- **Placeholders do not exist.** §11: *"No field should render without a placeholder."* Needed for
  jurisdiction (`US-UT`), coverages (`BI`), and the select ("Choose a line of business").
- **A token contract must be ratified** before the strings are wired — `{code}`, `{count}`,
  `{cuo_name}`, `{line_of_business}`, `{jurisdiction}`, `{existing_opens}`, `{existing_closes}`. A
  silently wrong token renders as literal braces.

---

## 6. Testing

Per Principle VII: no manual testing, all of it AI-runnable.

**Generator-level guards** (these are the durable ones):

- **No schema literal appears in Python.** The test fails if any of the eight `line_of_business`
  values, `^US-[A-Z]{2}$`, or `^[A-Z0-9][A-Z0-9-]*$` is found in the CUO plugin's source. This is
  what "values come from the EGF" means operationally.
- **The two schema copies agree** — command `payload_schema` vs ACDC schema, field by field. Two
  copies with no reconciler is how they drift.

**Behavioural:**

- Per-field: enum has exactly the schema's members and no default; `UTAH` rejected, `ut` normalises
  to `US-UT`; a lowercase coverage and a duplicate both rejected; `minItems 1` enforced.
- **Timing:** no error before the first submit; a format error appears on blur only after it.
- **The primary is enabled while the form is invalid** — the deadlock guard for §4.1.
- **Two submits schedule one issuance** — the D8 guard.
- The success banner clears when editing resumes (D9).
- The read-back shows canonical values: enter `ut`, the modal reads `US-UT`.
- `window_opens == window_closes` is rejected with the ordering message (D5, strict `<`).
- Overlap: with a held mandate for the same (line, jurisdiction), an overlapping window is blocked
  and the message names the existing mandate.

**Integration.** `submit_mandate_form_via_ui` (`tests/integration/roles/conftest.py:851`) must be
rewritten and the four-window arc re-run. Deliberate choices to limit the damage:

- Keep `cuoMandatePage.{lineOfBusiness,jurisdiction,coverages,thesis,submit}`.
- `effectiveWindow` → `windowOpens` + `windowCloses`, named for the schema fields.
- **A comma commits a coverage token**, so `type "BI,PD"` keeps working unchanged.
- New: `mandateReviewDialog`, `.confirm`, `.back`, `.summary`.

What breaks and must be updated: the `effectiveWindow` line becomes two; `lineOfBusiness` needs
`select` not `type`; the `is_checked` assertion goes away because the button no longer encodes
validity, replaced by asserting the review dialog opened; and one extra click to confirm.

---

## 7. Out of scope

- Modifying the EGF in any way.
- `ui/onboarding/form_builder.py` and the role-request flow (§3.3).
- The actuary and designer forms. They have the same defects; this spec does not fix them.
- Promoting the date field into the shared toolkit.
- A withdraw route or a mandates list (§5.1).
- The open disclosure posture — `ugard/backlog/2026-08-08-open-disclosure-posture-blocks-production.md`.
