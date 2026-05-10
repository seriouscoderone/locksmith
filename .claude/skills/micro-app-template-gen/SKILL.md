---
name: micro-app-template-gen
description: Walk a subject-matter expert (or AI agent) through producing a single micro-app template — a JSON artifact describing one role's slice of a KERI-native ecosystem application. Output is `micro-app-template.json` + sibling `metadata.json` + `schemas/*.json` conforming to the spec at `docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md`. Rigid in step order, flexible in content. Resumable.
user_invocable: true
---

# Micro-App Template Generator

## Overview

Guides a user through fleshing out a single **micro-app template** — the smallest deployable unit of a KERI-native application, scoped to one role's perspective on one use case. The output is a JSON artifact (`micro-app-template.json`) plus a sibling `metadata.json` plus a `schemas/` directory of JSON-Schema files for each issued credential. Together these conform to the contract defined in:

**`docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md`**

Read that spec before walking the steps. The spec is normative; this skill is one (informative) path to producing a conforming artifact.

## What is a micro-app template?

A micro-app template captures **one role's perspective on one use case** in some KERI-native ecosystem. The carrier's side of license-application is one template. The regulator's side is a different template. Bilateral conversations emerge at runtime from multiple templates coexisting in the same KERI substrate.

The template tells Locksmith (the wallet) what to render, what to send, what to react to, what to track. Locksmith's existing primitives — KEL, TEL, ACDC, IPEX, exn, OOBI — provide the runtime; the template provides the role-specific behavior.

The template has eight primitives:
1. **Header** — identifies the template
2. **Role** — the single role this template embodies
3. **Credentials** — held (imports) and issued (exports)
4. **Commands** — actions this role takes
5. **Aggregates** — local state this role tracks
6. **Reactions** — handlers for events this role observes but does not initiate
7. **Workflows** — multi-step external interactions, from this role's perspective
8. **Projections** — views Locksmith renders for the user playing this role
9. **Rules** — typed cross-cutting layer (legal prose, predicates, computations, validations, behavioral expectations)

Plus a sibling `metadata.json` capturing convention compliance, ecosystem affinity hints, and semantic lineage (does not affect the canonical SAID).

See the spec, sections §5–§9, for the JSON shapes.

## Prerequisites

Before starting, confirm with the user:

1. **Which role does this micro-app embody?** Get the role's id (kebab-case), display name, and intrinsic kind (individual, organization, system, device, agent, government).
2. **Is there a one-sentence outcome statement?** A past-tense fact in business language, from this role's perspective ("a license has been granted", "a claim has been adjusted").
3. **Where does the artifact get written?** Default: `docs/micro-apps/{role-id}-{use-case-id}/`. The directory contains `micro-app-template.json`, `metadata.json`, and `schemas/`.

## Workflow

The 10-step process is rigid in order — Step N's questions depend on Step N-1's answers. Within a step, the content is flexible. Save after each step.

### Step 0 — Identify the role

Ask: *Which role does this micro-app embody?*

Capture: `role.id`, `role.display_name`, `role.description`, `role.kind` (individual | organization | system | device | agent | government), `role.keri_infrastructure` flags (witness_pool, watcher_network, mailbox, acdc_registry — suggest defaults based on kind).

Produces the `role` primitive (spec §6.2). Save.

### Step 1 — Name the use case

Ask: *From this role's perspective, what is the outcome they want?*

Capture: `header.id` (kebab-case use case identifier), `header.display_name`, `header.description` (the past-tense outcome statement plus narrative context), `header.version` (start at `"1.0"`), `header.expression_language` (default `"UEL/1.0"`).

If two pivotal events surface, this is two micro-apps — split now.

Produces the `header` primitive (spec §6.1). Save.

### Step 2 — Held credentials (imports)

Ask: *What credentials must this role hold to perform its commands?*

For each held credential, capture: local id, expected schema SAID (look it up in known templates, or note as TBD if not yet defined elsewhere), expected issuer role, optional attribute constraints, lifecycle acceptance list, optional narrative.

Produces `credentials.held[]` (spec §6.3). Save.

### Step 3 — Issued credentials (exports)

Ask: *What credentials does this role produce?*

For each issued credential, capture the six layers (envelope, schema, lifecycle, rule_refs, value_flow). Author the JSON-Schema file in `schemas/{credential_id}.json`. Compute its SAID. Reference both.

Use forward-references to rules — they get authored in Step 9.

Produces `credentials.issued[]` (spec §6.3) plus `schemas/*.json` files. Save.

### Step 4 — Commands

Ask: *What actions does this role take?*

For each command: route (suggest per naming conventions in spec §8.6), counterparty role, payload schema, preconditions (auth/state/temporal as rule_ref forward-references), idempotency key expression, emissions.

Produces `commands[]` (spec §6.4). Save.

### Step 5 — Aggregates

Ask: *What state does this role track locally?*

For each aggregate: inception event type, state schema, initial state, invariants (rule_ref forward-references), log scope.

Produces `aggregates[]` (spec §6.5). Save.

### Step 6 — Reactions

Ask: *What does this role do when it observes external events?*

For each reaction: trigger (credential_received / exn_received / lifecycle_event / scheduled), emissions, failure policy.

Produces `reactions[]` (spec §6.6). Save.

### Step 7 — Workflows

Ask: *Are there multi-step external interactions this role participates in?*

For each workflow: counterparty role, trigger, ordered steps (self-actions referring to command/reaction ids; counterparty-waits with expected_inbound matches; branches; time_bounds).

Workflows from this role's perspective only. The counterparty has their own workflow in their own template.

Produces `workflows[]` (spec §6.7). Save.

### Step 8 — Projections

Ask: *What does this role need to look at to do their job?*

For each projection: source events, output schema, fold expression, access (row_filter rule_ref, lens_template), display hints.

Produces `projections[]` (spec §6.8). Save.

### Step 9 — Rules

Author all rules forward-referenced in Steps 3–8. Types: `legal_prose`, `behavioral_expectation`, `business_policy`, `predicate` (with explicit `purpose`), `computational`, `validation`, `binding_link`.

Resolve every forward reference; if a `rule_ref` points to an undefined rule, prompt the user to author it.

Produces `rules[]` (spec §6.9). Save.

### Step 10 — Conventions, hints, lineage (metadata)

Audit naming compliance against spec §8. Declare `ecosystem_affinity` tags. Optionally capture `semantic_lineage` relations to other templates. Free-form `author_intent_notes`.

Produces `metadata.json` (spec §9). Does not affect the canonical template's SAID. Save.

### Adversarial review

Walk the adversarial checklist (spec Appendix B) before declaring the template done.

### Save and saidify

1. Sort top-level keys lexicographically (and nested object keys recursively).
2. Re-serialize with deterministic spacing (two-space indent, single newline at EOF).
3. Replace `d` with a 44-character placeholder.
4. Hash the canonical form to produce the SAID.
5. Replace the placeholder in `d` with the SAID.
6. Write `micro-app-template.json`. Write `metadata.json` (with `for_micro_app_said` set to the new SAID). Confirm all `schemas/*.json` are present.

## Conversation rules

- **One question at a time** within a step. Don't batch.
- **Plain language** — push back on KERI jargon (AID, IPEX) in user-facing fields. Use the spec's vocabulary (Roles, Credentials, Workflows).
- **Cite the spec.** When making structural choices, point at the relevant section.
- **Save after each step.** Don't lose user input by batching writes.
- **Explicit recovery.** On re-entry to an existing template, summarize what's already filled in 3–5 lines before asking the next question.

## Skill discipline (rigid)

The 10-step order is fixed; later steps depend on earlier answers. What's flexible: the content of each answer and how the questions are phrased. What's rigid: the order, the requirement to complete each step before the next, and the requirement to revisit when later steps surface contradictions.

## Anti-patterns

- **DON'T** let the user skip Step 9 (rules). It's where most contractual and enforcement substance lives.
- **DON'T** let the user skip the adversarial review.
- **DON'T** invent credential SAIDs. If a held credential's schema SAID isn't yet known, mark it explicitly and revisit when the corresponding issuer template is authored.
- **DON'T** put credentials, commands, or workflows on `/ipex/*` routes — those are reserved for the protocol.
- **DO** follow the naming conventions (spec §8) when suggesting names; warn on deviations.
- **DO** treat Step 10 (convention compliance + lineage) as load-bearing for the emergent ecosystem view, even though it doesn't affect runtime.

## Status

**Stub.** This file is the skeleton; full conversational prose, question banks, output templates, and resumption logic land in the follow-on implementation task. The skill's contract (produce a conforming `micro-app-template.json` + `metadata.json` + `schemas/`) is fixed by the spec; the conversational design is to be elaborated.
