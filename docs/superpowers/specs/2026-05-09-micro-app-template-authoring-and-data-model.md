# Micro-App Template Authoring and Data Model

**Date:** 2026-05-09
**Status:** Design spec (pre-implementation)

## 1. Goal and scope

A **micro-app** is the smallest deployable unit of a KERI-native application: a single role's slice of operational behavior in some ecosystem. A homeowner-claims micro-app captures *the homeowner's side* of filing a claim. A regulator-licensing micro-app captures *the regulator's side* of granting and revoking licenses. The same business pattern decomposes across roles into multiple micro-apps; the bilateral conversation between them lives in the protocol, not in any single artifact.

A **micro-app template** is the JSON artifact that fully describes one micro-app: which role it embodies, what credentials it holds and issues, what commands and reactions it performs, what local state it tracks, what views it surfaces, and what rules govern all of it. The template is the contract a KERI wallet (Locksmith) reads to render and run a deployed micro-app.

This spec defines that template's **format, vocabulary, primitives, conventions, and supporting sibling metadata**. It is the contract between the artifact's producers (authoring tools) and consumers (the Locksmith wallet, the Designer plugin, the Ecosystem Viewer plugin, any future tooling).

**In scope:**

- The canonical JSON shape of `micro-app-template.json` and the SAID self-identification rules
- The 8 primitives a micro-app template captures
- The naming conventions recommended for cross-micro-app alignment
- The sibling `metadata.json` format for non-canonical viewer color
- A meta-schema requirement (delivered as a follow-on artifact derived from this spec)
- A non-prescriptive 10-step authoring path (Appendix A) which the `micro-app-template-gen` skill follows

**Explicitly out of scope:**

- The implementation of any specific authoring tool (skill, plugin, CLI)
- The UI of the `Micro App: Designer` plugin
- The `Micro App: Ecosystem Viewer` plugin
- Higher-Order Applications (HOAs) composed from micro-apps
- Locksmith wallet primitive upgrades (signing, OOBI, IPEX transport) — assumed already present
- Micro-app deployment, hosting, distribution, lifecycle
- The semantics of any specific industry domain (insurance, healthcare, etc.) — the spec is domain-agnostic

The spec is intentionally narrow: it defines *the artifact*. Three different consumers can build on top of it independently.

## 2. The three-artifact picture

This spec is the contract among three artifacts that consume or produce the micro-app template:

| Artifact | Type | Role |
|---|---|---|
| **`micro-app-template-gen`** | Claude skill | Conversational authoring path. Walks an SME or AI agent through producing a `micro-app-template.json` + `metadata.json`. Lives at `.claude/skills/micro-app-template-gen/SKILL.md`. |
| **`Micro App: Designer`** | Locksmith plugin | Viewer/editor over `micro-app-template.json` files. Direct manipulation — open, edit any primitive, validate, save, fork. Does not impose an authoring sequence. |
| **`Micro App: Ecosystem Viewer`** | Locksmith plugin | Reads the corpus of templates the wallet knows about (locally + via OOBI). Renders the emergent ecosystem view by clustering on SAID and naming convention. Surfaces competing implementations. |

The artifact format defined in this spec is the **shared contract**. Anyone may author a template by hand, by skill, by the Designer plugin, by a future AI agent, by an externally-generated tool. All paths produce conforming JSON; all consumers read it equivalently.

The skill and the two plugins are each separate projects outside this spec. Their implementations follow once the spec is locked.

## 3. Architecture

### 3.1 Micro-app template = unit of authoring

A micro-app template captures **one role's perspective on one use case**. If a real-world pattern involves multiple roles (a regulator and a carrier in a licensing flow), that pattern decomposes into **multiple templates** — one per role. The carrier's licensing-application micro-app and the regulator's licensing-grant micro-app are separate artifacts, independently deployable, that compose at runtime through KERI-native message exchange.

This is the decentralized constraint expressed at the authoring layer: no artifact owns the bilateral conversation. Each role authors its own half.

### 3.2 Locksmith as universal runner

Locksmith already implements the KERI wallet primitives: KEL maintenance, TEL observation, ACDC handling, IPEX transport, OOBI discovery, signing. A deployed micro-app **inherits these primitives by being KERI-native**. The template describes *which* messages a role sends and observes, *which* credentials it holds and issues, *which* state it tracks; Locksmith's existing primitives transport, sign, verify, store.

The template does not specify low-level wallet behavior. It assumes Locksmith. If Locksmith lacks some wallet primitive (a missing IPEX flow, a missing transport, a missing UI shell), that is a separate upgrade project, not a template concern.

The template is **domain-agnostic**: the same Locksmith shell renders an insurance micro-app, a healthcare micro-app, a coop governance micro-app, because the template's primitives are domain-agnostic. Locksmith reads the template's *shapes* (commands, projections, workflows) and renders them through universal UI patterns (buttons, lists, dashboards, notifications) regardless of the credentials' subject matter.

### 3.3 Ecosystem = emergent view, not authored artifact

There is no `ecosystem.json`. The ecosystem is the *projection* the Ecosystem Viewer plugin computes over the corpus of micro-app templates the wallet knows about. When two templates reference the same credential SAID, they are content-aligned. When two templates name credentials following the same convention but with different SAIDs, they are convention-aligned (suggested compatibility). The viewer renders both forms of alignment, plus the divergences and competing implementations.

This means the catalog grows by *publication*. Authoring a new micro-app and making it discoverable (via OOBI or local registration) adds to the emergent ecosystem. No central registry; no curator's permission; no top-down catalog.

## 4. Vocabulary

The spec uses these labels. Where a KERI-native term has a colloquial alternative, the spec prefers the colloquial one for SME accessibility; the underlying protocol concepts remain unchanged.

| Concept | Label in this spec | What it maps to in KERI |
|---|---|---|
| Participants | **Roles** | Categories of AIDs by intrinsic kind |
| Participant intrinsic kind | **Participant Type** | None — orthogonal to AID; the *kind of thing* the AID represents (individual, organization, system, device, agent, government) |
| Credential type definition | **Credential** | ACDC type — envelope contract + schema |
| Multi-step exchange | **Workflow** | A composition of IPEX moves and exn messages over time, from one role's perspective |
| Per-credential state machine | **Lifecycle** | TEL-backed state transitions (issue / update / revoke) with custom states layered on top |
| Authority hierarchy | **Authority** | KEL delegation + chained credentials forming trust topology |
| Derived / synthesized credential | **Derived Credential** | Projection-driven ACDC issuance — folds prior events into a new credential |
| Cross-ecosystem references | **Bridges** | Shared credentials across template populations |
| Authored rules | **Rules** | Typed clauses (legal prose, predicates, computations, validations, behavioral expectations) |
| Signed message envelope | (hidden in UI) | exn — KERI's general peer-message format |
| Credential exchange protocol | (hidden in UI; verbs surfaced) | IPEX — uses six verbs: apply, offer, agree, grant, admit, spurn |

The labels "IPEX" and "AID" do not appear in user-facing surfaces of conforming tools; their semantics surface through the verbs (apply, offer, grant, admit, spurn) and the Roles/Participant Type vocabulary above.

## 5. The canonical artifact: `micro-app-template.json`

### 5.1 Shape

A single JSON document with:

```json
{
  "d": "EAbc...defGHI789...",
  "spec_version": "micro-app-template/0.1",
  "header": { ... },
  "role": { ... },
  "credentials": {
    "imports": [ ... ],
    "exports": [ ... ]
  },
  "commands": [ ... ],
  "aggregates": [ ... ],
  "reactions": [ ... ],
  "workflows": [ ... ],
  "projections": [ ... ],
  "rules": [ ... ]
}
```

The eight primitives (header, role, credentials, commands, aggregates, reactions, workflows, projections, rules) are detailed in §6.

### 5.2 SAID self-identification

The top-level `d` field is the SAID of the document, computed via the same saidification recipe ACDC schemas use:

1. Set `d` to a placeholder of the appropriate length for the chosen digest algorithm (44 characters for Blake3-256).
2. Canonicalize the document — sorted keys, UTF-8 encoding, no extraneous whitespace, JSON form.
3. Hash the canonical form to produce the SAID.
4. Replace the placeholder in `d` with the computed SAID.

Anyone with the document can verify integrity by repeating steps 1–3 on the document with `d` replaced by its placeholder and comparing the result to the stored `d` value.

The SAID alone proves integrity (this exact content). It does not prove authorship. Endorsement — "this template was authored by AID X" — is an optional layer above the template: an issuer signs an ACDC of type `MicroAppTemplateEndorsement` whose payload references the template's SAID, anchored in the issuer's KEL. The template stands on its own SAID; endorsements are credentials *about* the template.

### 5.3 JSON canonical form, no YAML

The canonical artifact is JSON. The same JSON is both the stored form and the exchange form — no separate canonicalization step is required for SAID computation, because the file is already canonical.

The canonical form rules:

- Top-level keys sorted lexicographically (and nested object keys, recursively).
- UTF-8 encoding.
- No comments (JSON forbids them; commentary lives in `description` and similar fields).
- Whitespace: pretty-printed for readability is the human-facing form; the canonical form for SAID computation is the same JSON re-serialized with deterministic spacing (sorted keys, two-space indent, single newline at EOF — the choice is fixed by the meta-schema's canonicalizer reference).

A YAML rendering layer may exist as a post-MVP transformation for hand-authors who prefer YAML; it is read-only conversion to/from canonical JSON and is not part of the spec's normative shape.

### 5.4 Round-trip and lint requirements

Conforming tools must:

- **Parse** a `micro-app-template.json` and validate it against the meta-schema (§5.6).
- **Verify** the document's `d` value by recomputing the SAID and comparing.
- **Re-serialize** the document to canonical JSON (sorted keys, deterministic spacing) without semantic loss.
- **Validate** that all references (SAIDs, rule_refs, credential ids, role id, etc.) resolve to declared targets.

A round-trip is **lossless** when a tool reads, parses, re-serializes, and the resulting document is byte-identical to the canonical form of the original. The meta-schema's canonicalizer must produce stable output across implementations.

### 5.5 Meta-schema

A separate JSON Schema document (delivered as a follow-on artifact derived from this spec) describes the shape of `micro-app-template.json`. The meta-schema is the formal validator. Its `$id` is the SAID of its own canonical form. Conforming tools may bundle the meta-schema or fetch it by SAID.

The meta-schema artifact is the deliverable of a follow-on implementation task. This spec describes the shape it must encode; the schema document itself is generated from this spec's primitive definitions.

### 5.6 File layout

A typical micro-app template directory:

```
my-micro-app/
├── micro-app-template.json    # canonical artifact (SAID-self-identifying)
├── metadata.json              # sibling viewer color (optional; non-canonical; §9)
└── schemas/                   # JSON-Schema files for exported credentials (§6.3)
    ├── carrier_license.json
    ├── policy.json
    └── ...
```

Schema files are referenced by SAID + relative path from the template (§6.3). They live alongside the template, content-addressed, and the template carries the SAID of each. The directory is the unit of distribution.

## 6. The eight primitives

Every micro-app template declares exactly these primitives. Primitives are required unless marked optional.

### 6.1 Header

Identifies the template, captures its narrative purpose, tracks lineage.

```json
{
  "header": {
    "id": "carrier-license-application",
    "display_name": "Carrier License Application",
    "description": "A carrier applies to a state regulator for licensure to bear insurance risk, manages the resulting license credential, and responds to lifecycle events on it.",
    "version": "1.0",
    "expression_language": "UEL/1.0",
    "forked_from": {
      "template_said": "EHsh...",
      "template_version": "0.9",
      "forked_at": "2026-05-09",
      "fork_intent": "Adapted for surplus-lines carriers; relaxed state-of-domicile attribute."
    }
  }
}
```

- `id` (required) — kebab-case stable identifier; used as a key by other primitives
- `display_name`, `description` (required) — UI strings; `description` is the SME's narrative of what this micro-app does
- `version` (required) — semver-style; bumped on every published change
- `expression_language` (required when the template uses executable rules; recommended default `UEL/1.0`) — version of the predicate / computation language used by `rules[].expression`
- `forked_from` (optional) — populated if this template descends from another; tracks parent SAID, parent version, and the author's stated intent for the fork

### 6.2 Role

The single role this micro-app embodies. Every other primitive operates from this role's perspective.

```json
{
  "role": {
    "id": "carrier",
    "display_name": "Insurance Carrier",
    "description": "Licensed risk-bearing entity that underwrites and issues policies, bears liability, manages reinsurance.",
    "kind": "organization",
    "keri_infrastructure": {
      "witness_pool": true,
      "watcher_network": true,
      "mailbox": true,
      "acdc_registry": true
    }
  }
}
```

- `id` (required) — kebab-case, used as a reference target by all other primitives and by other templates' counterparty references
- `display_name`, `description` (required) — UI strings
- `kind` (required) — one of: `individual`, `organization`, `system`, `device`, `agent`, `government`. The kind is intrinsic to what the AID represents; it does not change across ecosystems.
- `keri_infrastructure` (required) — declarative flags describing what KERI infrastructure this role expects to have available:
  - `witness_pool` — operates witnesses for its own KEL
  - `watcher_network` — watches others' KELs
  - `mailbox` — has an always-on endpoint for offline message reception (implementation-agnostic: witness mailbox, personal relay, fat-client daemon, IPFS pin, etc.)
  - `acdc_registry` — operates one or more credential registries (TELs)

The kind suggests defaults for `keri_infrastructure` (e.g., `organization` typically has all four; `individual` often has only `mailbox`), but the SME may override.

Only one role is declared per template. Counterparty roles referenced elsewhere (in `credentials.imports[].issuer_role`, `commands[].counterparty_role`, etc.) are referred to by id only and resolved against the emergent ecosystem at render time.

### 6.3 Credentials — imports and exports

Credentials this role interacts with, split into two lists by direction.

**Imports** — credentials this role must hold to perform commands.

```json
{
  "credentials": {
    "imports": [
      {
        "id": "carrier_license",
        "expected_schema_said": "EAuthorityIssuedSchemaSAID...",
        "expected_issuer_role": "regulator",
        "expected_attribute_constraints": {
          "jurisdiction": { "type": "string" }
        },
        "lifecycle_acceptance": ["active"],
        "narrative": "Holding a license credential from a state regulator is the precondition for binding policies."
      }
    ],
    "exports": [ ... ]
  }
}
```

Each imported credential entry declares the *expectation*. The actual credential is observed at runtime from the wallet's TEL views. Fields:

- `id` (required) — local identifier used by commands and rules to reference this expectation
- `expected_schema_said` (required) — content-addressed schema identity that this micro-app expects to find on credentials it holds. This is the **imports SAID** that the Ecosystem Viewer matches against other templates' `exports[].schema_said`.
- `expected_issuer_role` (optional) — narrowing constraint: only accept credentials issued by AIDs in this role
- `expected_attribute_constraints` (optional) — soft type constraints on credential attributes (for validation at use time)
- `lifecycle_acceptance` (optional) — which lifecycle states make this credential usable (default: `["active"]`)
- `narrative` (optional) — SME explanation surfaced in UI tooltips

**Imports describe credential types, not instances.** Each entry in `credentials.imports[]` declares a credential *type* this role is expected to potentially hold (per its `expected_schema_said`, `expected_issuer_role`, etc.). Whether the role currently holds a credential of that type is a *runtime* concern that Locksmith determines by observing the wallet's TEL state — it is not asserted by the template. A role at the start of its lifecycle (e.g., a newly-instantiated carrier before licensure) declares the credential types its commands and reactions will reference, even when no instance exists yet. The `narrative` field is the conventional place to record "no active instance at instantiation; will be obtained via the license_application workflow."

**Exports** — credentials this role produces.

```json
{
  "credentials": {
    "imports": [ ... ],
    "exports": [
      {
        "id": "policy",
        "name": "Policy Credential",
        "description": "Insurance policy binding terms between carrier and policyholder.",
        "envelope": {
          "holder_role": "policyholder_individual",
          "verifier_roles": ["broker", "claims_adjuster", "regulator"],
          "edges": [
            {
              "edge_name": "authority",
              "credential_id": "carrier_license",
              "cardinality": "one",
              "operator": "authorizes"
            }
          ],
          "disclosure_mode": "selective"
        },
        "schema": {
          "schema_said": "EAbc...PolicySchemaSAID...",
          "schema_path": "schemas/policy.json"
        },
        "lifecycle": {
          "states": ["pending", "active", "expired", "cancelled", "revoked"],
          "initial": "pending",
          "transitions": [
            {
              "id": "activate",
              "from": "pending",
              "to": "active",
              "via_workflow": "policy_issuance",
              "tel_primitive": "issue",
              "requires": [{ "rule_ref": "premium_paid" }]
            },
            {
              "id": "expire",
              "from": "active",
              "to": "expired",
              "trigger": "automatic",
              "condition_rule_ref": "policy_term_elapsed",
              "tel_primitive": "update"
            },
            {
              "id": "cancel",
              "from": ["pending", "active"],
              "to": "cancelled",
              "via_workflow": "policy_cancellation",
              "tel_primitive": "update"
            },
            {
              "id": "revoke",
              "from": ["active"],
              "to": "revoked",
              "via_workflow": "policy_revocation",
              "tel_primitive": "revoke"
            }
          ]
        },
        "rule_refs": ["policy_warranty", "policy_premium_calculation"],
        "value_flow": {
          "implied_credentials": [
            {
              "credential_id": "commission_record",
              "relationship": "per_emission",
              "description": "Each policy emission produces a commission record for the producer."
            }
          ]
        }
      }
    ]
  }
}
```

Each exported credential has six logical layers, surfaced as nested fields:

- **`id`, `name`, `description`** — local identity and human-readable strings
- **`envelope`** — the contract: who holds (`holder_role`), who verifies (`verifier_roles`), chain references (`edges`), disclosure semantics (`disclosure_mode`)
  - `edges[]` — list of named chain references; each has `edge_name`, `credential_id`, `cardinality` (`one` | `one_or_more`), `operator`:
    - `authorizes` — holder of parent credential becomes issuer of this credential; authority is passed down through issuance. (KERI-native: I2I.)
    - `references` — informational reference, no authority transfer. (KERI-native: NI2I.)
    - `authorizes-via-delegate` — issuer of this credential is a KEL-delegated AID of the parent's holder. (KERI-native: DI2I.)
  - `disclosure_mode` — `full` (entire credential visible) | `selective` (per-field selective disclosure; annotations in the schema file) | `aggregate` (only aggregated values disclosable)
- **`schema`** — the JSON-Schema definition by reference: `schema_said` (content-addressed identity) + `schema_path` (relative path to the schema file in `schemas/`). The schema file is itself a JSON-Schema document with KERI/ACDC extensions (selective-disclosure annotations, edge block, etc.). Schema content is verified by re-saiding and comparing to `schema_said`.
- **`lifecycle`** — state machine for this credential type:
  - `states[]` — list of named states (any names the SME wants)
  - `initial` — starting state
  - `transitions[]` — each has `id`, `from` (string or array), `to`, optional `via_workflow` (manual transition driven by a workflow step), optional `trigger: "automatic"` and `condition_rule_ref` (automatic transition fired by rule evaluation), required `tel_primitive` (one of `issue`, `update`, `revoke`), optional `requires` (array of `rule_ref` objects). The `tel_primitive` is the mapping from abstract state to KERI substrate.
- **`rule_refs`** — array of rule identifiers (declared in §6.9) attached to this credential (Ricardian clauses, validations, computations, behavioral expectations)
- **`value_flow`** (optional) — documents economic/authority relationships implied by this credential:
  - `implied_credentials[]` — references to other credentials (in this template's exports list OR imported from elsewhere) with named `relationship` semantics. Supported `relationship` values: `issuer_grants` (holder of this credential is empowered to issue the named credential), `per_emission` (each emission of this triggers an instance of the named credential), `per_holder_emission` (each emission by this holder triggers an instance), `implies_obligation` (holding this creates an obligation expressed via the named credential).

### 6.4 Commands

The actions this role takes — buttons in the Locksmith UI, exn messages on the wire.

```json
{
  "commands": [
    {
      "id": "submit_application",
      "name": "Submit License Application",
      "description": "Submit a new license application to a state regulator.",
      "route": "/insurance/cmd/submit_application",
      "counterparty_role": "regulator",
      "payload_schema": {
        "type": "object",
        "properties": {
          "jurisdiction": { "type": "string" },
          "lines_of_business": { "type": "array", "items": { "type": "string" } },
          "effective_date_requested": { "type": "string", "format": "date" }
        },
        "required": ["jurisdiction", "lines_of_business"]
      },
      "auth_preconditions": [],
      "state_preconditions": [
        { "rule_ref": "no_active_license_for_jurisdiction" }
      ],
      "temporal_preconditions": [],
      "idempotency_key_expression": "hash(payload.jurisdiction + payload.lines_of_business)",
      "emissions": [
        {
          "kind": "exchange",
          "exchange": {
            "kind": "credential",
            "verb": "apply",
            "imported_credential_id": null,
            "exported_credential_id": null,
            "schema_said_referenced": "EAbc...CarrierLicenseSchemaSAID..."
          }
        }
      ]
    }
  ]
}
```

Each command has:

- `id`, `name`, `description` — local identity and UI strings
- `route` (required) — exn route this command's message uses (see §8 for naming conventions)
- `counterparty_role` (optional) — id of the role this command targets; null for self-only commands
- `payload_schema` (required) — JSON-Schema describing the command's input fields (what the actor supplies). Locksmith renders this as a form.
- `auth_preconditions[]` — array of `rule_ref` objects, each pointing to a `predicate` rule that gates authorization. Typically these check that the actor holds particular credentials.
- `state_preconditions[]` — array of `rule_ref` objects, each pointing to a `predicate` rule evaluated over the role's aggregates' state.
- `temporal_preconditions[]` — array of `rule_ref` objects, each pointing to a `predicate` rule evaluated against time.
- `idempotency_key_expression` (required) — UEL expression over `payload` only (no state, no principal) that produces a stable hash. Locksmith uses this to deduplicate retries.
- `emissions[]` — what events fire when the command succeeds. Each emission is either:
  - `kind: "exchange"` — an outbound exn message. The `exchange` object follows §6.7's shape (credential/message/null kinds).
  - `kind: "lifecycle_advance"` — advances a credential's lifecycle. The `lifecycle_advance` object has `exported_credential_id` and `to_state`.
  - `kind: "aggregate_event"` — appends an event to one of the role's aggregates. The object has `aggregate_id`, `event_type`, `payload_mapping` (UEL expression mapping command payload + state to event payload).

### 6.5 Aggregates

The role's local state — what it tracks across its history.

```json
{
  "aggregates": [
    {
      "id": "license_registry",
      "description": "The carrier's history of license credentials held and their lifecycle events.",
      "inception_event_type": "license_received",
      "state_schema": {
        "type": "object",
        "properties": {
          "active_licenses": {
            "type": "array",
            "items": { "type": "object" }
          },
          "expired_licenses": {
            "type": "array",
            "items": { "type": "object" }
          }
        }
      },
      "initial_state": {
        "active_licenses": [],
        "expired_licenses": []
      },
      "invariants": [
        { "rule_ref": "no_duplicate_active_license" },
        { "rule_ref": "expired_licenses_are_immutable" }
      ],
      "log_scope": "private"
    }
  ]
}
```

- `id`, `description` — local identity and SME narrative
- `inception_event_type` — name of the event that mints this aggregate's identifier (which is usually a TEL identifier)
- `state_schema` — JSON-Schema for the aggregate's folded state
- `initial_state` — the starting state used when no events have folded yet
- `invariants[]` — array of `rule_ref` objects pointing to `validation` rules; the aggregate enforces these between fold and append
- `log_scope` — `private` (local-only, no witnesses), `witnessed` (KEL-anchored, witnessed), `shared` (multi-party log)

Aggregates are typically backed by TELs at the protocol level (when tracking credential lifecycle) or by KEL-anchored local logs (when tracking domain state).

### 6.6 Reactions

What this role does when it observes an event it didn't initiate.

```json
{
  "reactions": [
    {
      "id": "on_license_granted",
      "description": "When a license credential is granted to us by the regulator, admit it and advance our local aggregate.",
      "trigger": {
        "type": "credential_received",
        "imported_credential_id": "carrier_license",
        "ipex_verb": "grant"
      },
      "emissions": [
        {
          "kind": "exchange",
          "exchange": {
            "kind": "credential",
            "verb": "admit",
            "imported_credential_id": "carrier_license"
          }
        },
        {
          "kind": "aggregate_event",
          "aggregate_id": "license_registry",
          "event_type": "license_received",
          "payload_mapping": "{ said: event.credential.said, jurisdiction: event.credential.attributes.jurisdiction, effective: event.credential.attributes.effective_date }"
        }
      ],
      "failure_policy": {
        "on_validation_failure": "log_and_spurn",
        "timeout_seconds": null
      }
    }
  ]
}
```

- `id`, `description` — local identity and SME narrative
- `trigger` — the event pattern this reaction matches. `type` is one of:
  - `credential_received` — an inbound IPEX-borne credential. Sub-fields: `imported_credential_id` (matches against `credentials.imports`), `ipex_verb` (which verb the inbound message was — `apply`, `offer`, `grant`, etc.)
  - `exn_received` — an inbound non-IPEX exn message. Sub-fields: `route` (the exn route pattern), `schema_id` (optional payload schema match)
  - `lifecycle_event` — a local credential's lifecycle transitioned. Sub-fields: `exported_credential_id` (or `imported_credential_id`), `to_state`
  - `scheduled` — a timer fired. Sub-fields: `cadence` (cron-style) or `at` (specific datetime)
- `emissions[]` — same shape as command emissions (§6.4)
- `failure_policy` — what to do if the reaction's emissions can't complete. `on_validation_failure`: `log_and_continue` | `log_and_spurn` | `abort`. `timeout_seconds`: maximum time to wait for downstream completion before deeming the reaction failed (null for no timeout).

Reactions are the subscriber pattern. The role observes events it didn't initiate and decides what to do locally. There is no central orchestrator pushing reactions.

### 6.7 Workflows

This role's external interactions over time — named sequences of commands and reactions, from this role's perspective only.

```json
{
  "workflows": [
    {
      "id": "license_application_carrier_side",
      "name": "License Application (Carrier's perspective)",
      "description": "Carrier's half of the bilateral license-application conversation with a state regulator.",
      "counterparty_role": "regulator",
      "trigger": {
        "type": "manual",
        "initiator_role": "carrier"
      },
      "steps": [
        {
          "id": "submit",
          "name": "Submit Application",
          "actor": "self",
          "command_id": "submit_application",
          "next_steps": ["await_response"]
        },
        {
          "id": "await_response",
          "name": "Await Regulator Decision",
          "actor": "counterparty",
          "expected_inbound": [
            {
              "trigger_type": "credential_received",
              "imported_credential_id": "carrier_license",
              "ipex_verb": "grant",
              "on_match": "next_step:admit"
            },
            {
              "trigger_type": "credential_received",
              "ipex_verb": "spurn",
              "on_match": "next_step:rejected"
            }
          ],
          "time_bound": {
            "duration": "30 days",
            "on_expiry": "next_step:timeout"
          }
        },
        {
          "id": "admit",
          "name": "Accept License",
          "actor": "self",
          "reaction_id": "on_license_granted"
        },
        {
          "id": "rejected",
          "name": "Application Rejected",
          "actor": "self",
          "advance_lifecycle": null
        },
        {
          "id": "timeout",
          "name": "Application Timed Out",
          "actor": "self"
        }
      ]
    }
  ]
}
```

Each workflow has:

- `id`, `name`, `description` — local identity and SME narrative
- `counterparty_role` (optional) — id of the primary counterparty; null for self-only workflows
- `trigger` — what starts the workflow:
  - `type: "manual"` with `initiator_role` — a user explicitly starts it
  - `type: "scheduled"` with `cadence` — runs on a schedule
  - `type: "lifecycle_event"` with credential and state — starts when a credential transitions
  - `type: "exn_received"` with route — starts when an inbound message arrives
  - `type: "credential_received"` with imported credential id and verb — starts when a credential is received
- `steps[]` — ordered (by `next_steps` references) list of steps. Each step has:
  - `id`, `name` — local identity and UI label
  - `actor` — `self` (this role acts) or `counterparty` (we await the counterparty's action)
  - For `actor: "self"`: `command_id` or `reaction_id` (which command or reaction this step invokes), `advance_lifecycle` (optional lifecycle advancement)
  - For `actor: "counterparty"`: `expected_inbound[]` — list of expected message patterns and what to do on match (`on_match: "next_step:<step_id>"`)
  - `next_steps[]` — linear, fan-out, or none; for branches, use `expected_inbound` matches or step-level `branches[]` with `rule_ref` conditions
  - `time_bound` (optional) — duration limit with `on_expiry: "next_step:<step_id>"`

Workflows from this role's perspective only. The counterparty has their own workflow in their own micro-app template. The bilateral conversation emerges at runtime from both templates running in coordination.

The exchange palette across all steps:

- **Credential exchange (IPEX):** `kind: "credential"`, with `verb ∈ {apply, offer, agree, grant, admit, spurn}` and `imported_credential_id` or `exported_credential_id` reference
- **Message exchange (exn):** `kind: "message"`, with `pattern ∈ {command, query, notification}` and `route` and optional `schema_id`
- **Internal step (no exchange):** `exchange: null`

### 6.8 Projections

Read-side views this role uses to do its job — what Locksmith renders for the user.

```json
{
  "projections": [
    {
      "id": "my_active_policies",
      "name": "Active Policies",
      "description": "List of policies this carrier currently has in force.",
      "source_events": ["policy_issued", "policy_expired", "policy_cancelled", "policy_revoked"],
      "output_schema": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "policy_said": { "type": "string" },
            "holder_aid": { "type": "string" },
            "jurisdiction": { "type": "string" },
            "effective_date": { "type": "string", "format": "date" },
            "expiration_date": { "type": "string", "format": "date" }
          }
        }
      },
      "fold_expression": "source == 'policy_issued' ? state + [{ policy_said: event.payload.said, holder_aid: event.payload.holder, jurisdiction: event.payload.jurisdiction, effective_date: event.payload.effective, expiration_date: event.payload.expiration }] : source == 'policy_expired' ? state.filter(p => p.policy_said != event.payload.policy_said) : source == 'policy_cancelled' ? state.filter(p => p.policy_said != event.payload.policy_said) : source == 'policy_revoked' ? state.filter(p => p.policy_said != event.payload.policy_said) : state",
      "access": {
        "row_filter_rule_ref": "principal_is_self_carrier",
        "lens_template": "Active Policies — {state.length} in force"
      },
      "display": {
        "view_type": "table",
        "columns": [
          { "field": "policy_said", "header": "Policy", "display_template": "{value|aid8}" },
          { "field": "holder_aid", "header": "Holder", "display_template": "{value|aid8}" },
          { "field": "jurisdiction", "header": "State" },
          { "field": "effective_date", "header": "Effective", "display_template": "{value|date}" },
          { "field": "expiration_date", "header": "Expires", "display_template": "{value|date}" }
        ],
        "default_sort": { "column": "effective_date", "direction": "desc" },
        "empty_state": "No policies in force."
      }
    }
  ]
}
```

- `id`, `name`, `description` — local identity and UI strings
- `source_events[]` — event types this projection folds over
- `output_schema` — JSON-Schema for the projection's resulting state
- `fold_expression` — UEL expression over `{ state, event, source }` producing the new state on each event
- `access` — read-side access control. `row_filter_rule_ref` points to a `predicate` rule evaluated per row against the principal. `lens_template` is a UEL template producing a per-principal label.
- `display` — Locksmith UI hints:
  - `view_type` — `table` | `list` | `cards` | `kanban` | `timeline` | `summary`
  - `columns[]` (for table view) — field, header, display template (with pipes like `|aid8`, `|date`, `|schemaName`)
  - `default_sort`, `empty_state`, and other view-specific hints

Projections drive what Locksmith shows. They are local to this role — application-internal read models that the role consults to make decisions. Cross-role projections do not exist; if another role needs to see this data, they query for it via exn (the data flows over the wire; no shared projection store).

### 6.9 Rules

The typed cross-cutting rule layer. Rules are referenced by `rule_ref` from anywhere else in the template.

```json
{
  "rules": [
    {
      "id": "policy_warranty",
      "type": "legal_prose",
      "title": "Coverage Warranty",
      "body": "Carrier warrants that coverage attaches on the effective date stated in the policy attributes, subject to receipt of premium per the schedule."
    },
    {
      "id": "premium_paid",
      "type": "predicate",
      "purpose": "lifecycle_transition_requires",
      "language": "UEL/1.0",
      "expression": "state.premium_payments.exists(p => p.policy_said == event.policy_said && p.amount >= event.policy.premium)",
      "title": "Premium has been paid",
      "description": "The premium payment record exists for this policy with at least the policy's required amount."
    },
    {
      "id": "policy_premium_calculation",
      "type": "computational",
      "language": "UEL/1.0",
      "expression": "attributes.base_rate * attributes.risk_multiplier * attributes.term_months / 12",
      "result_attribute": "attributes.premium",
      "title": "Premium calculation",
      "description": "Premium is base_rate × risk_multiplier × term_months ÷ 12."
    },
    {
      "id": "no_duplicate_active_license",
      "type": "validation",
      "language": "UEL/1.0",
      "expression": "state.active_licenses.filter(l => l.jurisdiction == event.payload.jurisdiction).length <= 1",
      "title": "At most one active license per jurisdiction",
      "description": "Carrier may not hold multiple active licenses for the same jurisdiction simultaneously."
    },
    {
      "id": "compliance_obligation",
      "type": "behavioral_expectation",
      "title": "Ongoing Compliance",
      "body": "Carrier maintains actuarially-certified solvency reserves and submits annual filings to the regulator within 90 days of fiscal year end."
    },
    {
      "id": "warranty_articulation",
      "type": "binding_link",
      "links": [
        { "rule_id": "policy_warranty" },
        { "rule_id": "premium_paid" }
      ],
      "description": "The Coverage Warranty prose articulates what the Premium Paid predicate enforces."
    },
    {
      "id": "principal_is_self_carrier",
      "type": "predicate",
      "purpose": "projection_row_filter",
      "language": "UEL/1.0",
      "expression": "row.holder_aid == principal.aid || principal.holds_credential('carrier_license', { state: 'active' })",
      "title": "Self-or-licensed carrier may view"
    }
  ]
}
```

Each rule has:

- `id` (required) — referenced by `rule_ref` from elsewhere
- `type` (required) — one of:
  - `legal_prose` — Ricardian contractual prose; `body` field; rendered as markdown
  - `behavioral_expectation` — prose-only obligation; `body` field; not cryptographically enforceable
  - `business_policy` — declarative business rule; may have both `body` (prose) and `expression` (formal restatement)
  - `predicate` — executable boolean expression; `expression` and `language` fields; `purpose` field identifies where this predicate applies (`auth_precondition`, `state_precondition`, `temporal_precondition`, `lifecycle_transition_requires`, `lifecycle_transition_condition`, `workflow_branch_condition`, `aggregate_invariant`, `projection_row_filter`, `derived_membership`)
  - `computational` — derived value formula; `expression`, `language`, `result_attribute` fields
  - `validation` — schema-level constraint; `expression` and `language`; evaluated at issuance/update/aggregate-append
  - `binding_link` — connects two or more other rules (typically pairs a `legal_prose` clause with the `predicate`/`computational`/`validation` that enforces it); `links[]` field
- `title` (required) — human-readable label
- `description` (optional) — SME narrative
- `body` (required for prose types) — markdown content
- `expression` (required for executable types) — UEL or other expression in the declared `language`
- `language` (required for executable types) — must match the template's `header.expression_language`
- `purpose` (required for `predicate` type) — where this predicate is intended to apply (drives the editor/validator)
- `result_attribute` (required for `computational` type) — dotted-path identifying the credential attribute the computation populates

Rules referenced from elsewhere in the template:

- `credentials.exports[].rule_refs[]` — rules attached to a credential (Ricardian, validations, computations, behavioral expectations)
- `credentials.exports[].lifecycle.transitions[].requires[].rule_ref` — predicate gating a state transition
- `credentials.exports[].lifecycle.transitions[].condition_rule_ref` — predicate gating an automatic transition
- `commands[].auth_preconditions[].rule_ref`, `commands[].state_preconditions[].rule_ref`, `commands[].temporal_preconditions[].rule_ref` — predicates gating a command
- `aggregates[].invariants[].rule_ref` — validations enforced by aggregate
- `workflows[].steps[].branches[].rule_ref` — branch condition predicates
- `projections[].access.row_filter_rule_ref` — row access predicates

## 7. Imports/exports and alignment mechanisms

The template's imports and exports — i.e., what credentials it depends on (`credentials.imports`) and produces (`credentials.exports`) — are the substrate for the emergent ecosystem view. Two alignment mechanisms operate over them.

### 7.1 SAID-based alignment (content-addressed)

Two templates are **content-aligned** on a credential when:

- Template A's `credentials.exports[i].schema.schema_said` equals
- Template B's `credentials.imports[j].expected_schema_said`

This is automatic and strong. It is the same alignment ACDC schemas already exhibit: identical canonical content → identical SAID → cryptographic equivalence. The viewer renders a directed edge from A to B labeled by the SAID.

The viewer's emergent ecosystem clusters templates that share SAID references. A "the insurance ecosystem" is what you see when you look at the connected component of templates whose import/export SAIDs interlock.

### 7.2 Convention-based alignment (naming)

Two templates are **convention-aligned** on a credential when:

- Template A's `credentials.exports[i].name` and Template B's `credentials.imports[j]` (looked up by `expected_schema_said` resolved through a known-naming-convention registry) follow the same naming pattern (e.g., both name a `ProducerLicense`)
- But their SAIDs differ (different canonical content)

This is fuzzy. The viewer renders a dashed edge labeled with a "compatible-by-convention?" hint, prompting the user to compare and decide. Two competing implementations of `ProducerLicense` is a common organic-ecosystem dynamic — the convention says "these are probably trying to do the same thing"; the SAIDs say "their authors disagreed on the details."

The naming conventions (§8) are how convention-alignment is detected. Tools may also implement semantic similarity (compare attribute lists, lifecycle states, envelope contracts) for finer-grained convention matching.

## 8. Naming conventions (recommended; non-normative)

The spec recommends these conventions. They are authoring guidance, not validation rules — deviations produce warnings, not errors. Conforming tools should suggest, autocomplete, and lint based on them.

### 8.1 Credential names

| Pattern | Use for | Examples |
|---|---|---|
| `<Domain>License` | Authorization credentials granting permission to act within a defined scope | `ProducerLicense`, `CarrierLicense`, `AdjusterLicense` |
| `<Domain>Authority` | Delegated authority credentials | `BindingAuthority`, `RegulatorAuthority` |
| `<Domain>Card` or `<Domain>Identity` | Identity-bearing credentials | `MemberCard`, `EmployeeIdentity` |
| `<Domain>Attestation` or `<Domain>Record` | Attestation-style credentials about facts | `InventoryCountAttestation`, `MeetingMinutesRecord` |
| `<Domain>Receipt` or `<Domain>Acknowledgment` | Receipts of transactions | `PaymentReceipt`, `DeliveryAcknowledgment` |
| `<Domain>Engagement` or `<Domain>Appointment` | Engagement / appointment of one role by another | `AuditEngagement`, `BrokerAppointment` |

### 8.2 Role names

| Pattern | Use for | Examples |
|---|---|---|
| Ends in `-er` or `-or` | Active roles | `Carrier`, `Producer`, `Adjuster`, `Regulator`, `Auditor` |
| Ends in `-ee` | Receiving / passive roles | `Licensee`, `Payee`, `Grantee` |

### 8.3 Lifecycle state names

Recommended standard states (custom states allowed for domain-specific lifecycles, but these names interop better):

| State | Meaning |
|---|---|
| `pending` | Awaiting some action before becoming active |
| `active` | In force, normal operation |
| `suspended` | Temporarily not in force; reversible |
| `expired` | Time-based end-of-life |
| `revoked` | Permanently invalidated |
| `superseded` | Replaced by a newer version of the same logical credential |

### 8.4 Workflow names

| Pattern | Examples |
|---|---|
| `<Action>Workflow` | `ClaimSubmissionWorkflow` |
| `<Verb>By<Role>` | `LicenseGrantedByRegulator`, `ClaimFiledByPolicyholder` |
| `<Domain><Phase>` | `PolicyIssuance`, `PolicyRenewal`, `PolicyCancellation` |

### 8.5 Authority tree names

| Pattern | Examples |
|---|---|
| `<Root>-<Domain>` | `Regulator-Insurance`, `Founder-Coop`, `Government-Identity` |

### 8.6 exn routes

| Kind | Pattern | Examples |
|---|---|---|
| Command routes | `/<ecosystem-tag>/cmd/<verb>_<noun>` | `/insurance/cmd/submit_application`, `/insurance/cmd/file_claim` |
| Query routes | `/<ecosystem-tag>/qry/<noun>` | `/insurance/qry/active_policies` |
| Notification routes | `/<ecosystem-tag>/note/<event_name>` | `/insurance/note/policy_lapsed` |

IPEX routes (`/ipex/apply`, `/ipex/offer`, etc.) are reserved and not application-defined; conforming tools must not author commands or messages on `/ipex/*` routes — those are the protocol's domain.

### 8.7 Convention compliance

The `metadata.json` sibling (§9) MAY include a `convention_compliance` field documenting which conventions this template follows and which it deviates from, with rationale. The Ecosystem Viewer uses this to render convention-aligned clusters.

## 9. Sibling `metadata.json`

An optional sibling file capturing ecosystem-level hints that do not affect runtime behavior or the canonical template's SAID. Consumed by the Ecosystem Viewer plugin to enrich its rendering.

```json
{
  "for_micro_app_said": "EAbc...",
  "ecosystem_affinity": ["insurance", "compliance"],
  "convention_compliance": {
    "credential_naming": "compliant",
    "role_naming": "compliant",
    "workflow_naming": "deviation: 'CarrierApplies' (recommended: <Verb>By<Role> pattern → 'LicenseAppliedByCarrier' or <Action>Workflow → 'LicenseApplicationWorkflow')"
  },
  "semantic_lineage": [
    {
      "relation": "refines",
      "target_said": "EOlder...",
      "note": "Adds support for surplus-lines carriers not in the parent."
    }
  ],
  "author_intent_notes": "Designed for US 50-state regulator topologies. Not validated against single-regulator jurisdictions (UK, SG, etc.).",
  "compatibility_hints": {
    "compatible_with": ["EAnotherMicroApp..."],
    "incompatible_with": [
      {
        "target_said": "EOldImpl...",
        "reason": "Uses different ProducerLicense schema SAID."
      }
    ]
  }
}
```

Fields:

- `for_micro_app_said` (required) — the SAID of the canonical template this metadata describes. Binds metadata to template.
- `ecosystem_affinity[]` (optional) — author-declared tags suggesting which emergent ecosystems this template belongs to. Used as hints by the viewer's clustering algorithm. Tags are kebab-case free text; conventions may emerge but are not enforced.
- `convention_compliance` (optional) — per-category compliance status: either `"compliant"` or a deviation note explaining what differs from the recommended convention.
- `semantic_lineage[]` (optional) — lineage relations beyond formal forking. Each entry has `relation` (one of `refines`, `improves`, `inspired_by`, `competes_with`, `obsoletes`), `target_said`, and a free-text `note`.
- `author_intent_notes` (optional) — free-text the viewer can surface to readers.
- `compatibility_hints` (optional) — `compatible_with[]` lists templates the author has tested or believes interoperate cleanly; `incompatible_with[]` lists templates the author knows do not, with reasons.

Metadata is **not** part of the canonical template's SAID. Two templates with identical canonical content but different metadata.json files share a SAID. The metadata is hint-layer, not contract-layer. Locksmith's runtime ignores it; the Ecosystem Viewer reads it; the Designer plugin may surface it for editing.

## 10. Out of scope (reiterated)

This spec deliberately does NOT cover:

- **HOA (Higher-Order Application) definition.** HOAs compose micro-apps but are not described by this format. HOAs are a separate concept with their own future spec.
- **Locksmith wallet upgrades.** Any missing wallet primitive (transport, OOBI flow, IPEX handler, UI shell) is a separate Locksmith project; this spec assumes the current wallet capabilities are sufficient for any conforming template.
- **The `Micro App: Designer` plugin's UI.** The plugin's implementation chooses its own UI patterns; this spec only defines what it must read, write, and validate.
- **The `Micro App: Ecosystem Viewer` plugin.** Its rendering of the emergent ecosystem from a corpus of templates is a separate project with its own spec.
- **The `micro-app-template-gen` skill's conversational design.** The 10-step authoring path in Appendix A is informative, not normative. The skill's actual implementation may differ.
- **Micro-app deployment, hosting, distribution.** Once a template is authored, how it gets onto a wallet (OOBI, file transfer, marketplace, registry) is out of scope.
- **Runtime behavior of deployed micro-apps.** Locksmith's existing runtime interprets the template; this spec defines what the template *contains*, not what Locksmith *does* with it.
- **Domain-specific semantics.** The spec is domain-agnostic. Insurance, healthcare, supply-chain, education, etc., are illustrative examples, not part of the spec.
- **The meta-schema's exact JSON-Schema content.** The meta-schema is a follow-on artifact derived from this spec; this spec describes the shape, the meta-schema encodes it formally.

## 11. Follow-on work

Implementation follows in roughly this order:

1. **Meta-schema artifact** — encode this spec's primitive shapes as a JSON-Schema. Validates conforming `micro-app-template.json` files. SAID-identified.
2. **`micro-app-template-gen` skill** — full implementation of the 10-step authoring path (Appendix A) producing conforming JSON. The stub at `.claude/skills/micro-app-template-gen/SKILL.md` (committed alongside this spec) is the starting point.
3. **`Micro App: Designer` plugin** — Locksmith plugin for viewing/editing conforming templates. Validates against the meta-schema; lints against conventions; supports forking; manages SAIDs on save.
4. **`Micro App: Ecosystem Viewer` plugin** (evolution of existing `ecosystem_viewer`) — reads the corpus of templates the wallet knows about; renders emergent ecosystem view; surfaces SAID-alignment and convention-alignment; renders competing implementations.
5. **Sample templates** — author the first concrete templates (perhaps small fragments of the insurance domain you've already modeled in `usurance/docs/insurance/ecosystem.yaml`) to validate the format under real use.
6. **Bridge tooling** — Ecosystem Viewer features for cross-ecosystem references (Bridges); reading neighbor ecosystems via OOBI.

Each follow-on is its own design and plan cycle.

---

## Appendix A: The `micro-app-template-gen` skill — 10-step authoring path (informative)

This appendix describes the conversational authoring path implemented by the `micro-app-template-gen` skill. It is one path among many that may produce a conforming template; the artifact contract (sections 1–10) is normative, this path is illustrative.

### Step 0 — Identify the role

Ask: *Which role does this micro-app embody?* The role is the micro-app's identity. Capture: id, display_name, description, kind (one of: individual, organization, system, device, agent, government), keri_infrastructure flags (witness_pool, watcher_network, mailbox, acdc_registry — suggest defaults based on kind, let user override).

Produces: `role` primitive (§6.2).

### Step 1 — Name the use case

Ask: *From this role's perspective, what is the outcome they want?* State as a past-tense fact in the language the business uses ("a license has been granted", "a claim has been adjusted"). If two pivotal events surface, you have two micro-apps — split now and revisit later.

Produces: `header.id`, `header.display_name`, `header.description`. Sets the narrative anchor for everything that follows.

### Step 2 — Identify credential imports

Ask: *What credentials must this role hold to perform its commands?* For each: an id, the expected schema SAID (resolved from other templates the wallet knows about, or asked of the user), the expected issuer role, optional attribute constraints, lifecycle states that make it usable.

These come from OTHER micro-apps. The skill prompts the user to look at the emergent ecosystem view (if available) or ask about SAIDs explicitly.

Produces: `credentials.imports[]` (§6.3).

### Step 3 — Identify credential exports

Ask: *What credentials does this role produce?* For each:

- Envelope (holder_role, verifier_roles, edges with operator choices, disclosure_mode)
- Schema (author the JSON-Schema file in `schemas/`; compute its SAID; reference it)
- Lifecycle (states, initial, transitions with via_workflow / requires / tel_primitive)
- Rule refs (forward-reference rules that will be authored in Step 9)
- Value flow (optional implied credentials)

This is the heaviest step. Subagents can be dispatched for schema authoring per credential.

Produces: `credentials.exports[]` (§6.3) + schema files in `schemas/`.

### Step 4 — Identify commands

Ask: *What actions does this role take?* For each command:

- Route (suggest based on naming convention)
- Counterparty role (if any)
- Payload schema (the actor's input — minimal)
- Preconditions (auth, state, temporal — each as rule_ref forward-references)
- Idempotency key expression
- Emissions (what fires on success — exchange / lifecycle_advance / aggregate_event)

Produces: `commands[]` (§6.4).

### Step 5 — Identify aggregates

Ask: *What state does this role track locally?* For each aggregate:

- Inception event type (the event that mints its identifier)
- State schema (the folded shape)
- Initial state
- Invariants (rule_ref forward-references)
- Log scope (private / witnessed / shared)

Produces: `aggregates[]` (§6.5).

### Step 6 — Identify reactions

Ask: *What does this role do when it observes external events?* For each reaction:

- Trigger (credential_received / exn_received / lifecycle_event / scheduled, with matching fields)
- Emissions (same as command emissions)
- Failure policy

Produces: `reactions[]` (§6.6).

### Step 7 — Identify workflows

Ask: *Are there multi-step external interactions this role participates in?* For each workflow:

- Counterparty role
- Trigger
- Steps (self-actions referring to command/reaction ids; counterparty-waits with expected_inbound matches; branches; time_bounds)

Workflows from this role's perspective only.

Produces: `workflows[]` (§6.7).

### Step 8 — Identify projections

Ask: *What does this role need to look at to do their job?* For each projection:

- Source events
- Output schema
- Fold expression (UEL)
- Access (row_filter rule_ref, lens_template)
- Display hints (view_type, columns, sort, empty_state)

Locksmith renders these for the user playing this role.

Produces: `projections[]` (§6.8).

### Step 9 — Author the rules

Now author all the rules forward-referenced in Steps 3–8: legal_prose, behavioral_expectation, business_policy, predicate (with explicit purposes), computational, validation, binding_link.

The skill resolves forward references at this point. If a rule_ref points to a rule_id that doesn't exist, the skill prompts the user to author it.

Produces: `rules[]` (§6.9).

### Step 10 — Conventions, hints, lineage (sibling metadata.json)

Audit naming compliance; suggest fixes for deviations. Declare optional ecosystem_affinity tags. Optionally capture semantic_lineage relations to other templates. Free-form author_intent_notes.

Produces: sibling `metadata.json` (§9). Does not affect the canonical template's SAID.

### Adversarial review (informal step)

Walk the adversarial checklist (Appendix B) before declaring the template done. Captured as `author_intent_notes` in metadata or as out-of-band notes.

### Save and saidify

Canonicalize the JSON (sort keys, deterministic spacing), compute the SAID, set `d`, save `micro-app-template.json` and `metadata.json` + `schemas/*.json`.

---

## Appendix B: Adversarial review checklist (informative)

Before declaring a template done, walk these:

- **Lies.** Are signatures and credential chains the only way to claim authority? Can an impostor present a forged credential and have it pass? (KERI substrate makes the answer "no by construction" when used correctly — verify your auth_preconditions actually leverage the substrate.)
- **Revocation between presentation and append.** A credential is valid at command time but revoked by the time the resulting event is folded. Does your micro-app handle this gracefully? Document the cut-off rule.
- **Races on the same aggregate.** Two commands arrive simultaneously; the loser must fail on a stale-state precondition. Is the loser's UX graceful?
- **Missed events.** A subscriber crashes during a multi-event sequence and resumes later. Can it catch up by replaying? Are your projections idempotent under replay?
- **Compromised actor.** The role's keys are rotated under duress. The aggregate respects whatever key state was authoritative at command time — verify this is the behavior your micro-app needs.
- **Counterparty cheats.** The counterparty sends an unexpected message or refuses to advance. Are your workflow time_bounds + spurn handlers complete?
- **Convention drift.** Schema SAIDs differ from neighbor micro-apps' but names match. Is this intentional competition, or an avoidable accident? Document in metadata.

---

## Appendix C: Type reference

### Participant Type (`role.kind`)

`individual` | `organization` | `system` | `device` | `agent` | `government`

### Membership rule types (future — for advanced authority topology; out of MVP scope unless explicitly needed)

`anchored` | `qualified` | `delegated` | `composite` | `derived` | `external` | `unbound`

(The MVP focuses on single-role templates; multi-role authority topology lives in the Ecosystem Viewer's emergent model. Future extensions may surface these directly.)

### Edge operators (`credentials.exports[].envelope.edges[].operator`)

| Operator | Semantic | KERI-native acronym |
|---|---|---|
| `authorizes` | Holder of parent becomes issuer of this credential | I2I |
| `references` | Informational pointer; no authority transfer | NI2I |
| `authorizes-via-delegate` | Issuer is a KEL-delegated AID of parent's holder | DI2I |

### TEL primitives (`credentials.exports[].lifecycle.transitions[].tel_primitive`)

`issue` | `update` | `revoke`

### IPEX verbs (`workflows[].steps[].command emissions[].exchange.verb` and reactions' `trigger.ipex_verb`)

`apply` | `offer` | `agree` | `grant` | `admit` | `spurn`

### Exchange kinds (`commands[].emissions[].exchange.kind` and `reactions[].trigger.type`-adjacent)

`credential` (IPEX) | `message` (exn) | `null` (internal)

### Message patterns (within `kind: message`)

`command` | `query` | `notification`

### Rule types (`rules[].type`)

`legal_prose` | `behavioral_expectation` | `business_policy` | `predicate` | `computational` | `validation` | `binding_link`

### Predicate purposes (`rules[].purpose` when `type: predicate`)

`auth_precondition` | `state_precondition` | `temporal_precondition` | `lifecycle_transition_requires` | `lifecycle_transition_condition` | `workflow_branch_condition` | `aggregate_invariant` | `projection_row_filter` | `derived_membership`

### Display view types (`projections[].display.view_type`)

`table` | `list` | `cards` | `kanban` | `timeline` | `summary`

### Semantic lineage relations (`metadata.semantic_lineage[].relation`)

`refines` | `improves` | `inspired_by` | `competes_with` | `obsoletes`
