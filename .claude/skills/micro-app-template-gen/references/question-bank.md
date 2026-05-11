# Question Bank

Per-step questions to ask an SME. Pick the primary question first; ask follow-ups only when the primary answer leaves ambiguity. One question at a time. Plain language — push back on KERI jargon in user-facing answers.

## Step 0 — Identify the role

**Primary:**
- *"Which role does this micro-app embody?"* — get id, display name, description

**Follow-ups:**
- *"Is this an individual, an organization, a system, a device, an autonomous agent, or a government?"* — get `kind`
- *"Does this role typically operate its own witnesses? Watch others' KELs? Need an always-on mailbox to receive offline messages? Run credential registries?"* — get `keri_infrastructure` flags. Suggest defaults by kind; let the SME override.

## Step 1 — Name the use case

**Primary:**
- *"From this role's perspective, what's the outcome they want? State it as a past-tense fact in business language."*

**Follow-ups:**
- *"If two outcomes feel central, can you state each separately? They might be two micro-apps."*
- *"Does this template descend from another? If so, what's the parent's SAID and version, and what did you change?"*

## Step 2 — Credential imports (the imports list)

**Primary:**
- *"What credentials must this role hold to take its actions?"*

**Follow-ups per imported credential:**
- *"What's this credential type called?"*
- *"What's the SAID of the schema?"* — if not known, note as TBD and continue
- *"Who issues it? (which role)"*
- *"Which lifecycle states make it usable? (default: active)"*
- *"Does the role start without an active instance of this credential type? If so, we still declare it here — the imports list captures types, not current holdings. Note the 'starts empty' status in the `narrative` field."*

## Step 3 — Credential exports (the exports list)

**Primary:**
- *"What credentials does this role produce?"*

**Follow-ups per exported credential:**
- *"What's the credential called and what does it convey?"*
- *"Who holds it? Who can verify it?"*
- *"Does it chain from another credential — like 'I can only issue this if I hold a parent credential'? If so, which?"*
  - *"Is the chain authorizing (holder becomes issuer), referencing (informational only), or via delegated AID?"*
- *"How sensitive is its data? Full disclosure, selective (per-field), or aggregate?"*
- *"What states does this credential go through?"* — list them
- *"For each state, how is it reached? Through which workflow? Mapping to KERI: is the transition an `issue` (initial creation), an `update` (mid-life change), or a `revoke` (terminal)?"*

## Step 4 — Commands

**Primary:**
- *"What actions does this role take?"*

**Follow-ups per command:**
- *"In imperative voice, what's this command called?"*
- *"What does the actor supply? (the payload)"*
- *"What must already be true for this command to be valid?"*
  - *"What credentials must the actor hold? (auth preconditions)"*
  - *"What facts must exist in the local state? (state preconditions)"*
  - *"Any deadlines, cooldowns, business hours? (temporal preconditions)"*
- *"If the actor retries, what stops a duplicate? (idempotency key — derivable from payload alone)"*
- *"What happens on success? Does it emit an IPEX message? Advance a credential's lifecycle? Append to a local aggregate? All of those?"*

## Step 5 — Aggregates

**Primary:**
- *"What state does this role track locally?"*

**Follow-ups per aggregate:**
- *"What history must I read to know if a command is valid?"* — that's the aggregate
- *"What's its identifier and how is it minted? (inception event)"*
- *"What invariants does it protect? (plain English; will become validation rules)"*
- *"Is this log private, witnessed, or shared with others?"*

## Step 6 — Reactions

**Primary:**
- *"What does this role do when something happens that they didn't initiate?"*

**Follow-ups per reaction:**
- *"What event are they reacting to? An incoming credential? An exn message? A local lifecycle transition? A scheduled timer?"*
- *"What do they do in response? (same emission shape as commands)"*
- *"What if the reaction fails? Log and continue? Spurn? Abort?"*

## Step 7 — Workflows

**Primary:**
- *"Are there multi-step external interactions this role participates in?"*

**Follow-ups per workflow:**
- *"Who's the counterparty?"*
- *"What kicks it off? A user action? A schedule? A received credential?"*
- *"Walk through the steps from this role's perspective only. For each: do they act, or are they waiting? If acting, which command or reaction? If waiting, what are they waiting for and what triggers the next step?"*
- *"Are there branches based on conditions? Time limits?"*

## Step 8 — Projections

**Primary:**
- *"What views does this role need to do their job?"*

**Follow-ups per projection:**
- *"What question does this answer?"*
- *"Which event streams does it fold over?"*
- *"What's the output shape? (Locksmith will render this as a table, list, cards, kanban, timeline, or summary)"*
- *"Who's allowed to see each row? (credential-gated row filter)"*

## Step 9 — Rules

**Primary:**
- *"Let's go through all the forward-referenced rules and author each. For each rule, what type fits best?"*

**Follow-ups per rule:**
- *Type-specific questions, see `rule-types-reference.md`*

## Step 10 — Metadata

**Primary:**
- *"Let's audit the naming conventions. Did we follow them, or do you have specific reasons for deviating?"*

**Follow-ups:**
- *"Which emergent ecosystems do you think this micro-app belongs to? (kebab-case tags)"*
- *"Does this template improve on, refine, or compete with any other template you know of?"*
- *"Any author notes you want surfaced when someone explores the emergent ecosystem view?"*
- *"Any templates you know are compatible or incompatible with this one?"*
