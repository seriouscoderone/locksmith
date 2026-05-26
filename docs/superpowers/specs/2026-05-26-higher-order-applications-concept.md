# Higher-Order Applications (HOAs) — Concept

**Date:** 2026-05-26
**Status:** Concept (pre-normative — to be refined as the pattern matures)

## 1. What is an HOA?

A **Higher-Order Application (HOA)** is a *persona-shaped desktop application* that composes a curated set of micro-apps into one coherent UX for one human role. The homeowner-HOA is the homeowner's experience of P&C insurance; the underwriter-HOA is the underwriter's. Each HOA is its own desktop app, but all are built from the same shared scaffold and share KERI-native infrastructure.

A human who plays multiple roles in an ecosystem (someone who is both a homeowner and an insurance agent, or both an event-organizer and a frequent attendor) runs **multiple HOAs side by side on the same KERI key** — one per persona — rather than a single "everything" HOA. The KERI-native infrastructure is built to make this transparent.

Ugard ships multiple HOAs (homeowner, agent, underwriter, claims-adjuster, product-engineer) for the P&C insurance ecosystem. Each is built on a future `locksmith-hoa-base` scaffold — Locksmith with the wallet UI peeled off, leaving its KERI-native primitives ready to be wrapped in a hand-crafted, persona-shaped UX.

## 2. The three layers of a KERI-native application stack

| Layer | What it is | Where it lives |
|---|---|---|
| **Micro-app** | A *protocol contract*. One role's slice of one use case, expressed as a JSON template describing credential exchanges, commands, reactions, workflows, and rules on top of KERI primitives (exn, IPEX, ACDC, TEL). Not "an app" — closer to an API specification. | `docs/micro-apps/` (templates). Authored via `micro-app-template-gen`. Spec: `2026-05-09-micro-app-template-authoring-and-data-model.md`. |
| **Runtime** | The *autonomous execution side*. Services that act on their own when invoked or when conditions arise — fulfilling commands, witnessing events, issuing credentials. Algorithmic and data-heavy work that has to *do* something on its own. Two flavors; see below. | Currently prototyped in the locksmith repo; will land on serverless AWS infra (Lambda / Step Functions / DynamoDB, per constitution Principle V). |
| **Higher-Order Application** | A *persona-shaped desktop application* that composes micro-apps into a human-shaped UX. Feels like a normal app; KERI-nativity surfaces primarily at login (Passkey-like ergonomics on a KERI key). | One desktop app per persona, built in this repo on `locksmith-hoa-base`. |

A micro-app is what you exchange. A runtime is what runs autonomously. An HOA is what a person uses.

### 2.1 Two kinds of runtime

The "runtime" layer hides a useful distinction that the trinity above flattens. A runtime is "what runs autonomously," but two flavors exist, and conflating them produces architectural confusion:

- **Compute runtime** — Lambda-like, *no AID*. Called by an HOA over an API; executes a command and returns a result. The **rating engine** that prices a quote against a product credential is one: an HOA asks it for a premium, it computes, it answers. It does not hold an identifier, does not sign claims as itself, and is not a counterparty in any KERI exchange. It is a tool an HOA reaches for.
- **Principal runtime** — *controls its own AID*, writes to its own KEL/TEL, and participates in IPEX exchanges as a party. The **VenueApplication** running at an event's door is one: an autonomous service that issues AttendanceRecord credentials to its TEL when Attendors present valid Tickets. It is a KERI principal, just one whose controller happens to be automated rather than human. It is something an HOA *coordinates with*, not something it calls.

Both flavors are valid; both are runtimes; both are deployed as services. They differ only in whether they are *KERI principals* — whether they hold identifiers, sign claims, and appear as counterparties in credential exchanges.

Recognizing the distinction prevents architectural confusion: "the underwriter HOA calls the rating engine" and "the attendor HOA exchanges credentials with the venue application" look superficially similar but are radically different patterns — request/response over an API versus protocol-level participation between KERI principals. The first looks like ordinary cloud software wearing a KERI badge; the second is what makes KERI-native infrastructure structurally different from "REST + signed JSON."

## 3. What earns the word "Higher-Order"?

An HOA is more than a bundle. It generates value beyond what installing the same micro-apps in a generic wallet would yield:

- **Persona-shaped UX and navigation.** The homeowner doesn't hunt through a generic credential drawer. They see what a homeowner cares about, when they care about it. Layout, vocabulary, surfacing, defaults — all shaped to the persona.
- **Cross-micro-app workflows.** Multiple micro-apps stitched into guided business processes. Annual renewal = update-policy + pay-premium + verify-coverage, walked through as one experience. The HOA owns the orchestration; the micro-apps own the steps.
- **Cross-micro-app data fusion.** Projections over the state of multiple micro-apps. A household dashboard surfaces all policies, all claims, all bills, all coverage gaps in one view.
- **HOA-owned local logic.** Features that don't belong to any single micro-app: preferences, reminders, document organization, comparison tools, notes. Things that are *about the persona*, not about a role-slice exchange.
- **Persona composition is the HOA-author's choice.** A human who plays multiple roles runs multiple HOAs on one KERI key, or — if the personas overlap closely — has them composed within one HOA whose UI surfaces both. No special architecture is required; the underlying KERI primitives are designed for either.

And, structurally:

- **Thesis: AI-buildable, ecosystem-emergent.** An HOA should be small enough that an AI agent can scaffold, build, and deploy one in days, not months. If that holds, multiple organizations adopting the pattern produce an interoperable ecosystem by virtue of sharing the same credential language — no central platform, no vendor lock-in, no integration tax. The post-Saaspocalypse SaaS pattern. This is a working hypothesis, not a demonstrated property; it will be validated or disconfirmed when ugard's first HOA reaches implementation.

## 4. Ugard's first HOAs

Concrete persona-shaped HOAs ugard plans to build, all on the same monorepo infrastructure:

| HOA | Persona | Primary micro-apps it composes |
|---|---|---|
| **Homeowner / policyholder HOA** | The insured | quote-application (homeowner side), policy-issuance, policy-endorsement, claims-intake, billing |
| **Insurance agent HOA** | Distribution intermediary | quote-application (agent side), distribution-management, commission, policy-issuance |
| **Underwriter HOA** | Carrier-side risk pricing | quote-application (underwriter side), policy-issuance, risk-profile, insurance-product-management (consumer) |
| **Claims-adjuster HOA** | Carrier-side claims handling | claims-intake (adjuster side), claims-management, cat-response, subrogation-recovery, document-generation |
| **Product engineer HOA** | Actuary / underwriter authoring | insurance-product-management (authoring side) — emits product + rate-table credentials that other HOAs consume |

The **rating engine** that prices a quote against a product credential is a **compute runtime**, not an HOA — it executes the command, it doesn't have a persona, it doesn't hold an AID.

The roles, credentials, governance, and trust framework these HOAs operate within are defined in `docs/insurance/ecosystem.yaml` (C0 ecosystem) and the per-use-case directories beside it.

## 5. Pattern across ecosystems

The HOA / micro-app / runtime trinity is domain-independent. P&C insurance is the first ecosystem ugard is instantiating it in, but the pattern applies elsewhere with no structural changes. One worked sketch:

**Attendance ecosystem.** Three personas (Attendor, EventOrganizer, VenueOwner) and one autonomous service (VenueApplication, deployed at physical venues). Four micro-app templates: **Booking** (VenueOwner authorizes an EventOrganizer to run an event there), **Event** (EventOrganizer defines the event), **Ticket** (EventOrganizer issues to Attendor, bound to Attendor's AID with controlled transfer via revoke+reissue), **AttendanceRecord** (VenueApplication writes to its own TEL on check-in; all three parties observe it as equals). At least two HOAs (an EventOrganizer dashboard for designing events and watching rosters; a VenueOwner manager for accepting Bookings and operating venue devices). The Attendor's needs may be served by a dedicated Attendor HOA or by a generic KERI wallet, depending on usage intensity — not every persona warrants its own HOA. The **VenueApplication is the exemplar principal runtime**: AID-bearing, IPEX-participating, but headless and autonomous; its controller is the VenueOwner. No P&C-specific machinery anywhere.

The same shape recurs in any ecosystem where humans play roles, services act on those roles' behalf, and verifiable artifacts flow between them — healthcare visits (Patient / Clinician / Clinic, plus an intake-kiosk principal runtime), property leases (Tenant / Landlord / Property-manager, plus an access-control principal runtime), and so on. In each case the same three-layer decomposition holds.

## 6. Shared infrastructure

HOAs in ugard share:

- A monorepo scaffold (`locksmith-hoa-base`, eventually) — KERI primitives, login/Passkey patterns, design system
- KERI infrastructure on serverless AWS (witness pool, watcher, registries, runtime), per the constitution's Principle V scale-to-zero requirement
- The micro-app template corpus (`docs/micro-apps/`) and the meta-schema that validates it
- Skills and patterns for authoring new HOAs (analogous to `micro-app-template-gen`, to be developed)

### 6.1 Implementation language

The constitution's "TypeScript everywhere" guidance was aspirational. The pragmatic near-term answer is **Python**: keripy is the KERI reference implementation, and the locksmith codebase from which `locksmith-hoa-base` will fork is already Python (PySide6 desktop). TypeScript via signify-ts remains the long-term direction — as signify-ts matures and browser-deployable HOAs become viable, the stack can migrate — but ugard's first HOAs ship on the existing Python stack. Migration plans are deferred to a follow-on artifact; this concept doc commits to nothing about packaging or runtime language beyond "Python now, TS later if and when it earns its keep."

## 7. Out of scope (for this concept)

This is a concept document, not a normative spec. The following are explicitly deferred:

- The contract format of an HOA manifest (if any)
- The `locksmith-hoa-base` scaffold itself — still being shaped in the locksmith repo
- The HOA-authoring skill and its workflow
- Login / Passkey-style KERI authentication mechanics
- Cross-HOA interaction patterns (e.g., whether an underwriter-HOA sends work directly to a homeowner-HOA, or only ever via shared KERI infra)

These will be designed in follow-on artifacts once the first HOA is in implementation and the pattern reveals what it needs.

## 8. Related

- Micro-app spec: `docs/superpowers/specs/2026-05-09-micro-app-template-authoring-and-data-model.md`
- Ecosystem definition: `docs/insurance/ecosystem.yaml`, `docs/insurance/credential-catalog.md`, `docs/insurance/trust-framework.md`
- Use-case directories: `docs/insurance/{quote-application, policy-issuance, claims-intake, ...}/`
- Constitution: `.specify/memory/constitution.md` (Principles V, VI, VIII bind this work)
