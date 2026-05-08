# vLEI Ecosystem Patterns: Research Notes for Ecosystem-Viewer Plugin

**Date:** 2026-05-08  
**Author:** Research pass via keri.host + web sources  
**Purpose:** Distill generic EGF primitives from the vLEI canonical example so the
Locksmith ecosystem-viewer plugin's data model can be extended to support real-world
ACDC governance ecosystems.

**Primary sources:**
- GLEIF vLEI EGF v4.0 Primary Document (2026-03-25)
  <https://www.gleif.org/organizational-identity/become-a-vlei-issuer-qvi/vlei-ecosystem-governance-framework/2026-03-25_vlei-egf-v4.0-primary-document_v1.2_final.pdf>
- WebOfTrust/vLEI GitHub — schemas and samples
  <https://github.com/WebOfTrust/vLEI>
- ACDC IETF draft (draft-ssmith-acdc-02/03) — spec primitives
  <https://www.ietf.org/archive/id/draft-ssmith-acdc-02.html>
- ToIP KSWG ACDC specification
  <https://trustoverip.github.io/kswg-acdc-specification/>
- SATP vLEI Binding draft (draft-smith-satp-vlei-binding-01)
  <https://datatracker.ietf.org/doc/html/draft-smith-satp-vlei-binding-01>
- vlei.wiki ACDC concept page
  <https://www.vlei.wiki/concept/acdc>

---

## 1. vLEI Overview: Layered Structure

The verifiable LEI (vLEI) ecosystem is GLEIF's production deployment of ACDC-based
verifiable credentials for organizational identity. It is the richest publicly documented
example of an ACDC Ecosystem Governance Framework (EGF).

### 1.1 Trust Layers

The vLEI defines five distinct trust layers, each populated by a specific actor class
(called a **role** in the EGF):

```
Layer 0 — GLEIF Root
  └─ Layer 1 — Qualified vLEI Issuers (QVIs)
       └─ Layer 2 — Legal Entities (LEs)
            ├─ Layer 3a — Official Organizational Role holders (OOR persons)
            └─ Layer 3b — Engagement Context Role holders (ECR persons)
```

Each layer corresponds to one or more **credential types** that establish membership
at that layer and authorize operations at the next layer down.

### 1.2 Credential Types and Their Issuance Flow

Six ACDC credential schemas are defined in
`schema/acdc/` of the `WebOfTrust/vLEI` repository:

| Short name   | Full schema name                                                        | Issuer role | Subject role |
|--------------|-------------------------------------------------------------------------|-------------|--------------|
| **QVI**      | Qualified vLEI Issuer vLEI Credential                                   | GLEIF (GEDA)| QVI org      |
| **LE**       | Legal Entity vLEI Credential                                            | QVI         | Legal Entity |
| **OOR AUTH** | Qualified vLEI Issuer OOR Authorization vLEI Credential                 | Legal Entity| QVI          |
| **ECR AUTH** | Qualified vLEI Issuer ECR Authorization vLEI Credential                 | Legal Entity| QVI          |
| **OOR**      | Legal Entity Official Organizational Role vLEI Credential               | QVI         | Natural person|
| **ECR**      | Legal Entity Engagement Context Role vLEI Credential                    | LE or QVI   | Natural person|

The credential SAIDs embedded in production schemas are:

- QVI schema SAID: `EBfdlu8R27Fbx-ehrqwImnK-8Cm79sqbAQ4MmvEAYqao`
- LE schema SAID: `ENPXp1vQzRF6JwIuS-mp2U8Uf1MoADoP_GqQ62VsDZWY`
- OOR AUTH schema SAID: `EKA57bKBKxr_kN7iN5i7lMUxpMG-s19dRcmov1iDxz-E`
- ECR AUTH schema SAID: `EH6ekLjSr8V32WyFbGe1zXjTzFs9PkTYmupJ9H65O14g`
- OOR schema SAID: `EBNaNu-M9P5cgrnfl2Fvymy4E_jvxxyjb70PRtiANlJy`
- ECR schema SAID: (see `legal-entity-engagement-context-role-vLEI-credential.json`)

### 1.3 The Authorization Credential Pattern (OOR AUTH / ECR AUTH)

A key non-obvious design: the Legal Entity **does not** directly issue OOR or ECR
credentials to persons. Instead:

1. The LE issues an **OOR AUTH** (or **ECR AUTH**) credential *to the QVI*,
   authorizing the QVI to issue a specific person's OOR (or ECR) credential. This
   authorization includes the person's name and role in its attribute block.
2. The QVI issues the OOR (or ECR) credential to the person, chaining back to the
   AUTH credential via the `e` (edges) section.

This allows the LE to retain ultimate semantic authority ("I authorized this role for
this person") while delegating the operational issuance work (KYC/identity verification,
key ceremony support) to the QVI.

### 1.4 Authorized Representatives (Multi-sig governance)

Each layer has a set of **Authorized Representatives** who constitute the multi-sig
signing group for that layer's AID:

- **GAR** — GLEIF Authorized Representative (≥7 GARs, 1/3 signing threshold per subgroup)
- **QAR** — QVI Authorized Representative (≥3 QARs, ≥2 required to co-sign)
- **LAR** — Legal Entity Authorized Representative (≥3 LARs, ≥2 required to co-sign)

These are not separate credential types in the ACDC sense — they are governance policies
on the multi-sig AID structure at each layer. The EGF documents them in the Technical
Requirements Part 1 (KERI Infrastructure).

---

## 2. Role / Category Concept

### 2.1 Abstract Roles, Not Hard-Enumerated AID Lists

The vLEI does **not** enumerate specific AIDs as "permitted issuers" for a given
credential type. Instead it defines **abstract roles** (QVI, Legal Entity, OOR holder,
ECR holder) and specifies which **role class** may issue each credential type.

The mechanism for expressing "any AID that holds a valid QVI credential issued by
GLEIF may issue LE credentials" is purely credential-based: the LE credential's `e`
section contains a `qvi` edge with:

```json
{
  "e": {
    "qvi": {
      "n": "<SAID of the QVI credential held by this issuer>",
      "s": "EBfdlu8R27Fbx-ehrqwImnK-8Cm79sqbAQ4MmvEAYqao"
    }
  }
}
```

The ACDC spec (draft-ssmith-acdc, Section 8.1.4) requires that validators confirm
the far-node ACDC's schema SAID matches the `s` field in the edge — this is the
**type-safe credential chain**. Combined with the I2I operator (see Section 3), this
enforces "the issuer of this LE credential must be the issuee (holder) of a credential
with schema SAID `EBfdlu8R27Fbx-...`."

The EGF document describes this as:
> "Qualification is the process by which GLEIF evaluates the suitability and sustainability
> of organizations seeking to operate within the vLEI ecosystem... as QVIs."

But the *technical enforcement* at credential-verification time is entirely via the
cryptographic chain — no explicit AID whitelist is required.

### 2.2 Role as "Holder of Valid Credential of Schema X Issued by Role Y"

The vLEI pattern treats role membership as a **derived property**:

> An AID is a QVI if and only if it is the issuee of a currently-valid (non-revoked)
> credential with schema SAID `EBfdlu8R27Fbx-ehrqwImnK-8Cm79sqbAQ4MmvEAYqao` issued
> by a GLEIF AID.

> An AID is a Legal Entity if and only if it is the issuee of a currently-valid LE
> credential (`ENPXp1vQzRF6JwIuS-...`) issued by a QVI (itself credential-qualified).

There is no out-of-band AID registry or whitelist. The role is entirely determined by
the credential graph — a property that makes the trust chain fully cryptographically
self-describing and auditable.

---

## 3. Qualification Rules

### 3.1 Credential-Driven Qualification (Primary Mechanism)

In the vLEI, qualification for every role is credential-driven:

- A QVI is qualified by holding a valid, unrevoked QVI credential from GLEIF.
- A Legal Entity is qualified by holding a valid, unrevoked LE credential from any
  QVI (itself credential-qualified).
- An OOR person is qualified by holding a valid OOR credential from a QVI, which
  chains to an OOR AUTH from the relevant LE, which chains to an LE credential.

The chain depth is: `OOR → OOR AUTH → LE → QVI` — four levels of credential chaining
from root to leaf credential.

### 3.2 Process-Driven Qualification (Out-of-Band, for QVIs only)

QVI qualification is the **one place** where an out-of-band process supplements the
credential chain. GLEIF's "Qualified vLEI Issuer Qualification Agreement" (a legal
contract) and the "vLEI Issuer Qualification Program Manual" define the due-diligence
process before GLEIF will issue the QVI credential. But once the credential is issued,
the trust chain is fully cryptographic thereafter.

This pattern — "off-chain diligence → root-level credential issuance → all downstream
trust is credential-based" — is a deliberate architectural choice in the EGF.

### 3.3 Enumeration Is Not Used

The vLEI explicitly avoids hard-enumerated AID lists as the mechanism for issuance
authorization. The GLEIF Root AID is the only "hardcoded" trust anchor, and its
identity is established via KERI key state (not an AID list).

### 3.4 Schema Registry as Qualification Anchor

The ACDC spec (draft-ssmith-acdc Section 3.6) states:
> "ACDC specific schema compliance requirements are usually specified in the eco-system
> governance framework for a given ACDC type. Because the SAID of a schema is a unique
> content-addressable identifier... compliance can be enforced by comparison to the
> allowed schema SAID in a well-known publication or registry of ACDC types for a given
> EGF."

The vLEI's Technical Requirements Part 3 ("Credential Schema Registry") is precisely
this registry. Schema SAIDs are the stable, content-addressed identifiers that glue the
EGF's policy layer to the ACDC's cryptographic enforcement layer.

---

## 4. Delegation / Multi-Tier Authority

### 4.1 Chain-of-Authority via ACDC `e` Section Edges

The primary delegation mechanism in vLEI is the ACDC `e` (edges) section combined with
the **I2I** (Issuer-to-Issuee) edge operator. From the ACDC spec:

> "I2I: The Issuer AID of the current ACDC MUST be the Issuee AID of the node that the
> edge points to."

This enforces the delegation chain cryptographically:

```
LE credential (i=QVI_AID)
  └─ e.qvi → QVI credential (a.i=QVI_AID)
               [I2I: issuer of LE must be issuee of QVI]

OOR credential (i=QVI_AID)
  └─ e.auth → OOR AUTH credential (i=LE_AID)
               └─ e.le → LE credential (a.i=LE_AID)
                          └─ e.qvi → QVI credential
```

The ACDC spec describes this as:
> "A chain of Issuer-To-Issuee-To-Issuer targeted ACDCs in which each Issuee becomes
> the Issuer of the next ACDC in the chain can be used to provide a chain-of-authority."
> (draft-ssmith-acdc, "Special Unary Operators" section)

### 4.2 The Three Edge Operators

The ACDC spec defines three unary operators for the `o` field in an edge sub-block:

| Operator | Meaning | vLEI Usage |
|----------|---------|------------|
| **I2I** (default) | Issuer of this ACDC MUST be the Issuee of the far-node ACDC | LE→QVI, OOR→OOR AUTH, ECR→ECR AUTH |
| **NI2I** | No constraint on issuer/issuee relationship | Reference edges, contextual links |
| **DI2I** | Issuer of this ACDC MUST be either the Issuee OR a delegated AID of the Issuee of the far-node ACDC | Delegated sub-AID issuance scenarios |

The OOR credential uses `"o": "I2I"` explicitly in its `auth` edge, ensuring the QVI
that issues the OOR must be the same QVI that received the OOR AUTH from the LE.

### 4.3 The Authorization Credential as a Delegation Primitive

The OOR AUTH / ECR AUTH pattern is a **delegation-via-credential** primitive that does
not exist in the ACDC spec directly — it is a vLEI convention built from spec primitives:

1. A parent role (LE) issues a targeted credential (`a.i = QVI_AID`) with a specific
   schema that means "authorization to issue type X for subject Y."
2. The authorized party (QVI) uses that credential as a chain edge in the downstream
   credential they issue.
3. The I2I operator on that edge cryptographically verifies that the issuer of the
   downstream credential is the holder of the authorization.

This pattern separates **semantic authority** (who authorized the role) from **operational
issuance** (who performed the issuance ceremony). It is a general pattern applicable to
any ACDC ecosystem that needs to delegate issuance across organizational boundaries.

### 4.4 KERI Delegation vs. ACDC Delegation

The vLEI also uses KERI **cooperative delegation** (KERI spec, delegation section) at the
AID level — GLEIF's root AID (offline, cold) delegates to GLEIF External (GEDA, operational).
This is distinct from ACDC credential chaining:

- **KERI delegation** (DI2I in ACDC terms): An AID delegates signing authority to a
  child AID. The child's inception event is anchored in the parent's KEL.
- **ACDC credential chaining** (I2I): A credential's issuer must hold a specific upstream
  credential, enforced by schema SAID matching in the edge block.

Both mechanisms compose in the vLEI: the GEDA (delegated GLEIF AID) issues QVI credentials
(ACDC chain), and the QVI may itself use KERI delegation if its own operational structure
requires it.

---

## 5. Generic Primitives

The following 5 primitives are abstracted from the vLEI and apply to any ACDC ecosystem.
Each is labeled by source:
- **(ACDC spec)** — defined in draft-ssmith-acdc
- **(vLEI convention)** — vLEI-specific pattern built from spec primitives
- **(general EGF)** — broader EGF concept applicable to any ToIP-style governance framework

---

### Primitive 1: Schema-SAID-Constrained Edge (ACDC spec, §8.1.4)

**Definition:** An edge in an ACDC's `e` section may specify `"s": "<SAID>"`, which
requires the credential at the far node to conform to the schema identified by that SAID.
Validators MUST check that the far-node ACDC's `s` field matches the edge's `s` field.

**Why it matters:** This is the type-safety mechanism of credential chains. It prevents
an issuer from substituting an unrelated credential to satisfy a chain requirement. In
the vLEI, every cross-layer edge specifies the exact schema SAID of the upstream
credential, making the chain tamper-evident and schema-version-locked.

**Plugin implication:** The plugin must track the schema SAIDs that appear in edge
definitions, not just the schema SAIDs of top-level credentials. Each schema's `e`
section is itself a structural artifact describing the credential graph the EGF demands.

---

### Primitive 2: I2I / NI2I / DI2I Issuance Operator (ACDC spec, §8.6.9–8.6.11)

**Definition:** The `o` field in an ACDC edge sub-block controls the issuer/issuee
relationship the validator must enforce between the issuing ACDC and the far-node ACDC:
- `I2I` (default): issuer of current ACDC must be issuee of far-node ACDC.
- `NI2I`: no issuer/issuee constraint.
- `DI2I`: issuer must be issuee or a KERI-delegated sub-AID of the issuee.

**Why it matters:** The I2I operator is the cryptographic encoding of "an AID may issue
this credential type only if it holds a valid upstream credential of the required type."
This is what makes role membership credential-driven rather than enumeration-driven.

**Plugin implication:** The plugin's edge model must distinguish `I2I`, `NI2I`, and `DI2I`
edges — they have fundamentally different governance meanings. An I2I edge is an
issuance-authority constraint; an NI2I edge is a reference or context link.

---

### Primitive 3: EGF Schema Registry (ACDC spec §3.6 + vLEI convention)

**Definition (ACDC spec):** An EGF may maintain a "well-known publication or registry of
ACDC types" keyed by schema SAID. Validators confirm a presented ACDC's schema SAID
against this registry before accepting it.

**Definition (vLEI convention):** Technical Requirements Part 3 is the vLEI's concrete
instantiation — a Credential Schema Registry that maps human-readable credential names to
schema SAIDs, versioning policy, and retirement dates.

**Why it matters:** Schema SAIDs are the stable join keys between the EGF's policy
documents and the cryptographic objects. The registry is what allows an EGF to evolve
schemas (by retiring old SAIDs and publishing new ones) without breaking the human-readable
governance narrative.

**Plugin implication:** The plugin needs a first-class `SchemaRegistryRecord` concept (per
ecosystem) that maps schema SAIDs to human-readable names, descriptions, versions, and
retirement status — not just a flat list of SAIDs.

---

### Primitive 4: Role as Credential-Holding Class (vLEI convention, generalizable)

**Definition:** A **role** in an ACDC EGF is an abstract named category of AIDs defined
by a qualification rule of the form:
> "An AID belongs to role R if and only if it is the issuee of a currently-valid
> (non-revoked) credential of schema SAID S issued by an AID belonging to role P."

Roles are arranged in a directed graph where edges encode the "issued by role P" relation.
The root role's qualification is the root-of-trust AID (hardcoded or publicly-known KEL).

**Why it matters:** This is the critical abstraction the current plugin is missing.
`permitted_issuers: dict[schema_said, list[AID]]` is an enumeration of concrete AIDs. The
vLEI uses zero hard-enumerated AID lists — it only names roles and credentials. A wallet
that understands roles can express "any AID holding a valid QVI credential may issue LE
credentials" without knowing the specific QVI AIDs in advance.

**Plugin implication:** Needs a `RoleRecord` that has: a name, a qualification rule
(schema SAID + issuer role), and optionally a cached set of known-qualifying AIDs for
lookup performance. The `permitted_issuers` mapping on `EcosystemRecord` should be
generalized to map `schema_said → role_name` (not `schema_said → list[AID]`).

---

### Primitive 5: Authorization Credential as Delegation Boundary (vLEI convention)

**Definition:** A **delegation boundary** arises when a role at layer N needs to
authorize a role at layer N+1 to issue credentials on its behalf to a specific subject,
without giving up its ultimate semantic authority. The pattern is:
- Layer-N AID issues an AUTH credential (schema: `AUTH_SCHEMA`) targeted at the
  layer-N+1 issuer AID, with the subject's identity in the attributes.
- Layer-N+1 issuer chains the downstream credential's `e` section back to the AUTH
  credential using I2I.
- Revocation of the AUTH credential by the layer-N AID cascades to the downstream
  credential (via ACDC revocation propagation rules).

**Why it matters:** This pattern decouples semantic authority (who has the right to grant
a role) from operational authority (who performs the issuance ceremony). It is essential
for any ecosystem where identity verification and governance are split across organizations,
as in the vLEI (GLEIF sets governance, QVIs perform KYC).

**Plugin implication:** The data model needs an `AuthorizationEdgeType` concept: an edge
where the near-node schema is a "role authorization" schema rather than the final role
credential. The graph view should render AUTH→OOR and AUTH→ECR edges differently from
direct issuance edges.

---

## 6. What the Current Plugin Is Missing

The current `EcosystemRecord` (in `db.py`) models:
- `schema_saids: list[str]` — flat set of credential schemas in the ecosystem
- `issuer_aids: list[str]` — flat set of specific AIDs considered issuers
- `permitted_issuers: dict[schema_said, list[AID]]` — specific AIDs per schema

This is sufficient for toy ecosystems and simple single-layer trust scenarios. For a
real vLEI-style EGF, the following are missing:

1. **Role/category records** — No concept of an abstract role ("QVI", "Legal Entity").
   Every issuer must be enumerated as a specific AID. The plugin cannot express
   "any AID holding a valid LE credential is a Legal Entity."

2. **Qualification rules** — No data structure to express "role R is conferred by
   holding schema SAID S issued by role P." The credential-based qualification chain
   cannot be modeled.

3. **Schema registry with human-readable metadata** — Schema SAIDs are stored as opaque
   strings with no version, description, retirement status, or canonical name. The EGF's
   schema registry concept (Technical Requirements Part 3) has no representation.

4. **Edge operator tracking** — The plugin reads the `e` section of ACDC schemas to
   render chain edges in the graph, but does not record or distinguish the edge operator
   type (I2I vs NI2I vs DI2I). An NI2I edge is structurally different from an I2I edge
   (reference vs. issuance authority) but both appear the same in the current graph view.

5. **Authorization credential type flag** — No way to mark a schema as an "authorization
   credential" (like OOR AUTH or ECR AUTH) vs. a "role credential" (like OOR or ECR).
   These have different governance semantics: an authorization schema is a delegation
   instrument, not an end-user identity assertion.

6. **Root-of-trust AID per ecosystem** — No `root_aid` field on `EcosystemRecord`. In
   any real EGF, there is at least one well-known root AID (GLEIF Root AID in vLEI) from
   which all trust chains descend. Without this, the plugin cannot validate credential
   chains — it has no anchor.

7. **Multi-sig / signing threshold policy per role** — The vLEI specifies ≥2-of-3 LAR
   signing for every LE operation. No governance policy on the signing quorum of each
   role is representable in the current model.

8. **Revocation registry reference per schema** — Each credential type specifies the
   PTEL (Public Transaction Event Log) registry format and availability requirements.
   The plugin has no `revocation_registry_type` per schema.

9. **Credential-chain depth annotation** — No record of the maximum valid chain depth
   (e.g., vLEI root → QVI → LE → OOR is depth 3). This matters for validation and
   for rendering the graph with correct layer separation.

10. **Schema version / SAID retirement records** — When an EGF retires a schema SAID and
    publishes a successor, the plugin has no way to record this relationship. Old
    credentials issued against the retired SAID remain valid per spec rules, but the
    plugin has no way to surface "this schema has been superseded."

11. **EGF source document reference** — No URI or SAID linking the ecosystem record to
    the authoritative EGF document (e.g., the GLEIF EGF PDF). Ecosystems can be created
    manually without any traceable governance document.

12. **Role-scoped OOBIs** — The vLEI defines a GLEIF OOBI that allows wallets to
    bootstrap trust in the GLEIF root AID. There is no `bootstrap_oobis` list per role
    or per ecosystem root.

13. **Issuer role constraint on permitted-issuers mapping** — The current
    `permitted_issuers: dict[schema_said, list[AID]]` conflates two distinct concepts:
    "which AIDs may issue this schema" (a governance policy) and "which AIDs have I
    personally observed issuing this schema" (an empirical observation). These need
    to be separate fields, or the governance policy needs to be expressed as a role
    reference rather than an AID list.

14. **Delegation type on edges** — No distinction between direct-issuance edges
    (QVI issues LE) and authorization-mediated issuance edges (LE issues OOR AUTH →
    QVI issues OOR). The graph renders both as equivalent chain edges.

15. **Ecosystem-level governance metadata** — No `governance_authority` field (the
    organization responsible for the EGF), no `effective_date`, no `version` string.
    An ecosystem record is just a name and a description, with no institutional context.

---

## Appendix A: vLEI Credential Chain Diagram

```
GLEIF Root AID (cold)
  │  (KERI delegation)
  ▼
GLEIF External (GEDA)
  │  issues ──────────────────────────────────────────────┐
  ▼                                                       │
QVI credential                                            │ schema: EBfdlu8R27...
  (issuee = QVI org AID)                                 │
                                                          │
QVI org AID ─── issues ──────────────────────────────────┤
  │                                                       ▼
  │  issues LE cred ──────────────────────────────────┐  LE e.qvi → QVI cred (I2I)
  │                                                   │  schema: ENPXp1vQzR...
  │                                                   │
Legal Entity AID ─── issues ───────────────────────┐  │
  │                                                  ▼  ▼
  │  issues OOR AUTH ──────────────────────────────────────┐
  │  (to QVI)           e.le → LE cred (I2I)              │
  │                     schema: EKA57bKBKxr...            │
  │                                                       │
  │  issues ECR AUTH ──────────────────────────────────┐  │
  │  (to QVI)           e.le → LE cred (I2I)           │  │
  │                     schema: EH6ekLjSr8...           │  │
  │                                                    OOR AUTH  ECR AUTH
  │                                                     │         │
  └──────────────────────────────────────────           │         │
                                            QVI issues OOR        QVI/LE issues ECR
                                            e.auth → OOR AUTH (I2I)  e.auth → ECR AUTH (I2I)
                                            OR                        e.le → LE cred
                                            LE issues ECR directly
```

---

## Appendix B: ACDC Spec Section Reference Table

| Concept | ACDC spec section | Notes |
|---------|-------------------|-------|
| Edge section (`e` field) | §8 "Edge Section" | Top-level section on edges |
| Schema constraint in edge (`s` field) | §8.1.4 | Validator MUST check SAID match |
| I2I operator | §8.6.9 "Unary I2I" | Default; issuer = issuee of far node |
| NI2I operator | §8.6.10 "Unary NI2I" | Removes I2I constraint |
| DI2I operator | (same section) | Issuer = issuee or delegated AID |
| EGF and schema registry | §3.6 "Composable JSON Schema" | EGF specifies allowed schema SAIDs |
| Rules section (`r` field) | §7–7.6 | Ricardian contract, terms-of-use |
| Chain-of-authority via I2I | §8.6.9 and "Targeted ACDC" | Issuee becomes next issuer |
| EGF definition | §3.6 | EGF = Ecosystem Governance Framework |

---

## Appendix C: vLEI-Specific vs. Spec-Defined vs. General EGF

| Primitive | Classification |
|-----------|---------------|
| Schema-SAID-constrained edge | **ACDC spec** (§8.1.4) |
| I2I / NI2I / DI2I operators | **ACDC spec** (§8.6.9–11) |
| EGF schema registry concept | **ACDC spec** (§3.6) + vLEI instantiation |
| Role as credential-holding class | **vLEI convention** (generalizable to any ACDC EGF) |
| AUTH credential delegation boundary | **vLEI convention** (no ACDC spec section; built from spec primitives) |
| Root-of-trust AID per ecosystem | **General EGF** (ToIP metamodel Layer 1) |
| Multi-sig quorum per role | **vLEI convention** (KERI multi-sig, not ACDC spec) |
| Schema retirement / successor records | **General EGF** (schema registry lifecycle) |
| Governance document reference | **General EGF** (ToIP metamodel) |
