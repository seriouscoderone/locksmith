# Ecosystem Governance Roadmap — Synthesis

Date: 2026-05-08
Status: Synthesis of three parallel research efforts; sets up Stage 12+ planning
Audience: the wallet's developer/owner (decision-maker) and the implementer

This doc synthesizes four parallel research efforts:
- `research/2026-05-08-vlei-ecosystem-patterns.md` (Agent A — vLEI investigation)
- `research/2026-05-08-applications-archaeology.md` (Agent B — codebase archaeology of the deleted `applications/` directory)
- `research/2026-05-08-current-state-audit.md` (Agent C — audit of the current `db.py` data model)
- `/Users/seriouscoderone/code/keripy/docs/ecosystem-pattern.md` ("The Ecosystem Pattern" — abstract DDD-shaped framing of *any* cooperative ecosystem; not KERI-specific)

The reader does not need to read all four. The synthesis here is sufficient to make the next-stage decision; deep references stay in the research docs.

**A note on scope before reading further.** The Ecosystem Pattern doc enumerates ten core elements of any ecosystem governance framework — Purpose & Scope, Authority Root, Roles, Attestation Catalog, Trust Registry, Risk Register, Liability & Remedy, Legal & Commercial, Compliance & Recognition, Audit & Assurance. **The wallet plugin can only meaningfully model a subset of these** (broadly: Trust Registry, Roles, Attestation Catalog, and parts of Authority Root + Delegation Tree). The wallet is a *viewer-and-light-editor of a trust registry*, not a framework authoring tool. §1.5 below maps the plugin's intended scope onto the pattern's ten elements; the rest of this doc focuses on what we CAN model, with explicit calls out where adjacent ecosystem-pattern elements sit out of scope.

---

## Section 1 — The shared finding (where the three agents converge)

The wallet's developer asked: "How do I let an ecosystem express *categories* of AIDs (rather than enumerated lists), and have membership in a category be derived from holding qualifying credentials?"

All three agents independently arrived at the same answer:

**The missing primitive is a `Role` — a credential-qualified class of AID, defined at the ecosystem level, that can replace the current `permitted_issuers: dict[schema_said, list[aid]]` AID-whitelist with an open-ended membership rule.**

| Agent | Term used | What it adds |
|---|---|---|
| A (vLEI) | "Role as a Credential-Holding Class" | vLEI has *zero* hard AID whitelists; every role membership is "AID holds valid credential of schema X issued by role Y". Cited as the deepest structural gap in the current plugin. |
| B (archaeology) | `AuthorizationDef(principal="holder_of(...)")` | The deleted `applications/` code already had a string-DSL principal ("holder_of(qualified-vlei-issuer-credential)") that expresses credential-based qualification. |
| C (audit) | `RoleRecord` dataclass + `issuer_qualification_rules` field | A non-breaking minimal addition to `EcosystemRecord` plus a new `rle.` Komer subkey. |

The convergence isn't an accident: the vLEI ecosystem is the canonical real-world example, the deleted code was modeling vLEI-flavored use cases, and the current data model can express none of it. The fix has the shape of these three converging recommendations.

**Other shared findings, in declining priority:**

- **The chain operators (I2I / NI2I / DI2I) and edge-locked schema SAIDs in `e` sections are already what the spec uses to express delegation chains** (Agent A, ACDC spec §8.1.4 and §8.6.9–11). They are first-class spec primitives — we don't need to invent governance overlays for them, only render them well. The current plugin already detects them via the inspector but the graph view's edge rendering does not visually distinguish I2I from NI2I, and the side panel does not explain the difference. Polish opportunity, not a new modeling primitive.
- **Schema lifecycle metadata** (Agent A's "EGF Schema Registry") — the wallet stores schemas as a flat `list[str]` of SAIDs. There's no per-schema version, retirement state, or successor pointer. vLEI and any real EGF need this. Lower urgency than Roles, but not far behind.
- **Authorization-credential boundary** (Agent A's "OOR AUTH / ECR AUTH") — the vLEI distinguishes "the credential that *grants the right* to issue X" from "the credential X". Operationally similar to chain-of-authority edges, but conceptually distinct. The current plugin can't render or model the distinction. Pairs naturally with Roles.

**What the agents agree to NOT do:**

- **Don't restore the per-application plugin classes** (Agent B's clearest "don't") — the deleted `ProducerLicensingPlugin`, etc. were retired explicitly because they conflated data with code. The right model is **one generic plugin (`ecosystem_viewer` itself) consuming any conformant data**.
- **Don't model `permitted_issuers` as both governance policy AND empirical observation** (Agent C's gotcha #1) — keep them separate. Policy lives in roles + qualification rules; observation, when it arrives, lives in a different field/index.
- **Don't reinvent edge operators** — I2I / NI2I / DI2I already exist in the ACDC spec; the inspector exposes them; the graph view renders them. Strengthen what's there before adding sibling concepts.

---

## Section 1.5 — Mapping to "The Ecosystem Pattern" frame

The Ecosystem Pattern doc (`keripy/docs/ecosystem-pattern.md`) lists ten core elements that any cooperative-ecosystem governance framework needs to address. Below we map each to the wallet plugin's scope: in / partial / out, with rationale. **The plugin is fundamentally a *trust-registry viewer + light governance editor*, not a framework authoring tool.** Several elements that are critical to a real ecosystem are explicitly out of scope here — they belong in human-readable charter documents, contracts, and governance bodies, not in a wallet's UI.

| # | Pattern element | Plugin scope | What we'd surface (if any) |
|---|---|---|---|
| 1 | Purpose & Scope | **Out** | An ecosystem's `description` field is decoration; framework-grade purpose statements live in the charter, not the wallet |
| 2 | Authority Root + Delegation Tree | **In, partial** | Authority Root = root role's `root_issuer_aids`; Delegation Tree = role hierarchy via `issuer_role_name`. We model the *trust-registry view* of the tree, not the legal granting docs |
| 3 | Roles & Membership Policies | **In** | This is the load-bearing addition (Stage 12–13). Roles + credential-based qualification rules ARE the membership policy in machine-readable form |
| 4 | Attestation Catalog | **In, partial** | Schemas-in-ecosystem already model the *catalog*. Disclosure modes, issuer/holder/verifier role bindings come along with Stage 12. Validity periods + revocation policy partially live in the schema (rd presence) |
| 5 | Trust Registry | **In** | Every ecosystem record IS a trust registry — list of legitimate schemas, list of legitimate issuers, role hierarchy. The plugin is essentially a personal trust-registry viewer |
| 6 | Risk Register & Trust Policies | **Out** | Belongs in the framework's controlled documents, not the wallet |
| 7 | Liability & Remedy Model | **Out** | Legal artifact, not a data structure for the wallet to model |
| 8 | Legal & Commercial Models | **Out** | Same |
| 9 | Compliance & Mutual Recognition | **In, deferred** | Mutual recognition is real plugin work: "this ecosystem accepts attestations from neighbor ecosystem X under rule Y." Stage 17+ territory; not the immediate goal but the model should not preclude it |
| 10 | Audit & Assurance Regime | **Out** | Same as Risk Register — framework artifact |

**The diagonal that emerges**: the wallet's reasonable scope is rows 2–5 plus eventual 9. It is the *machine-readable expression* of the parts of an ecosystem framework that need to drive automated verification and graph rendering. Charter, risk, liability, legal, commercial, audit live elsewhere. This boundary is healthy — keeping it sharp is what lets the plugin stay focused.

**Vocabulary alignment.** Where the Ecosystem Pattern doc's terms are clear, we adopt them verbatim:

| Synthesis term (was) | Pattern term (use) | Notes |
|---|---|---|
| "permitted issuer" | "Issuer (issuance role)" | The pattern doc's "Issuer" is a role family. Our PermittedIssuerEdge edge represents *role-membership-permitting-issuance*, which is consistent. Keep "PermittedIssuerEdge" as the data-model name; surface the user-facing label as "Issuer of <schema>" or "Permitted to issue <schema>" |
| "role" | "Role" | Same word; the pattern's §4.3 enumerates standard role families (Governing, Governed, Issuance, Custody, Verification, Independent oversight, Operations) — useful as a mental checklist when defining roles in an ecosystem, but the data model stores arbitrary user-named roles |
| "qualification rule" | "Membership Policy" | The Pattern's term covers more than credential qualification (it includes admission, suspension, restoration). The plugin's qualification rule is the credential-based subset |
| "ecosystem" | "Ecosystem" | Same |
| "permitted_issuers" data structure | "Trust Registry" | The whole `EcosystemRecord` is a small Trust Registry. `permitted_issuers` is one of its tables |

---

## Section 2 — Proposed data-model additions

The three agents propose compatible primitives. Synthesis below adopts the **vocabulary** that's clearest, the **scoping** Agent C proposed (smallest non-breaking change first), and the **discipline** all three converge on.

### 2.1 `RoleRecord` — new dataclass + Komer

```python
@dataclass
class RoleRecord:
    """A credential-qualified class of AID within an ecosystem.

    "Role" is a wallet-level convention overlay; the ACDC spec has no
    such primitive. The vLEI ecosystem implements equivalent structure
    via credential-chain-rooted hierarchies (see vLEI research §3).

    Membership is determined dynamically: an AID is *in* this role iff
    it holds a valid credential of `qualification_schema_said` issued
    by an AID that is itself in `issuer_role_name` (recursive, with
    `root_issuer_aids` as the base case to break recursion).
    """
    ecosystem_name: str = ""
    name: str = ""           # e.g., "state-doi", "qualified-producer"
    description: str = ""
    qualification_schema_said: str = ""
    """SAID of the schema whose holders qualify for this role."""
    issuer_role_name: str = ""
    """The role whose members are the authorized issuers of the
    qualification credential. Empty string means 'root role'."""
    root_issuer_aids: list[str] = field(default_factory=list)
    """When this is a root role (issuer_role_name=""), the
    enumerated AIDs that bootstrap the chain. Otherwise empty."""
    created_at: str = ""
    updated_at: str = ""
```

Stored in a new `rle.` Komer keyed by `(ecosystem_name, role_name)`.

The recursion is bounded: at the top of the role hierarchy is a *root role* with hard-listed `root_issuer_aids` (e.g., "GLEIF" in vLEI; "state-DOI" in the user's insurance scenario, until/unless that itself becomes credential-derived).

### 2.2 `EcosystemRecord` extension — non-breaking optional fields

```python
@dataclass
class EcosystemRecord:
    # ... existing fields unchanged ...

    # NEW (Stage 12+):
    issuer_qualification_rules: dict = field(default_factory=dict)
    """schema_said -> role_name. When set for a schema, ANY AID that
    is a member of role_name is a permitted issuer of that schema —
    in addition to (or instead of) AIDs enumerated in
    `permitted_issuers[schema_said]`. Both mappings are queried."""

    role_names: list[str] = field(default_factory=list)
    """Names of roles defined in this ecosystem. The actual RoleRecords
    live in the rle. Komer; this list is a convenience for iteration."""

    schema_version: int = 1
    """Wallet-internal version tag for forward-compatibility. Bumped
    when the record's schema changes in a way that needs migration
    detection. New records get the current version; old records read
    as version 1 by default."""
```

The rationale for both fields existing simultaneously: **`permitted_issuers` (per-AID enumeration) and `issuer_qualification_rules` (role-based qualification) are not mutually exclusive.** A small ecosystem may want hard-listed AIDs; a large governance framework wants role-based qualification; a hybrid ecosystem wants both ("in my role-driven ecosystem I want to also explicitly trust these specific AIDs"). The plugin's *resolver* (a new helper) checks both: an AID is a permitted issuer of a schema iff it's in the explicit list OR in any role named by the qualification rule.

### 2.3 New EcosystemBaser methods

CRUD for roles:
- `put_role(rec: RoleRecord)` — validates `ecosystem_name` exists, `qualification_schema_said` is a member of the ecosystem, `issuer_role_name` is either empty or a known role in this ecosystem
- `get_role(ecosystem_name, role_name) -> RoleRecord | None`
- `list_roles(ecosystem_name) -> list[RoleRecord]`
- `delete_role(ecosystem_name, role_name)` — cascades cleanup of `issuer_qualification_rules` entries pointing at the deleted role

Resolver:
- `resolve_role_members(ecosystem_name, role_name, vault) -> list[str]` — recursively walks the role chain, scans the vault's `vault.rgy.reger` for credentials matching the qualification, returns the AIDs of holders whose issuance chains terminate at a `root_issuer_aids` entry. Pure function over the vault state.
- `is_permitted_issuer(ecosystem_name, schema_said, aid, vault) -> bool` — checks both `permitted_issuers[schema_said]` (explicit list) and `issuer_qualification_rules[schema_said]` (role qualification, via the resolver).

### 2.4 What stays unchanged

- `permitted_issuers` — kept as-is. Existing UI, data, and design extension all continue to work. Role-based qualification is *additive*.
- `PermittedIssuerEdge` in the graph view — unchanged. The edge represents a permitted-issuer relationship regardless of whether it came from explicit enumeration or role qualification. (Future polish: visually distinguish the two — "explicit" with the existing solid line, "role-qualified" with a different stroke pattern.)
- The Annotation, History, and Membership records and their Komers — unchanged.

---

## Section 3 — How this maps onto the user's three examples

The user gave three concrete motivating scenarios. Mapping each onto the proposed model:

### 3.1 "State issuers (a category of AID), permitted to do XYZ"

In the new model:
- A `RoleRecord(name="state-doi", root_issuer_aids=["EAcm…CA-DOI", "EAcm…TX-DOI", …])` enumerates the state DOIs as the root role (no further qualification — they're the trust roots in this ecosystem).
- `issuer_qualification_rules["EProducerLicense…"] = "state-doi"` says: the ProducerLicense schema is issuable by any AID in the `state-doi` role.

The user can now add new state DOIs by editing the role's `root_issuer_aids` list — no per-schema permitted-issuer churn. Removing one cascades automatically (it's no longer in the role; the role's qualification rule still binds the schema).

### 3.2 "Producers (a category of AID), qualified by holding ProducerLicense"

In the new model:
- A `RoleRecord(name="qualified-producer", qualification_schema_said="EProducerLicense…", issuer_role_name="state-doi")` says: anyone holding a valid ProducerLicense issued by a state-doi role member is a qualified-producer.
- The `qualified-producer` role can then itself be referenced in another schema's qualification rule — e.g., a `QuoteRequest` schema with `issuer_qualification_rules["EQuoteRequest…"] = "qualified-producer"` would mean: any AID with a valid (chain-rooted-at-state-DOI) ProducerLicense may issue QuoteRequests.

The chain is recursive but bounded: `qualified-producer` → `state-doi` → root AIDs. Each level is one credential check.

### 3.3 "Maybe specify what credentials they need rather than which AIDs"

This *is* the model. The `qualification_schema_said` field IS "what credentials they need" expressed as a SAID. The `issuer_role_name` field is "issued by whom" expressed as a role reference (not a hard AID list).

The user's intuition was correct: this is exactly the layer that needs to land.

---

## Section 4 — Roadmap

Sequenced, with the smallest viable steps first. Each stage is implementable and shippable on its own — the user gets value at every stage, not just the end.

### Stage 12 — Roles, data model only (no UI)

*Pattern element: §3 Roles & Membership Policies (in scope), §2 Authority Root + Delegation Tree (partial — root_issuer_aids).*

**Scope**: data model + DB methods + tests, no user-facing UI yet.

- New `RoleRecord` dataclass + `rle.` Komer
- `EcosystemRecord.issuer_qualification_rules`, `role_names`, `schema_version` fields
- CRUD on EcosystemBaser: put/get/list/delete roles
- Resolver helpers: `resolve_role_members`, `is_permitted_issuer` (combines explicit + qualified)
- Unit tests: ~15-20 tests covering roles + qualification + cycles + cascades

**Why first**: lays the foundation. UI without data is empty; data without UI is invisible but tested-good. Stage 12 makes the data-model investment land cleanly.

**Estimated cost**: ~250-400 LOC, 1-2 sessions.

### Stage 13 — Roles UI, list-tab first

*Pattern element: §3 Roles & Membership Policies (in scope) + §5 Trust Registry (in scope — the page itself is a trust-registry viewer).*

**Scope**: surface roles in the ecosystem detail page's List tab.

- New "Roles" section between the Schemas and Issuer AIDs sections, with role cards: name, qualification schema (clickable), issuer role (clickable), root AIDs count, current member count (computed via resolver)
- Per-schema "Permitted issuers" sub-row on the schema member rows now also shows "(via role: state-doi)" when there's a qualification rule
- "+ Add role" affordance opens a small dialog: name, qualification schema picker, issuer role picker
- Right-click role card → "Edit" / "Delete"

**Why second**: roles need to be *manageable* before they can drive graph visualizations. The List tab is the keyboard-accessible, copy-paste-friendly surface — best for the initial creation/edit flow.

**Estimated cost**: ~300-500 LOC.

### Stage 14 — Roles + qualification in the graph view

*Pattern element: §2 Delegation Tree (in scope — the role hierarchy IS the delegation tree, rendered).*

**Scope**: the canvas surfaces roles as nodes and qualification edges.

- New `RoleNode` graphics item — distinct shape from issuer-sigil-circle (the design subagent should pick: a "constellation" of small dots? a halo around a placeholder sigil?)
- New `QualificationEdge` graphics item — schema → role, indicating "members of role qualify by holding this schema". Different stroke from PermittedIssuerEdge (perhaps dashed teal with a small "if" badge at the midpoint).
- The bottom row reorders to interleave roles between issuers, with role nodes spanning their member AID nodes (visual grouping).
- Drag-to-create extends: drag from a role node to a schema → creates an `issuer_qualification_rules` entry (analogous to the existing PermittedIssuerEdge drag).
- Side panel for a role: name, description, qualification schema, issuer role, current resolved members (with timestamps from registry checks).

**Why third**: this is where the ecosystem becomes *visualizable as a graph of governance*, not just a list of edges. It pays off the data model investment from Stage 12 and the UI investment from Stage 13.

**Estimated cost**: ~500-800 LOC. Substantial but well-scoped.

### Stage 15 — Schema lifecycle metadata (Agent A's #5 finding)

*Pattern element: §4 Attestation Catalog (in scope — schemas are attestation types; lifecycle metadata is part of the catalog).*

**Scope**: per-schema metadata — version, retirement, successor.

- `SchemaMetadataRecord` dataclass keyed by schema SAID, optional fields: human name (the wallet doesn't always have a clean title from the JSON Schema), version label, retirement_date, successor_said
- Surfaces on the schema detail page hero card: a "Retired" badge or "Superseded by X" link
- The schema-list cards on the overview show a small "v2" tag when there's a known successor in the wallet

**Why fourth**: lower urgency than roles, but the vLEI research called this out as a real EGF concept, and it's straightforward to model. Save for after the role infrastructure lands.

**Estimated cost**: ~200-300 LOC.

### Stage 16+ — Out of scope for this synthesis

Things the user / agents brought up but that should wait:
- **Authorization-credential boundary** (vLEI OOR AUTH / ECR AUTH pattern) — only meaningful once we render qualification chains; folds into a future "render the chain explicitly" task.
- **First-person projection lens** (Agent B's `ProjectionDef.lens`) — large UX change; requires the wallet's "active AID" concept to be more first-class. Defer.
- **Subscription / revocation cascade policy** (Agent B's `SubscriptionDef`) — depends on TEL-state polling infrastructure that doesn't exist yet.
- **General UEL (universal expression language) for preconditions** — Agent B explicitly flagged this as a tar pit.
- **Mutual-recognition rules** (Pattern element §9) — "this ecosystem accepts attestations from neighbor ecosystem X under rule Y." Real plugin work but conceptually expensive (cross-ecosystem trust composition); save for after Stages 12–15 prove out.

### Out of scope, period — pattern elements that aren't a wallet's job

Pattern elements §1, §6, §7, §8, §10 (Purpose, Risk Register, Liability, Legal/Commercial, Audit) are framework artifacts that live in human-readable charters and signed contracts. The wallet should never claim to model them. If a future reviewer suggests adding "a Risk Register section to the ecosystem detail page" — that's the wrong tool. Charters are written documents; the wallet shows the *trust-registry consequences* of those documents.

---

## Section 5 — What NOT to do

Distilled from the agents' gotchas:

1. **Don't restore the per-application Python plugin classes** (`ProducerLicensingPlugin`, etc.). The deleted code retired them with cause. Roles + qualification rules + manifest data is the right shape.
2. **Don't conflate `permitted_issuers` (governance policy) with empirical issuance observation.** When actual-issuance overlays land later, they go in a separate field/index.
3. **Don't migrate existing on-disk records.** The user's preference is clear (see git history for the brief migration code that was reverted). New fields get default values; the `schema_version` tag is informational, not a migration trigger. Existing records load with `issuer_qualification_rules={}` and `role_names=[]` and continue to work.
4. **Don't invent new edge operators.** I2I / NI2I / DI2I cover the chain-of-authority space the spec needs. Future polish should *visually distinguish* them, not add siblings.
5. **Don't bundle role membership resolution into every render.** The resolver scans the vault registry; cache results with explicit invalidation rather than computing every paint.
6. **Don't pretend the plugin is the framework.** The Ecosystem Pattern's ten elements include things (Risk, Liability, Audit) that are charter documents, not wallet data. Adding a "Risk Register tab" to the plugin would be a category error. The plugin is the *trust-registry view* of an ecosystem; it must stay there. When in doubt, ask: "is this something a wallet user clicks on, or something a governing body publishes in a PDF?"

---

## Section 6 — Open questions for the user

Before we plan Stage 12 in detail, three questions that affect the design:

### 6.1 Are roles per-ecosystem or shared across ecosystems?

**Current proposal**: per-ecosystem (the `RoleRecord.ecosystem_name` field). Two ecosystems both wanting "state-doi" would each define their own.

**Alternative**: roles are shared (cross-ecosystem). Pros: deduplication. Cons: governance ownership — who maintains the cross-ecosystem role definition? Increases complexity.

**Recommendation**: per-ecosystem for v1. If shared roles emerge as a real need, revisit then.

### 6.2 How dynamic is role membership?

The resolver scans the vault's credential registry to determine current members. This is point-in-time. Two scenarios:

- **Lazy resolution**: every UI render that needs members queries the registry. Simple, always-fresh, potentially expensive on large vaults.
- **Cached resolution**: members are cached in `RoleRecord.cached_member_aids` and refreshed on TEL events / explicit refresh. Faster reads, more state to manage.

**Recommendation**: start lazy. If performance bites, add caching in a follow-up.

### 6.3 Is `root_issuer_aids` enough for trust roots, or do we need something richer?

A root role's trust comes from the listed AIDs. What if the user wants to say "the trust root is whoever signs this configuration", or "the trust root is determined out-of-band by an OOBI / EGF document"?

**Recommendation**: enumerated AIDs are sufficient for v1. The vLEI itself starts from a single AID (GLEIF Root) — that's literally `root_issuer_aids=["EBA…GLEIF"]`. Anything richer is over-engineering until proven necessary.

### 6.4 Should the plugin link out to a charter / governance document?

The Ecosystem Pattern's §1 (Purpose & Scope) and the broader framework documents typically exist as PDFs, web pages, or controlled-document repositories. The plugin doesn't model these — but should it *link* to them? A `governance_url` field on `EcosystemRecord` (e.g., a URL or OOBI to the charter) would let the UI surface "Read the governance framework" without claiming to model the framework itself.

**Recommendation**: yes, add an optional `governance_url: str = ""` field in Stage 12 alongside the role fields. Surface it as a small link on the ecosystem detail page header. This honors the trust-registry-only scope while acknowledging the existence of the framework artifacts that sit upstream of it.

---

## Section 7 — Recommendation

**Proceed to Stage 12.** The data model investment is small and load-bearing. Stages 13 and 14 then unlock the user-stated goals (categories, qualification, multi-tier delegation) and naturally align with the existing UI surfaces (List tab, Graph tab).

Stage 11's polish items (selection-aware dimming, ghost-drop toasts, drag-cancel on focus loss) can interleave with Stage 12's data work — they're independent.

Once the user picks the answers to §6's three open questions, the implementation plan for Stage 12 is straightforward to write — the data shape is well-specified by the converged research.
