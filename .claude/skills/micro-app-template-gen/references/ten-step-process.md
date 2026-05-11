# The Ten-Step Process (Detailed)

Detailed prose for each step of the micro-app template authoring path. The SKILL.md gives a one-line summary per step; this file gives the full context, rationale, and instructions.

## Step 0 — Identify the role

**Goal:** Select the single role this micro-app embodies. Every subsequent step is from this role's perspective.

**Why this is Step 0:** A micro-app captures *one role's slice* of a use case. Multi-actor patterns decompose into multiple templates. Naming the role first prevents scope creep into multi-role territory.

**What to capture:**

| Field | Notes |
|---|---|
| `role.id` | kebab-case stable identifier (e.g., `carrier`, `homeowner`, `state-doi`) |
| `role.display_name` | Title case label for UI ("Insurance Carrier", "Homeowner") |
| `role.description` | One paragraph explaining what this role *is* in the ecosystem |
| `role.kind` | One of: individual, organization, system, device, agent, government |
| `role.keri_infrastructure` | Four boolean flags (witness_pool, watcher_network, mailbox, acdc_registry) |

**Suggesting defaults for `keri_infrastructure`:**

- `individual` → mailbox usually true; witness_pool/watcher_network/acdc_registry usually false
- `organization`, `government` → all four typically true
- `system`, `agent` → mailbox true; others depend on operational scope
- `device` → usually only mailbox

Let the SME override defaults. The flags are deployment-readiness *expectations* — not enforcement.

**Anti-patterns:**

- ❌ Declaring two roles ("carrier and broker") — split into two templates
- ❌ Picking the wrong kind ("carrier is a person") — explain what kinds mean
- ❌ Skipping keri_infrastructure ("I don't know what these mean") — default by kind

**Save:** Write `role` field to the output template. The header (Step 1) hasn't been authored yet; defer the file write until the canonical JSON has at least `header + role`.

## Step 1 — Name the use case

**Goal:** Capture the use case's identity (header) and articulate the pivotal event from this role's perspective.

**Why this matters:** The "pivotal event" is the past-tense fact that defines success. Naming it sharpens the scope and reveals when you're actually trying to model two use cases.

**Questions to ask:**

1. *Outcome statement?* — One sentence in past tense, in the role's voice. "A claim has been filed." "A license has been granted."
2. *Multiple events surfacing?* — If two pivotal events compete, you have two micro-apps. Stop and split.
3. *Version?* — Start at `"1.0"` unless this is explicitly a fork of an existing template (Step 0 already captured the role; the header version is independent).
4. *Forked from?* — If derived from another template, capture the parent's SAID + version + intent.

**Field mapping:**

| Field | Source |
|---|---|
| `header.id` | kebab-case use case identifier (often `<role>-<verb>-<noun>`) |
| `header.display_name` | Title case label |
| `header.description` | The pivotal event statement + 1-2 sentences of context |
| `header.version` | Semver |
| `header.expression_language` | `"UEL/1.0"` (default for now) |
| `header.forked_from` | Optional |

**Save:** Write `header` and `role` fields. The template is now structurally minimal-valid (other primitives are empty arrays).

## Step 2 — Credential imports (the imports list)

**Goal:** Identify the credentials this role must hold for its commands to be authorized.

**Why this comes before exported credentials:** What you import constrains what you can DO. Imported credentials determine the universe of commands available.

**For each imported credential, capture:**

| Field | Notes |
|---|---|
| `id` | Local identifier (used by commands' auth_preconditions) |
| `expected_schema_said` | SAID of the schema; lookup in known templates or note as TBD |
| `expected_issuer_role` | Optional narrowing constraint |
| `expected_attribute_constraints` | Optional type hints |
| `lifecycle_acceptance` | Which lifecycle states make it usable (default `["active"]`) |
| `narrative` | SME tooltip explanation |

**Imports describe types, not instances.** Even if the role has NO active credential of a given type at the moment the micro-app is instantiated, declare the type here. Locksmith determines runtime holdings by observing the wallet's TEL state. The `narrative` field is the conventional place to note "no active instance at start; obtained via [workflow_id]."

**When the SAID isn't yet known:** Note it explicitly. The Ecosystem Viewer will surface dangling imports as candidates for alignment.

**Anti-patterns:**

- ❌ Inventing schema SAIDs — they must be content-addressed
- ❌ Conflating "credentials this role *imports*" with "credentials this role *exports*" — different lists

## Step 3 — Credential exports (the exports list)

**Goal:** Define the credentials this role produces — their envelope, schema, lifecycle, rules, value flow.

**The most substantial step.** Each exported credential has six layers (per spec §6.3).

For each exported credential, walk:

1. **Envelope contract** — who holds it, who verifies it, what it chains from
2. **Schema** — author a JSON-Schema file in `schemas/` and capture its SAID
3. **Lifecycle** — states, initial state, transitions (with `tel_primitive` mapping each transition to issue/update/revoke)
4. **Ricardian rules** — forward-reference rule ids; will be authored in Step 9
5. **Value flow** — references to other credentials implied by this one

**Edge operators:**

| Operator | Meaning |
|---|---|
| `authorizes` | Holder of parent becomes issuer of this credential |
| `references` | Informational pointer; no authority transfer |
| `authorizes-via-delegate` | Issuer is a KEL-delegated AID of parent's holder |

**Lifecycle transitions ground out in TEL primitives:**

- `issue` — TEL issuance event (state becomes active or whatever the initial-active state is)
- `update` — TEL update event (intermediate state change, e.g., active → suspended)
- `revoke` — TEL revocation event

The state machine layered on top can have any names; transitions map each to one of these three TEL primitives.

**Schema authoring side-step:** When you reach the schema for a credential, write a separate JSON-Schema file at `schemas/{credential_id}.json`. Compute its SAID using `python scripts/saidify_acdc_schema.py` (the existing project utility) OR by stamping with the same saidify helper used for the template. Reference both `schema_said` and `schema_path` in the template.

## Step 4 — Commands

**Goal:** Define the actions this role takes. Each command becomes a button in Locksmith.

**For each command:**

1. **Route** — exn route following naming conventions (see `naming-conventions.md`). Must not start with `/ipex/`.
2. **Counterparty role** — who receives this command, if any
3. **Payload schema** — JSON-Schema for the actor's input (Locksmith renders as a form)
4. **Preconditions** — auth (forward-ref rules), state (forward-ref rules), temporal (forward-ref rules)
5. **Idempotency key expression** — UEL over `payload` only (no state, no principal)
6. **Emissions** — what fires on success: exchange (IPEX or exn out), lifecycle_advance (advance a credential's state), aggregate_event (append to a local aggregate)

**Anti-patterns:**

- ❌ Using `/ipex/*` for app-defined commands — reserved for protocol
- ❌ Referencing state or principal in idempotency_key_expression — must be deterministic from payload alone

## Step 5 — Aggregates

**Goal:** Define the local state this role tracks.

Aggregates are typically TEL-backed (when tracking credential lifecycle) or KEL-anchored local logs. For each:

1. **Inception event type** — the event that mints the aggregate's identifier
2. **State schema** — JSON-Schema for the folded state
3. **Initial state** — starting value
4. **Invariants** — forward-ref validation rules
5. **Log scope** — `private` | `witnessed` | `shared`

## Step 6 — Reactions

**Goal:** Define what this role does when it observes external events.

For each reaction:

1. **Trigger** — credential_received (with imported_credential_id + optional ipex_verb), exn_received (with route), lifecycle_event (with credential and state), or scheduled (with cadence)
2. **Emissions** — same shape as command emissions
3. **Failure policy** — `log_and_continue` | `log_and_spurn` | `abort`; optional timeout_seconds

**The subscriber pattern:** Reactions observe events; they don't push to others. The decentralized property.

## Step 7 — Workflows

**Goal:** Name the multi-step external interactions from this role's perspective.

Each workflow is a sequence of self-actions and counterparty-awaits. From this role's POV only — the counterparty's half lives in their own micro-app.

For each:

1. **Counterparty role**
2. **Trigger** — manual (with initiator_role), scheduled, lifecycle_event, exn_received, credential_received
3. **Steps** — ordered list. Each step has: `actor` (self or counterparty), `command_id` or `reaction_id` (for self steps), `expected_inbound` (for counterparty steps), `branches` (rule-conditioned next_step pointers), `next_steps` (unconditional), `time_bound` (duration + on_expiry).

The exchange palette across steps:

- IPEX credential exchange — kind: credential, verb: one of six (apply/offer/agree/grant/admit/spurn)
- exn message — kind: message, pattern: command|query|notification, route
- Internal step — exchange: null

## Step 8 — Projections

**Goal:** Define what this role looks at.

Projections fold events into views. Locksmith renders them.

For each:

1. **Source events** — names of event types to fold
2. **Output schema** — JSON-Schema for the resulting state
3. **Fold expression** — UEL over `{ state, event, source }` producing new state
4. **Access** — row_filter (rule_ref), lens_template
5. **Display** — view_type (table | list | cards | kanban | timeline | summary), columns, default_sort, empty_state

## Step 9 — Rules

**Goal:** Author every rule forward-referenced in Steps 3–8.

**Resolve every forward reference.** Walking the template after Step 9, no rule_ref should point to an undefined id.

For each rule, choose its `type`:

| Type | Body or Expression? | Notes |
|---|---|---|
| `legal_prose` | `body` (markdown) | Ricardian contractual prose |
| `behavioral_expectation` | `body` (markdown) | Prose-only obligation |
| `business_policy` | both `body` and `expression` allowed | Hybrid prose + formal |
| `predicate` | `expression` + `language` + `purpose` | Executable boolean |
| `computational` | `expression` + `language` + `result_attribute` | Derived value |
| `validation` | `expression` + `language` | Constraint check |
| `binding_link` | `links[]` | Connects prose to executable |

See `rule-types-reference.md` for detailed guidance per type.

## Step 10 — Conventions, hints, lineage (metadata.json)

**Goal:** Produce the optional sibling `metadata.json` with non-canonical viewer color.

1. **Convention compliance audit** — for each category (credential_naming, role_naming, workflow_naming, etc.), record whether the template complies with conventions or where it deviates with rationale
2. **Ecosystem affinity** — kebab-case tags suggesting which emergent ecosystems this template belongs to
3. **Semantic lineage** — optional refines/improves/inspired_by/competes_with/obsoletes relations to other templates
4. **Author intent notes** — free text the viewer can surface
5. **Compatibility hints** — compatible_with and incompatible_with lists

**Save:** Write `metadata.json` alongside `micro-app-template.json`. Set `for_micro_app_said` to the template's SAID (computed in the saidify step below).

## Adversarial review (informal)

Walk the adversarial checklist (see `adversarial-prompts.md`). Document concerns in `metadata.author_intent_notes` or as out-of-band notes.

## Save and saidify

1. Run `scripts/micro_app_validate.py --input <path>` — must pass.
2. Run `scripts/micro_app_saidify.py --input <path> --in-place` — stamps the `d` field.
3. Re-run validate to confirm SAID is now correct.
4. Update `metadata.json` `for_micro_app_said` to the new SAID.
5. Commit the entire directory.
