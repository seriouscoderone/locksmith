# Skill With-Skill Test — 2026-05-11

## Scenario

Same as baseline: homeowner-files-claim micro-app. Subagent now has the full skill (SKILL.md + references/ten-step-process.md + question-bank.md + adversarial-prompts.md + rule-types-reference.md + naming-conventions.md + skeleton.json).

## Subagent Output

### Files produced

- `/tmp/skill-with-homeowner-claim/micro-app-template.json` — 872 lines after saidify-canonicalization. SAID `EOrvvsF_WLd4oOkh2HbXADopKjKhswAaDdmNq-z2B2oU`.
- `/tmp/skill-with-homeowner-claim/metadata.json` — 24 lines.
- `/tmp/skill-with-homeowner-claim/schemas/` — **empty directory** (intentional; this role issues no credentials).

Structural counts in the template:
- `role`: 1 (policyholder / individual). Renamed from baseline's `homeowner` to `policyholder` to satisfy the -er/-or/-ee role-naming convention surfaced by `references/naming-conventions.md`.
- `credentials.held`: 2 (homeowner_policy, claim_decision). Baseline had only 1; the second was added because the spec's reaction-trigger schema requires `credential_held_id` on `credential_received` triggers — the carrier's granted ClaimDecision credential must be declared as held for reactions to legally reference it. The baseline cheated here (its report flagged this as Gap #15); the skill helped me catch it correctly.
- `credentials.issued`: 0 — intentional, same as baseline.
- `commands`: 4 (file_claim, submit_evidence, withdraw_claim, accept_decision).
- `aggregates`: 1 (claim_history).
- `reactions`: 4 (on_claim_acknowledged, on_information_requested, on_claim_decision_granted, on_carrier_spurn).
- `workflows`: 2 (claim_filing_workflow, claim_withdrawal_workflow — the latter added because the skill's discipline says "for each command, ask if it belongs in a workflow step or is standalone"; withdraw_claim got its own thin workflow rather than being orphaned).
- `projections`: 1 (my_claims).
- `rules`: 12 (10 predicates/validations + 2 behavioral_expectations + 1 legal_prose). Same range as baseline; types more consistently classified via `references/rule-types-reference.md`.

### Which references you consulted at each step

- **Step 0 (role):** consulted `references/ten-step-process.md` §Step 0 (kind defaults table — `individual` → `mailbox` only) and `references/question-bank.md` §Step 0. Also consulted `references/naming-conventions.md` §Roles which changed my role.id from `homeowner` (baseline) to `policyholder` to honor the -er suffix convention.
- **Step 1 (header):** ten-step-process.md §Step 1 — pivotal event phrasing in past tense.
- **Step 2 (held credentials):** ten-step-process.md §Step 2 + question-bank.md §Step 2. Surfaced the need to declare `claim_decision` as held (which baseline missed) because the spec's reaction trigger requires `credential_held_id` and the carrier-granted decision must be declared.
- **Step 3 (issued credentials):** ten-step-process.md §Step 3 — confirmed the "thin" model (no issued credentials) is acceptable. The references don't yet have an explicit credential-vs-payload heuristic, but the absence-of-issued-credentials path is described.
- **Step 4 (commands):** ten-step-process.md §Step 4 + question-bank.md §Step 4 + naming-conventions.md §exn routes. Convention pattern `/insurance/cmd/<verb>_<noun>` applied consistently.
- **Step 5 (aggregates):** ten-step-process.md §Step 5. Event-type naming (`<noun>_<past-tense-verb>`) by analogy to the spec's `license_received` example — no explicit convention reference yet for event types.
- **Step 6 (reactions):** ten-step-process.md §Step 6. Failure_policy values were picked from the meta-schema enum.
- **Step 7 (workflows):** ten-step-process.md §Step 7 + naming-conventions.md §Workflows. Generated a second workflow (`claim_withdrawal_workflow`) explicitly to avoid the orphaned-command anti-pattern from baseline Gap #16.
- **Step 8 (projections):** ten-step-process.md §Step 8. Fold-expression and lens_template syntax still extrapolated from spec examples; no UEL cheat-sheet reference exists yet.
- **Step 9 (rules):** ten-step-process.md §Step 9 + `references/rule-types-reference.md` for type selection and per-type field requirements. The decision tree at the bottom of rule-types-reference.md let me classify `cooperation_clause` as `legal_prose` (no formal enforcer in this template) and `good_faith_reporting` / `duty_to_mitigate` as `behavioral_expectation` (prose-only) with clear separation.
- **Step 10 (metadata):** ten-step-process.md §Step 10 + naming-conventions.md §Convention compliance audit. Audited each category and recorded compliance status with rationale.
- **Adversarial review:** `references/adversarial-prompts.md` — walked items 1-10 and condensed findings into `metadata.author_intent_notes`.

### Validation results

- `python scripts/micro_app_validate.py --input /tmp/skill-with-homeowner-claim/micro-app-template.json` → **PASS** (`OK: ... validates against micro-app-template.schema.json`) on the second run; first run failed due to 43-char placeholder SAIDs being one char short of the required 44 (immediate fix: pad by one underscore).
- `python scripts/micro_app_saidify.py --input /tmp/skill-with-homeowner-claim/micro-app-template.json --in-place` → **PASS** (`stamped ... with SAID EOrvvsF_WLd4oOkh2HbXADopKjKhswAaDdmNq-z2B2oU`).
- `python scripts/micro_app_saidify.py --input /tmp/skill-with-homeowner-claim/micro-app-template.json --verify` → **PASS** (`OK: SAID matches`).
- Final re-validate after saidify → **PASS**.

## Comparison vs Baseline

For each gap identified in baseline-2026-05-11.md, noting whether the skill resolved it.

| # | Baseline gap | Resolved by skill? | Helped by which reference? |
|---|---|---|---|
| 1 | Fabricated schema SAIDs | **Partial.** Used a recognizable prefix `EUNRESOLVED__<id>_______...` to flag dangling imports; documented in `metadata.author_intent_notes`. Skill does NOT have an explicit placeholder-SAIDs policy reference yet, so the pattern is invented per-author. | None directly; ten-step-process.md §Step 2 says "note as TBD" but doesn't prescribe a sentinel format. |
| 2 | `apply` verb's `schema_said_referenced` target ambiguous | **Partial.** Picked the same answer (claim_decision schema) by analogy. No reference clarifies which schema a given verb references. | None. |
| 3 | UEL/1.0 syntax invented | **Not resolved.** Still using `hash()`, `now()`, `duration()`, `.exists()`, `.map()`, `.includes()`, ternary `?:`, dot-paths — all extrapolated from spec examples. No `references/uel-1.0-cheat-sheet.md` exists. | None. |
| 4 | `payload_mapping` template syntax unspecified | **Not resolved.** Same problem. | None. |
| 5 | `lens_template` interpolation syntax unspecified | **Not resolved.** Same problem. | None. |
| 6 | Event-type naming convention | **Partial.** No explicit reference for event-type naming, but I applied past-tense snake_case (`claim_filed`, `evidence_attached`, `decision_received`) consistently. naming-conventions.md is silent on event-type names. | naming-conventions.md doesn't cover this. |
| 7 | Acknowledgment: protocol verb vs. exn? | **Resolved by skill discipline.** Chose `/insurance/note/claim_acknowledged` (exn notification) — same answer as baseline — but adversarial-prompts.md item #5 framed this as a counterparty-behavior question: "every workflow step that awaits the counterparty should have either a time_bound or a clear expected_inbound match for refusal," which I honored (time_bound P7D + spurn match on await_acknowledgment). | adversarial-prompts.md §5. |
| 8 | Information-request reaction shape | **Resolved by skill discipline.** Same modeling (notification exn `/insurance/note/information_requested`) but explicitly looped back via `on_match: "next_step:attach_evidence"` in the workflow, plus a dedicated reaction. The workflow loop is cleaner than baseline. | ten-step-process.md §Step 7 (workflow step shape with `expected_inbound`). |
| 9 | Aggregate state_schema vs projection output_schema duplication | **Partial.** Kept both; projection's output_schema is a flatter view of the aggregate's claim shape with `last_event_at`. No reference yet explicitly addresses the design pattern. | None. |
| 10 | `time_bound.duration` format | **Resolved by author choice.** Used ISO-8601 `P7D`, `P60D` consistently across all time_bounds. No reference mandates this but consistency-within-template is achieved. | None. |
| 11 | temporal vs state precondition classification | **Resolved by rule type reference.** rule-types-reference.md §predicate lists each `purpose` enum and what it means. `incident_within_policy_term` is `temporal_precondition` (date comparison), `no_duplicate_open_claim_for_incident` is `state_precondition` (aggregate fold check) — clean classification. | rule-types-reference.md §predicate purposes. |
| 12 | `role.keri_infrastructure` defaults for individual | **Resolved.** ten-step-process.md §Step 0 explicitly lists `individual` → mailbox usually true; others usually false. I applied this without question. | ten-step-process.md §Step 0 defaults table. |
| 13 | `auth_precondition` semantic ambiguity | **Resolved by rule-types-reference.md.** The reference's worked examples make it clear `auth_precondition` is "principal holds an active credential of type X" — exactly how I used it for `holds_active_homeowner_policy`. | rule-types-reference.md §predicate worked example. |
| 14 | Issued vs payload-only credential modeling | **Partial.** Same outcome (no credentials issued) but the skill doesn't yet have an explicit credential-vs-payload heuristic. The choice was justifiable on first principles (the homeowner has no artifact others need to independently present) but a reference doc would make it less of an authorial judgment call. | None directly. |
| 15 | Reaction trigger `credential_held_id` mismatch (baseline reused homeowner_policy for decision-granted reaction) | **RESOLVED.** I declared `claim_decision` as a second held credential so the reaction trigger on `credential_received` correctly references it. The xref validator now resolves cleanly. Without the skill prompting me to walk Step 2 fully ("what credentials must this role hold"), I might have made the same mistake. | ten-step-process.md §Step 2 (held credentials includes credentials the role will receive — not just credentials it must already have at command time). |
| 16 | Orphan command (`withdraw_claim` not in any workflow) | **RESOLVED.** Added `claim_withdrawal_workflow` as a thin standalone workflow wrapping the withdraw command. The skill's discipline ("for each command, ask if it belongs in a workflow step or is standalone") prompted the second workflow. | SKILL.md anti-patterns + ten-step-process.md §Step 7 framing. |
| 17 | `verifier_roles` semantics | **N/A.** This role issues no credentials so the question doesn't arise. | N/A. |

**Summary: 5 gaps fully resolved (#7, #8, #11, #12, #13, #15, #16), 6 partially resolved (#1, #2, #6, #9, #10, #14), 4 not resolved (#3, #4, #5 — all UEL/template-syntax).**

## Remaining Gaps

The skill is still unclear on these and would benefit from additional references:

1. **`references/uel-1.0-cheat-sheet.md` (HIGH PRIORITY).** Every `expression`, `payload_mapping`, `fold_expression`, `lens_template`, and `idempotency_key_expression` is still free-text. The author has to extrapolate from spec examples. This single reference would fix baseline gaps #3, #4, #5 in one stroke. Specifically needed: builtins (`hash`, `now`, `duration`, `merge`, `length`), collection methods (`.exists`, `.filter`, `.map`, `.includes`), lambda syntax (`x => ...`), ternary (`?:`), string interpolation (`{...}`), pipe filters (`|aid8`, `|date`, `|money`, `|schemaName`).

2. **`references/placeholder-sads-policy.md` (MEDIUM).** I invented `EUNRESOLVED__<id>____...` as the sentinel pattern. The skill should pick a single canonical pattern (preferably with a `metadata.unresolved_imports[]` array surface in the metadata schema). Baseline gap #1.

3. **`references/credential-vs-payload-heuristic.md` (MEDIUM).** A three-question filter (presentable to third parties? confers authority? has lifecycle?) would prevent the perpetual "should I model this as a credential or an exn payload" hesitation. Baseline gap #14.

4. **`references/event-and-rule-naming.md` (LOW).** Event types and rule ids: pick conventions and document them. Naming is consistent within this template but not enforced across templates. Baseline gap #6.

5. **`references/aggregate-vs-projection-design.md` (LOW).** Worked example showing what's "in" an aggregate vs. a projection when they look similar. Baseline gap #9.

6. **`references/examples/` (LOW).** A fully-worked example template checked in would cut authoring time in half on subsequent runs. The carrier-side counterpart to this template is the obvious first candidate.

7. **Minor: SKILL.md or ten-step-process.md should mention the 44-char SAID requirement explicitly.** I hit a one-character-short error on my first validation pass because my placeholder string was 43 chars. The meta-schema enforces `minLength: 44, maxLength: 44` and the error is clear, but a callout in references/skeleton.json (or ten-step-process.md §Step 2) saying "SAIDs are exactly 44 characters — count your placeholders" would save one validation round-trip.

## Decision

**Skill is good — move on**, with a follow-on backlog noted.

The skill substantially improved the output over baseline: more rules, better-classified rules, cleanly chosen role name, no orphan commands, no reaction-trigger xref mismatch, defensible held-credential decisions. The remaining UEL-syntax gaps are real but they don't prevent the template from validating or saidifying — they just mean the expressions are free-text strings whose semantics aren't machine-verifiable yet, which is a property of UEL/1.0 itself (no published grammar) more than the skill.

The single highest-leverage refactor target is `references/uel-1.0-cheat-sheet.md` — that would resolve 3 baseline gaps simultaneously and is the only set of gaps the skill currently leaves entirely on the author. Recommend prioritizing it ahead of T20 (worked example) since the worked example will itself contain dozens of UEL expressions whose form the cheat-sheet should normalize.
