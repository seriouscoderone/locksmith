# Designer Plugin Plan — Schema Alignment Addendum

**Date:** 2026-05-12
**Supersedes:** code-blocks in tasks 5-22 of `2026-05-12-designer-plugin.md` where they conflict with the canonical meta-schema.

## Why

The original plan invented field names (`header.label`, `role.name`, `command.effects[].credential_id`, `projection.render`, etc.) that don't match the canonical meta-schema at `docs/superpowers/specs/schemas/micro-app-template.schema.json`. Task 4's implementer caught this and corrected the test fixture; this addendum applies the same correction to tasks 5-22.

Tasks 1-4 are unaffected (schema-agnostic plumbing). Resume at Task 5 using canonical field names below.

## Canonical field map (per primitive)

Use these field names in fixtures, editor section labels, crossref walks, and dialog forms. Anything the original plan said about field names is overridden by this map.

### `header` (object, in template root)

Required: `id`, `display_name`, `description`, `version`, `expression_language`

Optional: `forked_from` (object with `template_said`, `template_version`, `forked_at`, `fork_intent`)

Patterns: `id` matches `^[a-z][a-z0-9-]*$`; `version` matches `^[0-9]+\.[0-9]+(\.[0-9]+)?$`; `expression_language` matches `^[A-Z][A-Za-z]*/[0-9]+\.[0-9]+$` (typical value: `"UEL/1.0"`).

### `role` (object, in template root)

Required: `id` (pattern `^[a-z][a-z0-9_-]*$`), `display_name`, `description`, `kind` (one of `individual`, `organization`, `system`, `device`, `agent`, `government`), `keri_infrastructure` (object with required boolean fields `witness_pool`, `watcher_network`, `mailbox`, `acdc_registry`).

### `credentials.imports[]` — `imported_credential`

Required: `id`, `expected_schema_said` (44-char SAID).

Optional: `expected_issuer_role`, `expected_attribute_constraints` (object), `lifecycle_acceptance` (array of strings, default `["active"]`), `narrative` (string).

**No `rule_refs` field.**

### `credentials.exports[]` — `exported_credential`

Required: `id`, `name`, `description`, `envelope`, `schema`, `lifecycle`.

- `envelope`: required `holder_role`, `verifier_roles[]`, `edges[]` (each with `edge_name`, `credential_id`, `cardinality` ∈ `{one, one_or_more}`, `operator` ∈ `{authorizes, references, authorizes-via-delegate}`), `disclosure_mode` ∈ `{full, selective, aggregate}`.
- `schema`: required `schema_said` (44 chars), `schema_path` (pattern `^schemas/[a-z][a-z0-9_-]*\.json$`).
- `lifecycle`: required `states[]` (unique strings, ≥1), `initial`, `transitions[]` each with required `id`, `from` (string or array of strings), `to`, `tel_primitive` ∈ `{issue, update, revoke}`. Optional per-transition: `via_workflow`, `trigger` ∈ `{manual, automatic}`, `condition_rule_ref`, `requires[].rule_ref`.

Optional: `rule_refs[]` (array of strings), `value_flow.implied_credentials[]` (each with `credential_id`, `relationship` ∈ `{issuer_grants, per_emission, per_holder_emission, implies_obligation}`).

### `commands[]`

Required: `id`, `name`, `description`, `route` (pattern `^/[a-z][a-z0-9_/-]*$`, must NOT start with `/ipex/`), `payload_schema` (object), `idempotency_key_expression` (string), `emissions[]`.

Optional: `counterparty_role` (string|null), `auth_preconditions[]`, `state_preconditions[]`, `temporal_preconditions[]` (each is a `rule_ref_obj`: `{rule_ref: string}`).

`emissions[]` is a union (oneOf) — each element has `kind` ∈ `{exchange, lifecycle_advance, aggregate_event}` with shape:
- `exchange`: `{kind: "exchange", exchange: <exchange object>}` where `exchange` is itself a oneOf (`{kind: "credential", verb, imported_credential_id?, exported_credential_id?, schema_said_referenced?}` or `{kind: "message", pattern ∈ {command, query, notification}, route, schema_id?}`).
- `lifecycle_advance`: `{kind: "lifecycle_advance", exported_credential_id, to_state}`.
- `aggregate_event`: `{kind: "aggregate_event", aggregate_id, event_type, payload_mapping}`.

### `aggregates[]`

Required: `id`, `description`, `inception_event_type`, `state_schema` (object), `initial_state` (any), `log_scope` ∈ `{private, witnessed, shared}`.

Optional: `invariants[]` (each is a `rule_ref_obj`).

### `reactions[]`

Required: `id`, `description`, `trigger`, `emissions[]`.

`trigger` is a oneOf with `type` ∈ `{credential_received, exn_received, lifecycle_event, scheduled}`:
- `credential_received`: requires `imported_credential_id`, optional `ipex_verb`.
- `exn_received`: requires `route` (path pattern), optional `schema_id`.
- `lifecycle_event`: optional `exported_credential_id`, `imported_credential_id`, `to_state`.
- `scheduled`: optional `cadence`, `at` (ISO date-time).

`emissions[]` same shape as commands.

Optional: `failure_policy` (object with `on_validation_failure` ∈ `{log_and_continue, log_and_spurn, abort}`, `timeout_seconds`).

### `workflows[]`

Required: `id`, `name`, `description`, `trigger`, `steps[]` (≥1).

`trigger.type` ∈ `{manual, scheduled, lifecycle_event, exn_received, credential_received}`. Various optional fields.

`steps[]` — each has required `id`, `name`, `actor` ∈ `{self, counterparty}`. Optional `command_id`, `reaction_id`, `advance_lifecycle` (`{credential_id, to_state}`), `expected_inbound[]`, `branches[]` (each `{rule_ref, next_step}`), `next_steps[]`, `time_bound` (`{duration, on_expiry}`).

Optional on workflow: `counterparty_role`.

### `projections[]`

Required: `id`, `name`, `description`, `source_events[]` (≥1 strings — event type names), `output_schema` (object), `fold_expression` (string).

Optional: `access` (`row_filter_rule_ref`, `lens_template`), `display` (`view_type` ∈ `{table, list, cards, kanban, timeline, summary}`, `columns[]`, `default_sort`, `empty_state`).

### `rules[]`

Required: `id`, `type` ∈ `{legal_prose, behavioral_expectation, business_policy, predicate, computational, validation, binding_link}`, `title`.

Conditional requireds based on `type`:
- `legal_prose`, `behavioral_expectation` → require `body`.
- `predicate`, `computational`, `validation` → require `expression`, `language`.
- `predicate` → require `purpose` (one of: `auth_precondition`, `state_precondition`, `temporal_precondition`, `lifecycle_transition_requires`, `lifecycle_transition_condition`, `workflow_branch_condition`, `aggregate_invariant`, `projection_row_filter`, `derived_membership`).
- `computational` → require `result_attribute`.
- `binding_link` → require `links[]` (each `{rule_id: string}`).

Optional always: `description`.

## First-person mental model (unchanged)

The Overview card grid still maps each primitive to its first-person framing. The labels change slightly to match canonical fields:

| Card | First-person | Card label (Overview) | Doc path |
|---|---|---|---|
| Role | "I am …" | Role | `role` |
| Imports | "I hold …" | Imported credentials | `credentials.imports` |
| Exports | "I issue …" | Issued credentials | `credentials.exports` |
| Commands | "I do …" | Commands | `commands` |
| Reactions | "I respond to …" | Reactions | `reactions` |
| Workflows | "I follow …" | Workflows | `workflows` |
| Aggregates | "I track …" | Aggregates | `aggregates` |
| Projections | "I see …" | Projections | `projections` |
| Rules | "I'm bound by …" | Rules | `rules` |

For each entry, the display-label-of-the-entry logic uses **the first of these that exists**: `display_name`, `name`, `title`, `id`. Use a single helper:

```python
def entry_label(entry: dict) -> str:
    return (entry.get("display_name") or entry.get("name")
            or entry.get("title") or entry.get("id") or "(unnamed)")
```

## Cross-reference reverse index — canonical paths (replaces Task 5 walk)

`compute_crossrefs(doc)` should produce keys of the form `"<kind>:<id>"` for these consumer relationships:

- **Commands** consume:
  - Each `rule_ref` under `commands[i].{auth_preconditions, state_preconditions, temporal_preconditions}` → key `rule:<rule_ref>`.
  - Each `emissions[j].exchange.{imported_credential_id, exported_credential_id, schema_said_referenced}` → keys `import:<id>` / `export:<id>` / `schema:<said>`.
  - Each `emissions[j].exported_credential_id` (lifecycle_advance) → key `export:<id>`.
  - Each `emissions[j].aggregate_id` (aggregate_event) → key `aggregate:<id>`.
- **Exports** consume:
  - Each `envelope.edges[].credential_id` → keys `export:<id>` AND `import:<id>` (emit both since the consumer doesn't know which one).
  - Each `lifecycle.transitions[k].via_workflow` → `workflow:<id>`.
  - Each `lifecycle.transitions[k].condition_rule_ref` → `rule:<id>`.
  - Each `lifecycle.transitions[k].requires[m].rule_ref` → `rule:<id>`.
  - Each `rule_refs[]` → `rule:<id>`.
  - Each `value_flow.implied_credentials[].credential_id` → `export:<id>` and `import:<id>`.
- **Imports** consume: nothing in the canonical schema (the field has no rule_refs).
- **Workflows** consume:
  - Each `steps[].command_id` → `command:<id>`.
  - Each `steps[].reaction_id` → `reaction:<id>`.
  - Each `steps[].advance_lifecycle.credential_id` → `export:<id>`.
  - Each `steps[].expected_inbound[].imported_credential_id` → `import:<id>`.
  - Each `steps[].branches[].rule_ref` → `rule:<id>`.
  - `trigger.credential_id` / `trigger.imported_credential_id` → `export:<id>` / `import:<id>`.
- **Reactions** consume:
  - `trigger.imported_credential_id` → `import:<id>`.
  - `trigger.exported_credential_id` → `export:<id>`.
  - Emissions: same rules as commands (above).
- **Projections** consume:
  - `access.row_filter_rule_ref` → `rule:<id>`.
  - Each `source_events[]` is an **event type name**, not an id. Do not emit a key for it in v1. (Future: a projection consumes the aggregate that emits that event type, but resolving that requires walking aggregates.)
- **Aggregates** consume:
  - Each `invariants[].rule_ref` → `rule:<id>`.
- **Rules** consume:
  - For `type: binding_link`, each `links[].rule_id` → `rule:<id>`.

## Editor right-pane sections (replaces tasks 10-17 inner section lists)

Keep the shell pattern from Task 7. The right pane for each editor shows: **Identity** (id + display label) → **primitive-specific sections** → **JSON view of the entry** (read-only `QPlainTextEdit`, formatted JSON) → **Used-by** chip strip.

The "JSON view of the entry" is the v1 escape hatch for deep nested editing (envelopes, payload schemas, branches, etc.). Editing happens via the top-level `JsonSourceView` (Task 19) or future v2 sub-editors.

Primitive-specific sections (minimum viable; everything else relegated to the JSON view):

- **Commands**: Identity · Route (read-only display) · Counterparty role · Preconditions (count of auth/state/temporal) · Emissions (kind summary) · Used-by.
- **Aggregates**: Identity · Inception event type · Log scope · Invariants count · Used-by.
- **Reactions**: Identity · Trigger summary (`type` + one-line description) · Emissions count · Used-by.
- **Workflows**: Identity · Trigger summary · Roles involved (derived from steps' actors + counterparty_role) · Step list (id + name + actor) · **SwimlaneDiagram** of steps · Used-by.
- **Projections**: Identity · Source events (list) · Fold expression (read-only `QPlainTextEdit`) · Display view type · Used-by. (UEL preview pane: defer to v2 since no evaluator exists; show fold expression text only.)
- **Rules**: Identity · Type (color-coded) · Title · Body (for prose types) OR Expression + Language (for computational types) · Purpose (predicates only) · Used-by.
- **Imports**: Identity · Expected schema SAID · Expected issuer role · Lifecycle acceptance (list) · Narrative · Used-by.
- **Exports**: Identity · Envelope summary (`holder_role` + `disclosure_mode`) · Schema SAID · **StateMachineDiagram** built from `lifecycle.states` + `lifecycle.transitions` (color-coded by `tel_primitive`) · Used-by.

The kind-color logic on rail items unchanged from Task 10 (`_kind_color_for(role.kind)`).

## Test fixtures (replaces all fixture JSON blocks in tasks 8-22)

Use the **existing valid fixtures** as the starting point:

- `tests/micro_app_template/fixtures/minimal_valid_template.json` — minimal valid skeleton; reuse for "empty workspace adds one" tests.
- `tests/micro_app_template/fixtures/credentials_valid.json` — carrier with imports + exports including a full lifecycle. Reuse and rename a copy under `tests/plugins/designer/fixtures/carrier-license-application.json` as needed.

New fixtures the plan asked for (write canonical-schema-valid versions under `tests/plugins/designer/fixtures/`):

- `regulator-grants-carrier-license.json` — government role, one export (the carrier license), one workflow, two rules. Use SAID `EGCpXap_yYxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx6yAv` for visual continuity with the mockups.
- `carrier-license-application.json` — copy of `credentials_valid.json` with `header.display_name` set to "Carrier License Application", retaining its imports+exports shape.
- `broken-references.json` — minimal valid skeleton with one export whose `lifecycle.transitions[0].via_workflow` references a non-existent workflow id, and one command whose `auth_preconditions[0].rule_ref` references a non-existent rule id. The xref validator will flag both; the validation panel should group them.
- `draft-untitled.json` — minimal-shaped doc with `d=""` and `header.id="untitled-draft"`, `header.display_name="Untitled template"`. (Not meta-schema-valid because `d` is empty — that's the point; draft-mode tests assert the store accepts it but the validator reports an issue.)

For tasks that originally inlined fixture JSON in the plan, the subagent should instead **copy from `tests/micro_app_template/fixtures/`** and adapt minimally.

## Per-task delta summary

- **Task 5 (crossref):** Walk follows canonical paths (above). All key formats `<kind>:<id>` unchanged. The test fixtures must use canonical field names (not `rule_refs` on commands — use `auth_preconditions[].rule_ref` etc.).
- **Task 7 (shell):** Unchanged. Schema-agnostic widgets.
- **Task 8 (browser):** Card displays `header.display_name`, `role.display_name`, `role.kind`. Counts derive from `credentials.imports.length` etc.
- **Task 9 (overview):** `entry_label` helper, card labels per the table above. Header strip shows `header.display_name`; role chip shows `role.display_name`.
- **Tasks 10-17 (editors):** Use the section lists above. Add a read-only entry-JSON pane below the structural sections in every editor.
- **Task 18 (validation panel):** Unchanged.
- **Task 19 (JSON view):** Unchanged.
- **Task 20 (dialogs):**
  - `CreateTemplateDialog` collects: template `display_name`, template `id` (auto-slugify from display_name with override), role `display_name`, role `id`, role `kind`. The new template is saved as a draft with all required `header` + `role` fields stamped (`description=""`, `version="0.1"`, `expression_language="UEL/1.0"`; `keri_infrastructure` all-false).
  - `EditHeaderDialog`: edits `display_name`, `description`, `version`, `expression_language`.
  - `EditRoleDialog`: edits `display_name`, `description`, `kind`, four `keri_infrastructure` booleans (checkboxes).
- **Task 21 (plugin wiring):** Unchanged in shape. Plugin loads model from store, passes to overview + editors.
- **Task 22 (README + draft fixture):** Use the canonical draft fixture above.

## Bottom line for subagents

When a subagent's task prompt references a field name from the original plan, the subagent must check this addendum's canonical field map and use the canonical name instead. If a primitive's field is missing from the addendum, the original plan's invented field name is wrong — escalate to the controller.
