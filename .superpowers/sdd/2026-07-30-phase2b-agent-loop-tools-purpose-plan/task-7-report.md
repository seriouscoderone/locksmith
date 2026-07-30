# Task 7 report — real corpus loop test + unconstrained-field audit

## Status: complete, all green

## Steps taken (TDD, per brief)

1. Wrote `tests/test_audit_schema.py` verbatim from the brief. Ran it — confirmed
   `ModuleNotFoundError: No module named 'keri_assistant.audit_schema'`.
2. Wrote `src/keri_assistant/audit_schema.py` verbatim from the brief (`unconstrained_entity_fields`,
   `_walk` helper reusing `grounded_set_for` from `actionschema.py`). Re-ran: 6/6 passed on first try,
   no source-module edits needed.
3. Wrote `tests/test_loop_real_templates.py` verbatim from the brief, reading the two real templates
   by path from `tests/fixtures/real/` (never a sibling repo). 7/7 passed on first try.
4. Ran the full suite from `packages/keri-assistant/`: **220 passed**, 0 failures, 0 errors, 0 skips
   (baseline 207 + 13 new = 220, exact match).
5. No existing test was touched. No source module other than the new `audit_schema.py` was created
   or edited.

## `unconstrained_entity_fields()` output on the real corpus

Grounding used: `known_aids={DOI}`, `allowed_schema_saids=frozenset()` (same `G` as the brief's test
file).

### `regulator_grants_carrier_license.json`

```
('grant_license', 'application_id')
('grant_license', 'effective_date')
('grant_license', 'expiration_date')
('grant_license', 'granted_at')
('grant_license', 'jurisdiction')
('grant_license', 'license_number')
('reinstate_license', 'reinstatement_note')
('revoke_license', 'revocation_reason')
('revoke_license', 'revoked_at')
('spurn_application', 'application_id')
('spurn_application', 'denial_reason')
('spurn_application', 'denied_at')
('suspend_license', 'suspended_at')
('suspend_license', 'suspension_reason')
```

`('grant_license', 'application_id')` is the live 2A defect: required, plain string, and the
template's own field description reads "SAID of the carrier_license_application this grant
adjudicates." — exactly the case the module exists to surface. `spurn_application` carries the same
field for the same reason. The rest of the list (dates, reasons, notes, jurisdiction, license number)
is genuinely free text under this grounding — the module does not distinguish "should be an entity
reference" from "is actually free text"; that discrimination is the point of the docstring's
"visibility, not enforcement" framing, and is why the list is meant for human template review rather
than automated blocking.

### `actuary_attests_product_rating.json`

```
('attest_rating', 'attested_at')
('attest_rating', 'product_id')
('attest_rating', 'product_version')
('attest_rating', 'rate_program_version')
('attest_rating', 'statement')
('bounce_candidate', 'bounced_at')
('bounce_candidate', 'detail')
('bounce_candidate', 'product_id')
('ingest_rate_workbook', 'filing_date')
('ingest_rate_workbook', 'ingested_at')
('ingest_rate_workbook', 'ipd_coordinate')
('ingest_rate_workbook', 'product_id')
('ingest_rate_workbook', 'state')
('ingest_rate_workbook', 'workbook_ref')
('open_rate_program', 'line_of_business')
('open_rate_program', 'opened_at')
('open_rate_program', 'product_id')
('record_priceability_review', 'note')
('record_priceability_review', 'option_ref')
('record_priceability_review', 'product_id')
('record_priceability_review', 'reviewed_at')
('record_priceability_review', 'state')
('record_priceability_review', 'thread_id')
('revoke_attestation', 'product_id')
('revoke_attestation', 'reason')
('revoke_attestation', 'revoked_at')
('seal_rate_program', 'effective_date')
('seal_rate_program', 'filing_reference')
('seal_rate_program', 'ipd_coordinate')
('seal_rate_program', 'product_id')
('seal_rate_program', 'sealed_at')
('seal_rate_program', 'state')
('seal_rate_program', 'supersedes_program_version')
('stage_rate_shard', 'product_id')
('stage_rate_shard', 'record_kind')
('stage_rate_shard', 'shard_name')
('stage_rate_shard', 'source_ref')
('stage_rate_shard', 'staged_at')
('stage_rate_shard', 'state')
('supersede_attestation', 'product_id')
('supersede_attestation', 'superseded_at')
```

Notable in this list, echoing the brief's "three naming shapes" narrative (checked directly against
both vendored files — see Concerns below): every command's `product_id` (a `<noun>_id` suffix) is
reported across the whole file, and the `*_ref` fields (`workbook_ref`, `source_ref`, `option_ref`) —
each documented as pointing at a specific filed artifact/source — are reported too, matching the "ref"
naming shape. `thread_id` on `record_priceability_review` is the same `_id` shape again.

## Concerns / things worth flagging to the plan author

- I checked both vendored templates directly for a literal plural `_saids` field (grep across all
  `payload_schema.properties` keys in both files) and found none. The brief's "three misses in three
  shapes" narrative is presented as a finding from "a scan of the real corpus" generally, not
  necessarily from just these two vendored files, so this is not a contradiction — just noting that
  the plural-`_saids` shape is not independently demonstrated by the corpus these tests exercise. Not
  a code change; nothing in the brief asked the tests to assert that shape.
- `unconstrained_entity_fields` only walks fields typed `"string"` (per the brief's own `_walk`
  implementation, matching the stated interface: "required, free-string payload fields"). A plural
  `_saids` field would almost certainly be typed as an array of strings, not `"string"`, so as
  specified this module would not catch that shape even if the corpus had one. That is consistent
  with the documented scope (string fields only) but worth the plan author knowing, since the
  docstring's own narrative uses the plural as the "decisive" example of a miss.
- No source module besides the new `audit_schema.py` was edited; no existing test was touched.

## Suite count

**220 passed**, 0 failed, 0 errors, 0 skipped (`packages/keri-assistant`, full suite,
`--import-mode=importlib`). Baseline was 207 → +13 (6 in `test_audit_schema.py`, 7 in
`test_loop_real_templates.py`), exact match to the two new files' test counts.

## Venv

No `pip install`/`pip uninstall` run. Tests ran against the existing shared venv's interpreter
(`/Users/seriouscoderone/code/locksmith/.claude/worktrees/assistant-2b/.venv/bin/python`) unmodified.

---

## Follow-up: `claimed_credential_refs` (added after review)

The team lead measured `unconstrained_entity_fields`'s own output on the real corpus after the
first commit and found a 2% signal ratio (1 genuine credential reference out of 55 rows) — a plain
listing delivers the form of visibility without the substance, since nobody reads a 55-row list to
find one item. Added `claimed_credential_refs(surface, grounding) -> tuple[tuple[str, str, str], ...]`
**alongside** `unconstrained_entity_fields` (not a replacement) in the same module, following TDD:
wrote the new tests first (both synthetic, in `test_audit_schema.py`, and real-corpus, in
`test_loop_real_templates.py`), confirmed `ImportError: cannot import name 'claimed_credential_refs'`,
then implemented it.

Design, per the team lead's spec: two independent signals over the same `unconstrained_entity_fields`
candidate set (so it is a strict filter, never a widening) —

- **Signal A** — the field's own `description` matches `\bSAID\b|self-addressing|\bdigest\b`
  (case-insensitive). Reason: `"described as a SAID"`.
- **Signal B** — an undescribed field shares its leaf name (the property's own local name, not the
  full dotted path) with a signal-A hit elsewhere in the same surface. Reason:
  `"shares a name with <verb_id>.<path>, which is described as a SAID"`.

Internally, `_walk` (private, shared by both public functions) now returns `(path, schema)` pairs
instead of bare paths, so `claimed_credential_refs` can read each candidate's own `description`; the
schema shape and public contract of `unconstrained_entity_fields` are unchanged and its existing
tests pass unmodified. A `_candidates()` helper factors out the "walk every exchange verb's payload"
loop that both public functions now share.

### `claimed_credential_refs` output on the real corpus

Grounding: same `G` as above.

```
CARRIER:
('grant_license', 'application_id', 'described as a SAID')
('spurn_application', 'application_id', 'shares a name with grant_license.application_id, which is described as a SAID')

ACTUARY:
(empty — zero hits)
```

This matches the team lead's own pre-measurement exactly: 2 hits on carrier, 0 on actuary, no false
positives.

`grant_license.application_id`'s own description reads "SAID of the carrier_license_application this
grant adjudicates." — signal A. `spurn_application.application_id` has **no description at all**
(`{"type": "string"}`, nothing else) — a description-only detector would miss it; it is caught only
via signal B, because it shares the leaf name "application_id" with the described field above. Verified
directly against the vendored JSON before writing the test. So the corpus contains **two** live
instances of the defect, not the one previously known — confirming the team lead's claim that signal
B is the interesting half.

Actuary's zero is a **correct negative**, not a gap: I grepped every required-field description in
both templates for the SAID/digest/self-addressing pattern before implementing. Actuary has plenty of
description text that matches (`index_said`, `shard_said`, `program_manifest_said`, `version_said`,
`attestation_said`, `superseded_by_said` are all literally described as "SAID of ..."), but every one
of those fields is already named `*_said`, so `grounded_set_for` reaches them and they never enter the
unconstrained candidate set in the first place — they're filtered out one step upstream of the new
detector, exactly as the "is a filter, never a widening" test requires. One near-miss worth recording:
`ingest_rate_workbook.shards`'s description also matches the SAID pattern ("each SAID-addressed"), but
its JSON type is `"array"`, not `"string"`, so it was never a candidate either — consistent with both
functions' documented scope (string fields only).

### Tests added

- `test_audit_schema.py` (+5, now 11 total): signal A on a synthetic description; signal B on an
  undescribed twin with the exact reason string; a genuinely free-text field with no claim and no
  twin is NOT reported (while confirming it IS still in `unconstrained_entity_fields`, the point of
  having both functions); the subset invariant on the synthetic fixture; a `*_said`-named field is
  not reported even though its own description claims a SAID (already excluded upstream, not a gap).
- `test_loop_real_templates.py` (+3, now 10 total): the two real carrier hits (with the exact B-signal
  reason string, referencing `grant_license.application_id`); actuary reports zero, with a comment
  explaining why that's correct rather than a miss; the subset invariant against
  `unconstrained_entity_fields` on both real templates.

### Suite count (updated)

**228 passed**, 0 failed, 0 errors, 0 skipped — up from 220 (+8, exactly matching the two files' new
test counts: +5 and +3). No existing test was touched; no source module other than `audit_schema.py`
was edited; no `pip install` run.

### Concerns

- None new. The blind-spot honesty the team lead asked for is in the module docstring: a credential
  reference with neither a claiming description nor a claiming twin is caught by **neither** signal —
  that residual gap is why the real fix stays the upstream ACDC-edge decision, not a smarter detector
  here.

---

## Second follow-up: the plural-`_saids` coverage gap (commit after review)

I had flagged, as a concern in the first follow-up, that `_walk` only reports `type: "string"` leaves
and would be structurally blind to an array-of-SAIDs field even if the corpus had one — while the
module's own docstring calls the plural `_saids` shape "the decisive" example of a miss. The team lead
independently verified this exact concern against a template we did not vendor
(`declaration_saids`, `type: array`, `items: string`) and confirmed the detector does not catch it as
shipped. Two fixes, both applied to the follow-up lineage as a new commit (not an amend, for the same
diffability reason as the first follow-up):

**Fix 1 — close the coverage gap (correctness, not documentation).** `_walk` now also reports a
required field whose schema is `type: "array"` with `items` an open (`enum`-free) `type: "string"`
schema, at the field's own path (not per-element — the defect is "this field accepts any string",
a property of the whole array). Refactored the shared `_open_string` predicate out of the scalar and
array branches so both paths agree on what "open" means. `claimed_credential_refs` needed no code
change — it already reads `schema.get("description")` off whatever candidate `_walk` hands it, so a
SAID-described array field is picked up by signal A automatically once it becomes a candidate.

**Fix 2 — stopped overclaiming in the docstring.** Reworded the opening paragraphs to say plainly
that the three naming shapes come from a scan of the *wider* corpus, that only two of the three
(`<noun>_id`, `ref`) are demonstrated by the two templates vendored into this repo, and that the
plural `_saids` shape is covered only by a synthetic fixture — with an explicit pointer to the test
that pins this fact against the real corpus, so the claim can't silently drift out of sync with what
the tests actually cover.

### Tests added (TDD: written first, confirmed 1 failure against the pre-fix code, then fixed)

- `test_audit_schema.py` (+2, now 13 total): a required array-of-strings named with a plural,
  described as a SAID (`declaration_saids`), is reported by **both** `unconstrained_entity_fields`
  and `claimed_credential_refs`; a required array-of-strings with an `enum` on `items` is **not**
  reported (already constrained).
- `test_loop_real_templates.py` (+1, now 11 total): an explicit, recursive (not just top-level)
  assertion that **neither** vendored template contains a field ending `_saids` — pins the honesty
  claim added in Fix 2 against the actual corpus.

Confirmed red first: running both files before the fix gave exactly 1 failure (the new array test)
and 23 passes, including the new "neither template has a plural field" assertion — proof the honesty
claim was already true of the corpus even before the code fix, and that the code fix alone closed the
gap.

### Effect on the real-corpus output

`unconstrained_entity_fields` gained exactly one new row on the real corpus:
`('open_rate_program', 'states')` on the actuary template (a required array of jurisdiction-code
strings, no `enum`) — a genuine, previously-invisible unconstrained field, not noise; it is NOT a
credential reference (description: "Jurisdictions this product will be rated for.") and does not
share a leaf name with any SAID-described field, so it correctly does not appear in
`claimed_credential_refs`. `lines_of_business` (carrier) and `shards` (actuary) were checked and
correctly remain unreported: the former's `items` carries an `enum`, the latter's `items` is
`type: object`, not `type: string`, so it needs the deeper item-object walk this fix deliberately does
not add (out of scope — "array of strings", not "array of anything").

`claimed_credential_refs` is **unchanged** on both real templates after the fix — still exactly the
same 2 carrier hits and 0 actuary hits reported in the first follow-up. Confirmed by direct output
inspection, not just the passing subset-invariant test.

### Suite count (updated again)

**231 passed**, 0 failed, 0 errors, 0 skipped — up from 228 (+3, exactly matching the two files' new
test counts: +2 and +1). No existing test was touched; no source module other than `audit_schema.py`
was edited; no `pip install` run.

### Concerns

- None new beyond what's already documented. The residual blind spot (a credential reference with
  neither a claiming description nor a claiming twin, in either scalar or array form) is unchanged by
  this fix and remains stated in the docstring as the reason the real fix is the upstream ACDC-edge
  decision, not a smarter detector.
- Per the team lead's explicit scope note: I did not vendor a third real template to demonstrate the
  plural shape — that stays the owner's call, raised separately by the team lead.

---

## Third follow-up: pinning the array-of-objects non-catch explicitly (commit 3bc65faf)

The team lead's next message crossed with the second follow-up above (441bf1a0) — it was written
against `235ee187` and reported the array fix as still missing, when it had already landed one commit
later. Confirmed the crossing directly: `git log --oneline` shows 441bf1a0 already present, and
`grep array audit_schema.py` on HEAD finds the fix.

What was genuinely still missing: an **explicit** synthetic test for the array-of-objects non-catch.
The narrowness of the array fix (`items` a bare string is a gap; `items` an object is not) was
previously backed only indirectly, by the real corpus's "actuary reports zero" test — not by a
dedicated case. Added `test_a_required_array_of_OBJECTS_is_not_reported_even_if_its_description_
claims_a_said` to `test_audit_schema.py`, mirroring the real `shards` field shape (array of objects,
each with a `shard_said` leaf, array's own description also matching the SAID pattern via "each
SAID-addressed") — the exact shape whose description-level near-miss was flagged back in the first
follow-up. No source change was needed; this pins behavior `441bf1a0` already had.

Confirmed directly, not just via the passing test:

```
array-of-strings (declaration_saids):
  unconstrained_entity_fields -> (('seal', 'declaration_saids'),)
  claimed_credential_refs     -> (('seal', 'declaration_saids', 'described as a SAID'),)

array-of-objects (shards-shaped, description also SAID-matching):
  unconstrained_entity_fields -> ()
  claimed_credential_refs     -> ()
```

### Suite count (final)

**232 passed**, 0 failed, 0 errors, 0 skipped — up from 231 (+1, the new confirming test). No existing
test was touched; no source module was edited in this step (test-only commit); no `pip install` run.

### Commit lineage for this task, in full

`0104a7f3` (unconstrained_entity_fields + real-corpus loop test, 220 passed) → `235ee187`
(claimed_credential_refs, 228 passed) → `441bf1a0` (array-of-strings fix + docstring honesty, 231
passed) → `3bc65faf` (array-of-objects non-catch pinned explicitly, 232 passed). Nothing amended;
each commit is independently diffable.
