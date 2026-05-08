# Current-State Audit: `ecosystem_viewer` Data Model

**Date:** 2026-05-08  
**Scope:** `src/locksmith/plugins/ecosystem_viewer/db.py`  
**Purpose:** Catalog precisely what `EcosystemRecord` and `EcosystemBaser`
model today, then map the gaps against the four stated goals:
1. AID categories / roles (abstract groupings, not AID lists)
2. Credential-based qualification (role membership derived from held credentials)
3. Multi-tier delegation (chartering authority → operational issuer → end issuer)
4. General EGF-style modeling

Cross-references: `2026-05-08-vlei-ecosystem-patterns.md` (vLEI research)
and `2026-05-08-applications-archaeology.md` (deleted `applications/` archaeology).

---

## 1. Current Data Model — Exhaustive Inventory

### 1.1 `EcosystemRecord` (stored in `eco.` Komer)

```python
@dataclass
class EcosystemRecord:
    name: str = ""
    description: str = ""
    schema_saids: list[str] = field(default_factory=list)
    issuer_aids: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    source_kind: str = "manual"
    source_url: str = ""
    permitted_issuers: dict = field(default_factory=dict)
```

**Field-by-field analysis:**

| Field | Python type | Concept modeled | What is NOT modeled |
|---|---|---|---|
| `name` | `str` | Primary key; user-chosen display name | No namespace or URI form; no external EGF identifier |
| `description` | `str` | Free-text human summary | No governance document reference (URI/SAID linking to authoritative EGF PDF) |
| `schema_saids` | `list[str]` | Flat set of ACDC schema SAIDs that belong to this ecosystem | No per-schema metadata: no canonical name, no role designation, no version, no retirement status. No schema-to-schema edge structure at the `EcosystemRecord` level. |
| `issuer_aids` | `list[str]` | Flat set of AID strings considered "issuers" in this ecosystem | No role assignment per AID. No root-of-trust flag. No abstract role reference (the AID "is a QVI" is not expressible). No multi-sig policy. |
| `created_at` | `str` | ISO8601 creation timestamp | — |
| `updated_at` | `str` | ISO8601 last-modification timestamp | No `version` integer for change tracking. |
| `source_kind` | `str` | Provenance enum: `'manual'`, `'imported_oobi'`, `'imported_file'` | No `effective_date`, no `governance_authority` org, no EGF version string. |
| `source_url` | `str` | OOBI/file URL when sourced externally | Not a content-addressable SAID; can't verify the source is authentic. |
| `permitted_issuers` | `dict` (typed: `dict[str, list[str]]` by convention) | Per-schema: which specific AIDs are "permitted issuers" within this ecosystem. The spec's EGF concept made wallet-first-class. | The dict's value type is `list[str]` (AID strings), not `list[str \| RoleRef]`. Role-based qualification ("any AID holding schema X") is not expressible. The gap between "governance policy" and "empirical observation" is not distinguished: if Acme has issued one credential and GLEIF is the approved issuer, the field can't express both simultaneously. |

**What `EcosystemRecord` silently omits:**

- Any root-of-trust AID designation (the anchor for chain validation)
- Schema-to-schema edge structure (which schemas have I2I edges to which)
- Abstract role definitions (named groupings of AIDs by qualification rule)
- Qualification rules ("a member of role R holds credential of schema S issued by role P")
- Revocation cascade / subscription rules (what to do when an upstream schema's instance is revoked)
- Reactive policies (automated cross-application reaction to lifecycle events)
- EGF governance metadata (authority org, effective date, version, document SAID)
- Bootstrap OOBIs (per-role or per-root OOBI for wallet onboarding into the ecosystem)

---

### 1.2 `AnnotationRecord` (stored in `ann.` Komer)

```python
@dataclass
class AnnotationRecord:
    kind: AnnotationKind = AnnotationKind.SCHEMA
    target: str = ""
    note: str = ""
    tags: list[str] = field(default_factory=list)
    updated_at: str = ""
```

| Field | Concept | What's not there |
|---|---|---|
| `kind` | Enum: `SCHEMA`, `AID`, `CREDENTIAL`, `ECOSYSTEM` | No `ROLE` kind — once roles exist as a first-class concept they will need annotations |
| `target` | SAID, AID, or ecosystem name being annotated | One note per `(kind, target)` pair — no multi-note history per target |
| `note` | Freeform markdown-ish text | No structured fields (e.g., trust level, risk flag) |
| `tags` | `list[str]` freeform tags | No tag vocabulary; no tag hierarchy |
| `updated_at` | Last modification timestamp | No creation timestamp; no author AID (annotations are personal-wallet state, so author = vault owner, but this is implicit) |

**What `AnnotationRecord` would need to support new goals:**

A new `AnnotationKind.ROLE` variant once `RoleRecord` exists. Otherwise the model is extensible as-is — the composite key `(kind.value, target)` means adding the new enum value and using the role's name as `target` is sufficient.

---

### 1.3 `DiscoveryEvent` (stored in `his.` Komer)

```python
@dataclass
class DiscoveryEvent:
    kind: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: str = ""
```

| Field | Concept | What's not there |
|---|---|---|
| `kind` | Free-form label (`'oobi_resolved'`, `'ecosystem_added'`, `'annotation_added'`) | No formal event taxonomy; adding a `role_qualified` event would require callers to agree on the string |
| `payload` | Arbitrary dict for event data | No schema; no required fields beyond what callers happen to put in |
| `timestamp` | ISO8601 string, also the Komer key | Key collision if two events share the same millisecond timestamp (unlikely but theoretically possible; the Komer's `pin()` would silently overwrite) |

This record is **audit-trail only** and does not drive any logic. It requires no changes for the new goals beyond callers adding new `kind` values for role-related events.

---

### 1.4 `_MembershipRecord` (stored in `smbr.` and `ambr.` Komers)

```python
@dataclass
class _MembershipRecord:
    ecosystem_names: list[str] = field(default_factory=list)
```

| Field | Concept | What's not there |
|---|---|---|
| `ecosystem_names` | Set-as-list of ecosystem names keyed to a SAID or AID | Only tracks which ecosystems a SAID/AID belongs to. Doesn't track which ecosystems it is a *permitted issuer* in. Doesn't track which ecosystems it qualifies as a *role member* in. |

The two Komer subkeys:
- **`smbr.` (`schema_membership`):** keyed by schema SAID → `_MembershipRecord`
- **`ambr.` (`aid_membership`):** keyed by AID → `_MembershipRecord`

Both use the same `_MembershipRecord` shape. The `smbr.` and `ambr.` indexes are maintained in sync with the `eco.` primary store by `put_ecosystem` diffing old vs new member sets. The cleanup is correct and well-tested.

---

### 1.5 `EcosystemBaser` — Komer subkeys summary

| Subkey | Key | Schema | Purpose |
|---|---|---|---|
| `eco.` | `(name,)` | `EcosystemRecord` | Primary record: grouping + permitted issuers |
| `ann.` | `(kind.value, target)` | `AnnotationRecord` | User notes + tags on any artifact |
| `his.` | `(timestamp,)` | `DiscoveryEvent` | Chronological audit trail |
| `smbr.` | `(schema_said,)` | `_MembershipRecord` | Reverse: schema → which ecosystems |
| `ambr.` | `(aid,)` | `_MembershipRecord` | Reverse: AID → which ecosystems |

**No current subkeys for:**
- Role definitions
- Qualification rules
- Schema metadata registry (human names, versions, retirement)
- Subscription / policy rules

---

## 2. Reverse-Index Coverage

### 2.1 What exists today

| Query | Index | Method |
|---|---|---|
| "Which ecosystems contain schema S?" | `smbr.(said,)` | `ecosystems_for_schema(said)` |
| "Which ecosystems contain AID A?" | `ambr.(aid,)` | `ecosystems_for_aid(aid)` |
| "Which AIDs are permitted issuers of schema S in ecosystem E?" | inline in `EcosystemRecord.permitted_issuers[said]` | `permitted_issuers_for(eco, said)` |

### 2.2 What the new goals require (not currently stored)

| Query needed | Implied index or computation | Classification |
|---|---|---|
| "Which AIDs qualify for role R in this ecosystem?" | Derived: scan wallet credentials for issuees holding schema S from role P. No stored index. | **Computed at query time** from `vault.rgy.reger`. Expensive for large wallets. A cached `rmbr.` (role membership) reverse index keyed by `(ecosystem_name, role_name, aid)` → `bool` would enable O(1) lookup but requires cache invalidation when new credentials appear. |
| "Which schemas have I2I edges to schema S?" | Derived from `ACDCSchemaInspection.edge_requirements`. Not stored in `EcosystemBaser`. | **Computed at render time** from inspector. Fine as-is if derived per-render; would need a graph cache for large ecosystems. |
| "Which roles are the permitted issuers of schema S in ecosystem E?" | New index once `permitted_issuers` generalizes to `dict[str, list[str \| RoleRef]]` | New: per-role permitted-issuer lookup, not currently expressible |
| "Which AIDs are root-of-trust for ecosystem E?" | New field on `EcosystemRecord`: `root_aids: list[str]` | Trivial to add |
| "Given this schema SAID, what is its canonical human-readable name in ecosystem E?" | New: per-ecosystem schema registry record | New `SchemaDescriptorRecord` or inline dict on `EcosystemRecord` |

---

## 3. What the Inspector Already Exposes

`ACDCSchemaInspection` and `ACDCInspection` (from `src/locksmith/acdc/inspector.py`)
expose primitives that the new governance modeling should consume directly:

### 3.1 From `ACDCSchemaInspection`

```python
schema_said: str                      # stable join key to EcosystemRecord.schema_saids
title: str                            # human name — could populate SchemaDescriptorRecord
description: str                      # ditto
credential_type: str | None           # convention field on most ACDC schemas
schema_version: str | None            # version string
requires_nonce: bool                  # private variant — instances can't be correlated
requires_targeted: bool               # schema forces issuee — role membership expressible
requires_registry: bool               # revocable credential — subscription logic relevant
edge_requirements: tuple[SchemaEdgeRequirement, ...]
```

**`SchemaEdgeRequirement`** is the most directly useful:

```python
@dataclass(frozen=True)
class SchemaEdgeRequirement:
    name: str
    target_schema_said: str | None  # the chained schema SAID — the "upstream qualification" anchor
    operator_constraint: tuple[str, ...] | None
    operator_locked: str | None     # I2I/NI2I/DI2I locked in schema
    requires_operator: bool
```

The `target_schema_said` is precisely the "qualification schema SAID" in the vLEI
research's "Role as credential-holding class" primitive (vLEI §4, Primitive 4). When
a schema has an `edge_requirements` entry with `operator_locked="I2I"` and a non-null
`target_schema_said`, that entry encodes "the issuer of this credential must hold a
valid credential of `target_schema_said`." A `QualificationRule` record in the new
model could be derived directly from this without re-parsing schema bytes.

### 3.2 From `ACDCInspection`

```python
issuer_aid: str            # who issued this specific instance — feeds "observed issuers" vs "permitted issuers"
issuee_aid: str | None     # the holder — for role qualification checks
schema_said: str           # join key to schema registry
registry_said: str | None  # TEL SAID — for revocation state check
is_private: bool           # affects whether the credential can be correlated
is_targeted: bool          # targeted ACDCs can carry I2I chain guarantees
is_self_issued: bool       # trust posture — an attestation about oneself
is_self_attested: bool     # untargeted self-claim
edges: tuple[EdgeInspection, ...]  # actual edge data in a specific instance
```

The `issuer_aid` + `schema_said` pair is what a "credential-based qualification check"
reads at runtime: "does a given AID hold at least one valid (non-revoked) credential
of schema S?" — computable by scanning `vault.rgy.reger` and calling `inspect_acdc`
on each result, checking `issuer_aid` equals the AID of the qualification-granting
issuer role.

### 3.3 How inspector feeds role/qualification logic

```
Goal: "is AID X a member of role 'QVI'?"

Role definition (new RoleRecord, see §4.1):
  qualification_schema_said = "EBfdlu8R27Fbx-ehrqwImnK-8Cm79sqbAQ4MmvEAYqao"
  issuer_role = "gleif_root"   (or issuer_aids = ["<GLEIF root AID>"] for the trust anchor)

Algorithm:
  for cred in vault.rgy.reger.cloneCreds():
      insp = inspect_acdc(cred.sad)
      if (insp.schema_said == role.qualification_schema_said
          and insp.issuee_aid == X
          and is_not_revoked(vault.rgy, insp)):
          return True   # X qualifies
  return False
```

All the primitives needed for this check already exist in the inspector. What's
missing is the `RoleRecord` that carries the `qualification_schema_said` and the
`issuer_role` reference — that is the new data model addition.

---

## 4. Gaps to Address — By User Goal

### 4.1 Goal 1: AID Categories / Roles

**What's missing:** There is no `RoleRecord` concept. `issuer_aids: list[str]`
is the only grouping mechanism, and it is an enumerated AID list.

**Vocabulary:** vLEI research calls this "Role as credential-holding class"
(Primitive 4). The archaeology research calls it `AuthorizationDef(principal=
"holder_of(<credential_id>)")`.

**New dataclass needed:**

```python
@dataclass
class RoleRecord:
    """An abstract named category of AIDs in an ecosystem.

    A role is defined by a qualification rule: an AID belongs to this
    role iff it is the issuee of a currently-valid (non-revoked)
    credential of `qualification_schema_said` issued by an AID whose
    role is `issuer_role_name`.

    For the root role (no upstream issuer), `issuer_role_name` is None
    and `root_issuer_aids` enumerates the concrete trust-anchor AIDs.

    Convention overlay — the ACDC spec does not define "role."
    See vLEI research §2.1 and §4 (Primitive 4).
    """
    ecosystem_name: str = ""      # owning ecosystem (join key)
    name: str = ""                # unique within ecosystem (e.g. "qvi", "legal_entity")
    display_name: str = ""        # human label ("Qualified vLEI Issuer")
    description: str = ""
    qualification_schema_said: str = ""
    """The schema SAID whose credential, held validly, confers this role."""
    issuer_role_name: str = ""
    """The role whose members may issue the qualifying credential.
    Empty string = no upstream role constraint (use root_issuer_aids)."""
    root_issuer_aids: list[str] = field(default_factory=list)
    """Trust-anchor AIDs for the root role, or for roles whose issuer
    is not itself credential-qualified (e.g. the GLEIF root AID)."""
    cached_member_aids: list[str] = field(default_factory=list)
    """Performance cache of currently-qualified AIDs. NOT authoritative;
    must be revalidated against vault.rgy on use."""
```

**New `EcosystemBaser` Komer:** `rle.` subkey, keyed by
`(ecosystem_name, role_name)`.

**New reverse index:** `rmbr.` (role membership), keyed by `(ecosystem_name, aid)` →
`list[str]` of role names the AID currently qualifies for. Cache-only; invalidated
on new credential arrival or revocation event from `vault.signals`.

**`EcosystemRecord` change needed:** Minimal. Add:

```python
root_aids: list[str] = field(default_factory=list)
"""Trust-anchor AIDs for this ecosystem — the root-of-trust from which
all credential chains descend. In vLEI this is the GLEIF root AID."""
```

---

### 4.2 Goal 2: Credential-Based Qualification

**What's missing:** `permitted_issuers: dict[str, list[str]]` stores concrete AID
lists. It cannot express "any AID holding a valid credential of schema S from a
member of role R is a permitted issuer."

**Vocabulary:** vLEI research §3.1 (credential-driven qualification) and
§3.3 (enumeration is not used). Archaeology §2.7 `AuthorizationDef(principal=
"holder_of(<schema_said>)")`.

**Smallest non-breaking change to `EcosystemRecord`:**

Add an optional field alongside `permitted_issuers`:

```python
issuer_qualification_rules: dict = field(default_factory=dict)
"""schema_said -> role_name | None. Where non-None, any AID
that qualifies for `role_name` in this ecosystem is a permitted
issuer of that schema — supplementing or replacing the explicit
AID list in `permitted_issuers`. Convention overlay.

Empty dict = no credential-based qualification configured;
fall back entirely to `permitted_issuers` for legacy behavior."""
```

The type is `dict[str, str]` (schema_said → role_name) by convention; typed as bare
`dict` for the same Komer-compatibility reason `permitted_issuers` uses bare `dict`.

A helper method on `EcosystemBaser`:

```python
def permitted_issuers_for_role(
    self, ecosystem_name: str, schema_said: str,
) -> str | None:
    """Return the role_name that confers issuer qualification for
    schema_said, or None if no credential-based rule is configured."""
    rec = self.get_ecosystem(ecosystem_name)
    if rec is None:
        return None
    return (rec.issuer_qualification_rules or {}).get(schema_said)
```

Callers combine both fields: a permitted issuer is either in the explicit AID list
OR qualifies under the role rule. The explicit list remains as a legacy/override path.

---

### 4.3 Goal 3: Multi-Tier Delegation

**What's missing:** No schema-to-schema edge structure in `EcosystemRecord`. No
distinction between "authorization credential" schemas (delegation instruments like
OOR AUTH) and "role credential" schemas (end-user role credentials like OOR).

**Vocabulary:** vLEI research §4.1–4.3 (I2I chain-of-authority, delegation via ACDC
edges, AUTH credential pattern). Archaeology §2.5 `EdgeDef(operator="I2I"|"DI2I")`.

**Two new fields needed on `EcosystemRecord`:**

```python
schema_roles: dict = field(default_factory=dict)
"""schema_said -> schema_role_label. Labels a schema's function
in the ecosystem: 'credential' | 'authorization' | 'registry_anchor'.

- 'credential': an end-user role credential (OOR, ECR, ProducerLicense).
- 'authorization': a delegation instrument (OOR AUTH, ECR AUTH). The
  issuer of a downstream credential must hold one of these.
- 'registry_anchor': a root-of-trust schema (not commonly issued but
  anchors the chain).

Convention overlay (vLEI §4.3, Primitive 5).
Empty dict = no role labels configured; all schemas treated as 'credential'."""

chain_depth_hints: dict = field(default_factory=dict)
"""schema_said -> int. Optional annotation of the maximum valid chain
depth from this schema to a root-of-trust schema. Used by the graph
view to assign Sugiyama layers correctly when edge structure is
ambiguous. Convention overlay; not authoritative."""
```

**The deeper structural gap:** schema-to-schema edge structure is derivable from
`ACDCSchemaInspection.edge_requirements` at render time, but is not stored in
`EcosystemRecord`. For the graph view this is currently computed live (the graph
reads the inspector for each schema). For a richer model — where the EGF explicitly
defines which schemas participate in a delegation chain — a new
`SchemaDescriptorRecord` (see §4.4) is the right home.

---

### 4.4 Goal 4: General EGF-Style Modeling

**What's missing:** The three primitives from the vLEI research that have no
representation at all: schema registry with human metadata, subscription/policy
rules for revocation cascade, and governance document references.

**Vocabulary:** vLEI Primitive 3 (EGF schema registry), archaeology §2.13
`SubscriptionDef`, §2.14 `PolicyDef`.

**New dataclass: `SchemaDescriptorRecord`**

```python
@dataclass
class SchemaDescriptorRecord:
    """Per-ecosystem, per-schema metadata overlay.

    The ACDC spec's EGF schema registry concept (spec §3.6): a mapping
    from schema SAID to human-readable name, description, version, and
    lifecycle state. The schema itself is content-addressed (SAID is
    canonical); this record adds the governance layer on top.

    Keyed by (ecosystem_name, schema_said).
    """
    ecosystem_name: str = ""
    schema_said: str = ""
    canonical_name: str = ""
    """Ecosystem-local human name, e.g. 'Qualified vLEI Issuer Credential'."""
    short_name: str = ""
    """Short/code name, e.g. 'QVI'."""
    version_label: str = ""
    """EGF-assigned version string, independent of the schema's own version field."""
    status: str = "active"
    """'active' | 'deprecated' | 'retired'. When 'retired', successor_said
    should point to the replacement."""
    successor_said: str = ""
    """Schema SAID of the replacement if status == 'retired'."""
    schema_role: str = "credential"
    """'credential' | 'authorization' | 'registry_anchor'. See schema_roles
    on EcosystemRecord."""
    notes: str = ""
```

**New `EcosystemBaser` Komer:** `sdesc.` subkey, keyed by
`(ecosystem_name, schema_said)`.

**New dataclass: `SubscriptionRecord`** (maps to archaeology `SubscriptionDef`)

```python
@dataclass
class SubscriptionRecord:
    """An inbound subscription to lifecycle events for a given schema SAID.

    Subscribes by schema SAID, not by issuer AID — the KERI-native
    design that allows a carrier to subscribe to ProducerLicense events
    regardless of which DOI issued them.

    The ACDC spec explicitly delegates revocation propagation to the EGF
    (spec §1112). This record captures that EGF decision.

    Convention overlay. Archaeology §2.13 SubscriptionDef.
    """
    ecosystem_name: str = ""
    subscription_id: str = ""      # unique within ecosystem
    schema_said: str = ""
    """Subscribe to lifecycle events for credentials of this schema."""
    reaction_policy_id: str = ""
    """PolicyRecord.policy_id to invoke when an event arrives."""
    filter_expr: str = ""
    """Optional free-text filter predicate (documentation-grade, not executable)."""
```

**New dataclass: `PolicyRecord`** (maps to archaeology `PolicyDef`)

```python
@dataclass
class PolicyRecord:
    """An automated reaction policy.

    When a subscribed event matching `trigger_event_kind` arrives,
    the wallet invokes `reaction_description`. For the current stage
    this is documentation-grade; a future ApplicationDoer would execute it.

    Convention overlay. Archaeology §2.14 PolicyDef.
    """
    ecosystem_name: str = ""
    policy_id: str = ""
    trigger_event_kind: str = ""
    """Free-form event kind string, e.g. 'credential_revoked'."""
    trigger_schema_said: str = ""
    """The schema SAID of the credential whose lifecycle event triggers this."""
    reaction_description: str = ""
    """Human-readable description of the reaction (documentation only for now)."""
    timeout: str = ""
    compensation_description: str = ""
```

**EGF metadata fields on `EcosystemRecord`:**

```python
governance_authority: str = ""
"""Name or AID of the organization responsible for this EGF."""
egf_document_said: str = ""
"""Content-addressed SAID of the authoritative EGF document, if available."""
egf_document_url: str = ""
"""URL of the EGF document (supplementary; SAID is authoritative)."""
effective_date: str = ""
"""ISO8601 date this EGF became effective."""
egf_version: str = ""
"""Version string for the EGF itself (e.g. '4.0')."""
```

---

## 5. Migration Concerns

### 5.1 How Komer deserializes records

`koming.Komer` serializes records to JSON via `dataclasses.asdict()` and
deserializes by calling the dataclass constructor with keyword args parsed from
the stored JSON. The current behavior on deserialization: **unknown fields in the
stored JSON are silently ignored; missing fields raise `TypeError` because the
dataclass constructor gets no value for a required positional argument.**

Since all fields in `EcosystemRecord` have defaults, the critical risk is
the **opposite direction**: if a new field is added without a default, any
pre-existing stored record will fail to deserialize.

The git log shows no migration-related commits — confirming the developer
has not shipped any migration tooling and considers it a cost to avoid.

### 5.2 The safe discipline: default everything, never rename

**Rule 1: Every new field on an existing dataclass MUST have a default.**

```python
# Safe — existing records without this field deserialize to default
issuer_qualification_rules: dict = field(default_factory=dict)

# UNSAFE — existing records fail to deserialize
issuer_qualification_rules: dict   # no default; KeyError on old records
```

**Rule 2: Never rename a field.** Renaming is a breaking schema change in both
directions. If `permitted_issuers` must be renamed `issuer_eid_map`, the migration
path is: add the new field with a default, write a one-time migration helper (not a
Komer hook — a function called once at vault open time), copy the old field to the
new one, clear the old one in a follow-up commit once all stored records have been
migrated.

**Rule 3: Never change a field's type non-additively.** `permitted_issuers: dict`
is typed as bare `dict` intentionally — this gives the deserializer maximum
flexibility. Changing it to `dict[str, list[str | RoleRef]]` where `RoleRef` is a
new dataclass would break old records that stored plain strings. The safe approach:
keep `permitted_issuers` as the legacy `dict[str, list[str]]` field and add
`issuer_qualification_rules` as a new `dict[str, str]` field alongside it.

**Rule 4: Consider adding a `schema_version` integer to each record.**

```python
@dataclass
class EcosystemRecord:
    # ... existing fields ...
    _schema_version: int = 1
    """Internal version tag. Increment when the record shape changes.
    NOT the EGF version; this is the wallet's internal schema version for
    migration tooling."""
```

This is the lightest possible migration hook: a `_schema_version` field that lets a
future migration function detect "this record needs upgrading" in O(1) rather than
inferring from field presence. Add it now (default=1, invisible to users) rather than
retrofitting it when the first real migration is needed.

---

## 6. What's Quietly Already There

Several parts of the current model could support the new goals with minimal change:

### 6.1 `permitted_issuers: dict` is close to a role reference

The field is already `dict[str, list[str]]` (schema_said → AID list). Generalizing
its values to `list[str | dict]` — where a `dict` value is a role reference
`{"role": "qvi"}` instead of a bare AID string — would be a non-breaking extension
using bare `dict` serialization (old records that only have AID strings continue to
work; new records can mix AIDs and role refs). The existing CRUD methods
(`set_permitted_issuers`, `add_permitted_issuer`, `remove_permitted_issuer`) would
need to be generalized but the storage key stays the same.

This is the smallest non-breaking path to credential-based qualification without
introducing `issuer_qualification_rules` as a separate field.

### 6.2 `_MembershipRecord` can absorb role membership

The existing `ambr.` (AID membership) Komer already maps `aid → list[ecosystem_names]`.
The same shape can be extended as a **role membership reverse index** keyed by
`(ecosystem_name, aid)` → `list[role_names]` in a new `rmbr.` subkey, using the
same `_MembershipRecord` dataclass. No new schema; the existing reverse-index
maintenance pattern in `_add_membership`/`_remove_membership` is reusable as-is.

### 6.3 `DiscoveryEvent.payload: dict` is already schema-free

New event kinds (e.g., `'role_qualified'`, `'credential_revoked_cascade'`) can be
added without any dataclass change — just new string `kind` values and agreed payload
shapes. This is intentional extensibility in the current design.

### 6.4 `AnnotationRecord.kind: AnnotationKind` is an `str, Enum`

Because `AnnotationKind` is `class AnnotationKind(str, Enum)`, adding a new member
`ROLE = "role"` is non-breaking for existing stored records (the stored string
`"role"` will deserialize correctly to the new enum value once added). Existing
records with `kind = "schema"`, `"aid"`, etc. are unaffected.

### 6.5 `EcosystemBaser.reopen` already patterns for new Komers

Every sub-DB is initialized in `reopen()` as `None` in `__init__` and then
assigned in `reopen()`. Adding a new Komer is three lines:

```python
def __init__(self, ...):
    # ...
    self.roles = None        # new
    self.schema_descs = None  # new

def reopen(self, **kwa):
    # ...
    self.roles = koming.Komer(db=self, subkey='rle.', schema=RoleRecord)
    self.schema_descs = koming.Komer(db=self, subkey='sdesc.', schema=SchemaDescriptorRecord)
```

The LMDBer base class creates the sub-DB lazily; no schema migration is triggered by
adding a new subkey to an existing LMDB file.

### 6.6 `source_url: str` is underused

The `source_url` field was designed for OOBI or file URLs, but is never read by any
current UI code (it's stored but not rendered). This field could be repurposed or
extended to hold the EGF governance document URL, with `egf_document_said` as a
companion for content-addressable references. The field already exists; no new storage
is needed for the URL half.

---

## 7. Summary: Priority Ordering of Data-Model Additions

By which addition unlocks the most downstream work:

| Priority | Addition | Unlocks |
|---|---|---|
| 1 | `RoleRecord` dataclass + `rle.` Komer | Goals 1, 2, 3 all depend on this. It is the primitive that makes all three derivable. |
| 2 | `issuer_qualification_rules: dict` on `EcosystemRecord` | Goal 2 (credential-based qualification without full role machinery) — smallest non-breaking path |
| 3 | `root_aids: list[str]` on `EcosystemRecord` | Enables chain validation anchoring (Goal 3) |
| 4 | `SchemaDescriptorRecord` + `sdesc.` Komer | Goal 4 (schema registry, version, retirement, role labels) |
| 5 | `schema_roles: dict` on `EcosystemRecord` | Goal 3 (AUTH vs credential schema distinction) |
| 6 | `SubscriptionRecord` + `PolicyRecord` + `sub.`/`pol.` Komers | Goal 4 (revocation cascade, reactive EGF modeling) |
| 7 | EGF metadata fields on `EcosystemRecord` | Goal 4 (governance document, authority, version) |
| 8 | `_schema_version: int` on all record dataclasses | Migration safety; should be added early while the record count is low |

---

## Appendix: Cross-Reference Table

| Goal | vLEI Primitive | Archaeology Primitive | Closest current hook | New model object |
|---|---|---|---|---|
| AID role categories | Primitive 4 (§4) | `AuthorizationDef(principal="holder_of(...)")` | `issuer_aids: list[str]` (flat list only) | `RoleRecord` |
| Credential-based qualification | §3.1–3.4 | `AuthorizationDef.credential_pattern` | `permitted_issuers` AID list | `issuer_qualification_rules` field + `RoleRecord.qualification_schema_said` |
| Multi-tier delegation | §4.1–4.3 | `EdgeDef(operator="I2I"/"DI2I")` | `ACDCSchemaInspection.edge_requirements` (derived, not stored) | `schema_roles` dict + `SchemaDescriptorRecord.schema_role` |
| EGF schema registry | Primitive 3 (§5, Primitive 3) | `CredentialDef.schema_path` + SAIDs | `schema_saids: list[str]` (opaque strings) | `SchemaDescriptorRecord` |
| Revocation cascade | §4.3 + spec §1112 | `SubscriptionDef` + `PolicyDef` | None | `SubscriptionRecord` + `PolicyRecord` |
| Root-of-trust anchor | §5, Primitive 4 + §6 (gap 6) | n/a (issuer AID resolved at install) | None | `root_aids: list[str]` on `EcosystemRecord` |
| Migration safety | n/a | n/a | No version tag | `_schema_version: int` on all records |
