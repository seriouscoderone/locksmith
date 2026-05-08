# Applications Archaeology: Deleted `src/locksmith/applications/` Directory

**Date:** 2026-05-08  
**Source:** `git show be6b315:src/locksmith/applications/...` (commit `be6b315`, branch `sidebar-ux`)  
**Purpose:** Extract data-model patterns from the deleted `applications/` directory and
assess which primitives the current `ecosystem_viewer` plugin's `EcosystemRecord` is missing.

---

## 1. What the Deleted Code Was

The `src/locksmith/applications/` directory was a **declarative manifest format** for
KERI-native enterprise applications — thin, role-specific slices of a real-world
credentialing workflow described entirely as Python data. Each manifest was a single
`Application` value enumerating the registries it owns, the credentials it issues, the
commands that trigger issuance, the events those commands produce, and the policies that
react to upstream lifecycle events from other applications.

The design was consciously *pre-runtime*: as of commit `be6b315` (the most mature state)
nothing in the wallet loaded these manifests at runtime. The plugins that originally
consumed them (per-slice `ProducerLicensingPlugin` and `CarrierAppointmentPlugin`) had
been retired in `ce9d09f` because they were 95 % boilerplate. The manifests were kept
as pure data artifacts — "a Python value plus a saidified JSON schema; anyone reading
them gets the same shape" — with an explicit note that a future generic `ManifestPlugin`
(Phase 3) would consume them directly.

The final commit also introduced a **templates / instances** split. A *template* captures
the recurring shape of a deployment (schemas, registries, commands, projections — with
generic prose naming "the named state", "the issuing authority"). An *instance* is a
full copy customized for one specific organization: prose names the org explicitly, an
`ISSUER_ALIAS` constant identifies the AID alias, and `schema_path` links back to the
template's canonical schema files. Because instances share the template's schema bytes,
they automatically share schema SAIDs — cross-org interoperability emerges from
content-addressed schemas, not from explicit integration work.

---

## 2. Primitive Catalog

All primitives live in `src/locksmith/applications/types.py` at commit `be6b315`.

### 2.1 `Application`

```python
@dataclass(frozen=True)
class Application:
    id: str
    name: str
    description: str
    registries: list[RegistryDef] = field(default_factory=list)
    credentials: list[CredentialDef] = field(default_factory=list)
    commands: list[CommandDef] = field(default_factory=list)
    events: list[EventDef] = field(default_factory=list)
    projections: list[ProjectionDef] = field(default_factory=list)
    subscriptions: list[SubscriptionDef] = field(default_factory=list)
    policies: list[PolicyDef] = field(default_factory=list)
```

**Meaning:** The top-level envelope for one role's slice of a credentialing workflow.
Note that the issuer AID is *deliberately absent* — it is resolved at install time
from the AID whose KEL the manifest hangs off of, so the same manifest data can be
issued by different organizations (e.g., California DOI, Texas DOI) without changing
the content.

**Current analog:** `EcosystemRecord` has `name`, `description`, `schema_saids`, and
`issuer_aids` but nothing equivalent to commands, events, projections, subscriptions,
or policies. It is a grouping record, not a workflow descriptor.

---

### 2.2 `RegistryDef`

```python
@dataclass(frozen=True)
class RegistryDef:
    id: str
    name: str
```

**Meaning:** A TEL (Transaction Event Log) registry the application owns. Anchored in
the issuer AID's KEL via a SEAL event when created. In practice, one registry per
credential type is the pattern used here (though the spec allows many credentials per
registry).

**Problem it solves:** Makes explicit which registries the application controls and
their human-readable names, so a generic UI can render "Carrier Appointment Registry"
rather than a raw SAID.

**Current analog:** `EcosystemRecord` has no registry concept at all. The wallet's
`Credentials → Schemas` UI creates registries implicitly.

---

### 2.3 `CredentialDef`

```python
@dataclass(frozen=True)
class CredentialDef:
    id: str
    registry_id: str
    schema_path: str          # filesystem path to saidified JSON schema
    attributes: dict[str, AttributeDef] = field(default_factory=dict)
    edges: dict[str, EdgeDef] = field(default_factory=dict)
    rule: str = ""
```

**Meaning:** One ACDC credential type the application issues. `schema_path` is the
content-addressed source of truth; the SAID is derived from the schema bytes. `rule`
is the machine/human-readable governance text embedded in the issued credential's `r`
block. `edges` names other credentials this credential depends on (cross-application
credential chaining).

**Problem it solves:** Connects the human-readable attributes and rules to a specific
saidified schema file, making it impossible to issue without the correct schema SAID.

**Current analog:** `EcosystemRecord.schema_saids` stores SAIDs as bare strings with no
attribute, edge, or rule information. There is no machine-readable description of what
each schema means or how it relates to others.

---

### 2.4 `AttributeDef`

```python
@dataclass(frozen=True)
class AttributeDef:
    type: str
    description: str = ""
    enum: list[str] | None = None
    min_items: int | None = None
    min_length: int | None = None
    max_length: int | None = None
```

**Meaning:** Metadata about one field in a credential's `a` block — type, human
description, valid enum values, length constraints. Mirrors what JSON Schema would
say about the field, but as Python data accessible without parsing a raw schema file.

**Problem it solves:** Lets a generic UI render a form for issuing a credential without
having to understand raw JSON Schema syntax.

**Current analog:** None. The ecosystem viewer has no per-attribute metadata.

---

### 2.5 `EdgeDef`

```python
@dataclass(frozen=True)
class EdgeDef:
    target_credential_id: str
    cardinality: Literal["one", "many"] = "one"
    operator: Literal["I2I", "NI2I", "DI2I", "NOT"] | None = None
```

**Meaning:** An ACDC edge linking one credential to another, with the ACDC spec's
unary operator (`I2I` = issuer of this credential must be the issuee of the chained
credential; `NI2I` = no constraint; `DI2I` = issuer must be a delegated AID of the
issuee; `NOT` = negation). The `operator` field was corrected in `7925a27` after an
earlier iteration incorrectly used a fabricated `MUST_NOT_REVOKED` value that has
no basis in the spec.

**Problem it solves:** Makes the credential trust chain explicit and machine-readable.
Combined with `schema_path` in `CredentialDef`, an edge is a type-safe commitment:
the edge's `target_credential_id` resolves to a `CredentialDef` whose schema SAID
locks the chain at the bytes level (via JSON Schema `const` in the edge sub-block).

**Current analog:** None. `EcosystemRecord` stores bare schema SAIDs with no edge or
chain-of-authority information.

**Important note:** `EdgeDef.operator` governs the issuer/issuee relationship between
credentials. It does **not** govern revocation propagation — that is EGF-dependent
(ACDC spec §1112) and is handled by `SubscriptionDef` + `PolicyDef` (see below).
This distinction was clarified in `7925a27`.

---

### 2.6 `CommandDef`

```python
@dataclass(frozen=True)
class CommandDef:
    id: str
    payload: dict[str, str]          # field name -> type hint string
    authorization: AuthorizationDef
    preconditions: PreconditionsDef = field(default_factory=PreconditionsDef)
    idempotency_key: str | None = None
    produces: list[str] = field(default_factory=list)  # EventDef ids
    issues: str | None = None         # CredentialDef id to mint
    grants_to: str | None = None      # payload field name -> the IPEX grant target AID
```

**Meaning:** A command an authorized actor can submit to the application. `authorization`
says who is allowed to submit it. `preconditions` declares the state and temporal guards
that must hold before the command succeeds. `produces` names the events that will be
appended on success. `issues` names the credential that will be minted. `grants_to`
names the payload field whose AID value will receive the IPEX grant.

**Problem it solves:** Describes issuance workflows declaratively, without hard-coding
UI flows. A generic `ManifestPlugin` can render "Issue Credential" buttons by reading
`CommandDef.payload` and `CommandDef.authorization` without knowing anything specific
about this credential type.

**Current analog:** None in `EcosystemRecord`. The wallet's `IssueCredentialDialog` is
hard-coded for the general case.

---

### 2.7 `AuthorizationDef`

```python
@dataclass(frozen=True)
class AuthorizationDef:
    principal: str
    credential_pattern: str | None = None
```

**Meaning:** Who is authorized to submit a command. `principal` is a predicate string;
the two attested patterns are `"control_of(issuer_aid)"` (AID control gate) and
`"holder_of(<credential_id>)"` (credential-based gate). `credential_pattern` declares
an inbound credential that must be presented alongside the command.

**Problem it solves:** Makes authorization rules machine-readable. In the insurance
template, every `IssueProducerLicense` and `AppointProducer` command requires
`control_of(issuer_aid)`, but the pattern explicitly accommodates credential-based
authorization for future commands (e.g., a producer self-service renewal that requires
presenting their existing license).

**Current analog:** `EcosystemRecord.permitted_issuers` is a `dict[schema_said, list[AID]]`
that expresses "these specific AIDs are allowed issuers." That is an AID whitelist
approach rather than a credential-based qualification approach. The vLEI research
(§2.1) identifies AID whitelisting as explicitly weaker than credential-based qualification.

---

### 2.8 `PreconditionsDef`

```python
@dataclass(frozen=True)
class PreconditionsDef:
    state: list[str] = field(default_factory=list)
    temporal: list[str] = field(default_factory=list)
```

**Meaning:** Guard conditions a command must satisfy before execution. `state`
predicates check registry / credential state (e.g., "no active license with this
licenseNumber exists"). `temporal` predicates check time relationships (e.g.,
`"expiresDate > issuedDate"`, `"issuedDate <= now"`). Both are free-text strings
at this stage; the module docstring acknowledges tightening into a UEL (Universal
Expression Language) as future work.

**Problem it solves:** Prevents duplicate issuance, temporal violations, and
state inconsistencies without baking those rules into plugin code.

**Current analog:** None.

---

### 2.9 `CommitsTo`

```python
@dataclass(frozen=True)
class CommitsTo:
    prior_event: bool = True
    command: bool = True
    credential_presentation: bool = False
    credential_issued: str | None = None   # CredentialDef id
    registry_id: str | None = None
    custom: list[str] = field(default_factory=list)
```

**Meaning:** Declares what cryptographic commitments a TEL event carries. The most
important fields are `credential_issued` (names the `CredentialDef` whose SAID gets
committed into the event) and `registry_id` (names the TEL the event is appended to).

**Problem it solves:** Documents the provenance chain: given a TEL event, what issued
credential, command, and prior event does it commit to? This is the audit trail
backbone — a verifier can reconstruct the issuance from the TEL.

**Current analog:** None in the current plugin.

---

### 2.10 `EventDef`

```python
@dataclass(frozen=True)
class EventDef:
    id: str
    commits_to: CommitsTo
    payload_fields: list[str] = field(default_factory=list)
```

**Meaning:** A TEL event type that a command appends on success. `payload_fields`
names the subset of the command's payload that flows into the event record.

**Problem it solves:** Decouples the event schema from the command schema — a listener
watching the TEL only needs to know `EventDef.payload_fields`, not the full command
payload.

**Current analog:** None.

---

### 2.11 `GateDef`

```python
@dataclass(frozen=True)
class GateDef:
    principal: str | None = None
    credential_pattern: str | None = None
    public: bool = False
```

**Meaning:** Who can read a projection. Exactly one field is set: `principal` for AID
control, `credential_pattern` for credential-based read access, `public` for
unauthenticated access.

**Problem it solves:** Makes read-side authorization first-class in the manifest. In
the insurance template, `LicenseLookup` is `public=True` (anyone can verify a
producer's license), `LicensesIssuedByMe` is gated on `control_of(issuer_aid)` (DOI
only), and `MyLicense` is gated on `holder_of(ProducerLicense)`.

**Current analog:** None. The ecosystem viewer's current read model is fully open
(any loaded vault can see any ecosystem).

---

### 2.12 `ProjectionDef`

```python
@dataclass(frozen=True)
class ProjectionDef:
    id: str
    lens: Literal["issuer", "holder", "subscriber", "public"]
    gate: GateDef
    source: str             # free-text fold description
    shape: list[str] = field(default_factory=list)
    freshness: Literal["eager", "lazy"] = "eager"
    query_input: str | None = None
```

**Meaning:** A named read-side view over the application's TEL events. `lens`
declares the first-person framing: issuer-side tables show all credentials issued;
holder-side tables show the holder's own credentials; public views are anonymous
lookups. `gate` controls who can access this projection. `shape` names the fields
to render. `query_input` names a parameter for parameterized projections (e.g.,
lookup by `producerAID`).

**Problem it solves:** A generic `ManifestPlugin` can render multiple views of the
same application without knowing anything specific about the credential type. The
`lens` enum is the key: it tells the wallet's renderer which first-person framing
to apply.

**Current analog:** The ecosystem viewer's `graph_view.py` renders a static DAG of
schema relationships. There is no per-issuer / per-holder / public projection concept.

---

### 2.13 `SubscriptionDef`

```python
@dataclass(frozen=True)
class SubscriptionDef:
    id: str
    schemas: list[str]     # event schema SAIDs to subscribe to
    filter: str | None = None
    reaction: str | None = None   # CommandDef id to invoke
```

**Meaning:** An inbound subscription to lifecycle events from *other* applications.
Crucially, subscriptions are keyed by schema SAID, not by source AID — a KERI-native
design choice: the carrier subscribes to "all ProducerLicense lifecycle events" without
hard-coding which DOI issued them.

**Problem it solves:** Cross-application reactive workflows. The carrier appointment
application subscribes to ProducerLicense events so it can react to revocations. This
is the one mechanism for cross-role revocation propagation that the ACDC spec
explicitly leaves to the EGF (spec §1112).

**Current analog:** None. The ecosystem viewer has no reactive/subscription concept.

---

### 2.14 `PolicyDef`

```python
@dataclass(frozen=True)
class PolicyDef:
    id: str
    trigger_event_id: str
    reaction_command_id: str
    timeout: str | None = None
    compensation_command_id: str | None = None
```

**Meaning:** A within-application automated reaction to an inbound event. When
`trigger_event_id` fires (via a `SubscriptionDef` subscription), the application
automatically invokes `reaction_command_id`. `timeout` and `compensation_command_id`
sketch a saga/compensation pattern for failure cases (the format note says this is
future work).

**Problem it solves:** Makes revocation-cascade policies machine-readable without
relying on operator-defined CEP (complex event processing) rules. In the carrier
template, `SuspendDependentAppointments` fires `SuspendAppointment` when a subscribed
`ProducerLicenseRevoked` event arrives.

**Current analog:** None.

---

## 3. Composition Example: Acme Insurance CA Manifest

The following shows how the primitives compose to model the scenario
"Acme Insurance Co. issuing `CarrierAppointment` credentials chained to
`ProducerLicense` credentials issued by the Usurance California DOI proxy."

### Step 1 — DOI proxy issues `ProducerLicense` to a producer AID

The `usurance_proxy_doi_ca` instance declares:

```python
# One registry (TEL) anchored in usurance-proxy-doi-ca's KEL
RegistryDef(id="producer-license-registry", name="Producer License Registry")

# One credential type, content-addressed by schema SAID
CredentialDef(
    id="ProducerLicense",
    registry_id="producer-license-registry",
    schema_path="../../templates/insurance_regulation/schemas/producer_license.json",
    # schema SAID = ECmEfS_FcGeVLduy-ym1qDx3usSL9J0wwfOlY8kTBg80
    edges={},           # no upstream credential required
    rule="... explicit proxy disclosure ..."
)

# The only command that can mint it
CommandDef(
    id="IssueProducerLicense",
    authorization=AuthorizationDef(principal="control_of(issuer_aid)"),
    preconditions=PreconditionsDef(
        state=["no active license with this licenseNumber exists in registry"],
        temporal=["expiresDate > issuedDate", "issuedDate <= now"],
    ),
    idempotency_key="licenseNumber",
    issues="ProducerLicense",
    grants_to="producerAID",    # IPEX grant goes to the producer
)
```

On execution, `IssueProducerLicense` appends a `ProducerLicenseIssued` event to the
`producer-license-registry` TEL, commits to `credential_issued="ProducerLicense"`,
and IPEX-grants the credential to `producerAID`.

### Step 2 — Carrier appointment chains to the license via `EdgeDef`

The `acme_insurance_ca` instance declares:

```python
CredentialDef(
    id="CarrierAppointment",
    registry_id="carrier-appointment-registry",
    schema_path="../../templates/insurance_regulation/schemas/carrier_appointment.json",
    # schema SAID = ELSeXqzFfDo0gn5Lhat_aj5c8Ohe49oU_DgNT3GnlM3r
    edges={
        "producerLicense": EdgeDef(
            target_credential_id="ProducerLicense",
            cardinality="one",
            operator=None,      # defaults to I2I (spec §1099-1108)
        ),
    },
    rule="... appointment is cryptographically conditional on the license ..."
)
```

The `EdgeDef.target_credential_id="ProducerLicense"` resolves across application
boundaries: the carrier's manifest doesn't embed the DOI application, but the
schema's `e.producerLicense.s` field is hardcoded to
`ECmEfS_FcGeVLduy-ym1qDx3usSL9J0wwfOlY8kTBg80` (the ProducerLicense schema SAID).
This is the **schema-SAID-constrained edge** from the vLEI research (§5, Primitive 1):
a verifier confirming the `CarrierAppointment` must also confirm the chained
`ProducerLicense` matches that exact schema SAID.

The default `I2I` operator means: the issuer of `CarrierAppointment` (Acme's AID)
must be the issuee of `ProducerLicense`. Wait — that is the *template* check. In the
actual deployment, the `CarrierAppointment` is issued *to the producer*, and the edge
points to the producer's `ProducerLicense`. The operator applies to the chain: the
carrier (Acme) issues `CarrierAppointment`; the `producerLicense` edge has I2I
semantics meaning the issuee of the appointment is the issuee of the chained license.
The comment in the carrier manifest says `operator=None` deliberately to let the
ACDC spec's default apply; the comments note this was intentional after the
`7925a27` cleanup.

### Step 3 — Carrier subscribes to license lifecycle for revocation cascade

```python
SubscriptionDef(
    id="ProducerLicenseLifecycleFeed",
    schemas=["ECmEfS_FcGeVLduy-ym1qDx3usSL9J0wwfOlY8kTBg80"],
    # subscribes by schema SAID, not by usurance-proxy-doi-ca's AID
    reaction="SuspendDependentAppointments",
)

PolicyDef(
    id="SuspendDependentAppointments",
    trigger_event_id="ProducerLicenseRevoked",
    reaction_command_id="SuspendAppointment",
    timeout=None,
    compensation_command_id=None,
)
```

The `SubscriptionDef` fires on any `ProducerLicense` lifecycle event regardless of
which DOI issued it. When a `ProducerLicenseRevoked` event arrives, `PolicyDef`
automatically triggers `SuspendAppointment` — the manifest-level policy that the
ACDC spec explicitly delegates to the EGF (spec §1112).

This three-step composition shows how `RegistryDef`, `CredentialDef`, `EdgeDef`,
`CommandDef`, `SubscriptionDef`, and `PolicyDef` together express:

> "An issuer (carrier) may appoint producers who hold a valid license from any
> DOI instance sharing the same schema SAID, and will automatically react when that
> license is revoked."

No per-DOI integration, no AID whitelist — the shared schema SAID is the only coupling.

---

## 4. What Was Retired and Why

### 4.1 `ce9d09f`: Retire Slice Plugins

The first two applications were each implemented as full Locksmith plugins
(`ProducerLicensingPlugin`, `CarrierAppointmentPlugin`) with lifecycle hooks, page
widgets, and `pyproject.toml` entry-point registrations. Commit `ce9d09f` retired
these plugins for a clear reason stated in the commit body:

> "The producer-licensing and carrier-appointment plugins were 95% boilerplate
> (lifecycle hooks + a lens page that wrapped the existing IssueCredentialDialog).
> For the current stage of work — testing the manifest format and the substrate,
> not building production UX — the plugin scaffolding adds cost without value.
> The vanilla wallet's schema-add and credential-issue flows already exercise
> every primitive the plugin pages were exposing."

What was kept: `types.py` (the manifest format) and the `manifest.py` files for each
application (the data). What was deleted: the `{plugin,pages}.py` modules and the
`pyproject.toml` entry points. The commit explicitly frames the retained manifests as
"pure data artifacts: a Python value describing each application plus the saidified
ACDC schema it issues. Anyone reading them — a future generic ManifestPlugin (Phase 3),
a Skill emitting new applications, a test harness — gets the same shape."

The design move: separate *what the application is* (the manifest format, which is
permanent) from *how the wallet surfaces it* (plugin pages, which are premature at
slice-testing stage).

### 4.2 `be6b315`: Templates vs. Instances

The final commit (`be6b315`) observed that the first two manifests mixed deployment-
specific prose (organization name, jurisdiction, proxy disclosure) with shape that
recurs across deployments (schemas, registries, commands, projections). The templates/
instances split makes this layering explicit:

- **Templates** are exemplars, not factories. No `make_application(state, issuer)`
  parameterized constructor. The manifest is plain Python data; divergences between
  deployments are literal text differences.
- **Instances** are full copies, not references to their template. This prevents a
  template change from silently mutating deployed instances.
- **Schemas live only in the template** and are referenced by `schema_path` pointing
  back. Schema SAIDs are shared across all instances of the same template — that is
  the interoperability mechanism.

---

## 5. Which Primitives We Should Restore

The following five primitives would directly enable the ecosystem-viewer plugin's stated
goals of AID categories, credential-based qualification, and multi-tier delegation:

### 5.1 `EdgeDef` (+ schema-SAID cross-reference in `CredentialDef`)

**Why:** The current `EcosystemRecord` stores schema SAIDs as a flat list with no
relationship information. `EdgeDef` encodes the credential chain structure that is
the primary trust model in any ACDC EGF. The vLEI research (Primitive 1) identifies
the schema-SAID-constrained edge as the mechanism by which role qualification becomes
cryptographically self-describing.

**Restoration form:** Add an `edges: dict[str, EdgeDef]` field to a new
`SchemaDescriptor` record (or expand `EcosystemRecord` to include a separate
per-schema metadata map). This lets the graph view render actual trust chains instead
of a flat schema list.

### 5.2 `AuthorizationDef` (credential-based principal)

**Why:** `EcosystemRecord.permitted_issuers` is an AID whitelist — it requires an
operator to enumerate specific AIDs. The vLEI research (§2.1, §3.3) shows that
production EGFs avoid explicit AID lists because they create maintenance burden and
degrade when issuers rotate keys. `AuthorizationDef.principal = "holder_of(<schema_said>)"` 
expresses "any AID holding a valid credential of type X may issue credential Y" — the
credential-qualification pattern that is both more scalable and more ACDC-native.

**Restoration form:** Replace or supplement `permitted_issuers` with a
`qualification_rule` field that accepts the `holder_of(...)` predicate. Keep the
AID whitelist as a legacy fallback for ecosystems where explicit AID control is
genuinely required.

### 5.3 `SubscriptionDef`

**Why:** Cross-application reactive workflows (revocation cascade being the canonical
case) are not expressible in the current `EcosystemRecord`. `SubscriptionDef` is
KERI-native: it subscribes by schema SAID, not by issuer AID, which means a carrier
does not need to know which specific DOI issued a license — only that the license
matches the expected schema SAID. This maps directly to the vLEI research (§4.3,
"authorization credential as delegation primitive") and to the TEL-watching
infrastructure already in the wallet (`Watchmen`, `Adjudicator`).

**Restoration form:** Add `subscriptions: list[SubscriptionDef]` to `EcosystemRecord`
or to a new `ApplicationManifest` record that `EcosystemRecord` may optionally
reference. The subscription list drives the wallet's `SubscriptionDoer` (if/when
implemented).

### 5.4 `PolicyDef`

**Why:** Paired with `SubscriptionDef`, `PolicyDef` makes revocation-cascade rules
machine-readable at the manifest level rather than hard-coded in plugin logic. The
ACDC spec explicitly delegates revocation propagation to the EGF (spec §1112); a
`PolicyDef` is the wallet's first-class representation of that EGF decision. For the
ecosystem viewer specifically, rendering which applications subscribe to which schemas
and what they do on revocation is the key governance-visibility feature.

**Restoration form:** Add `policies: list[PolicyDef]` alongside `subscriptions`.

### 5.5 `ProjectionDef` (lens + gate)

**Why:** The ecosystem viewer currently renders a flat graph. `ProjectionDef.lens`
provides the first-person framing (`"issuer"`, `"holder"`, `"public"`) that tells the
wallet's renderer whether to show "credentials I issued" vs. "my credentials" vs. "a
public lookup." `GateDef` makes read-side authorization first-class: public credential
lookups (like `LicenseLookup` in the DOI template) are marked `public=True`, while
issuer dashboards are gated on `control_of(issuer_aid)`. This is the mechanism by
which the wallet can show the right information to the right participant without
hard-coded role checks.

**Restoration form:** Add `projections: list[ProjectionDef]` to the application
manifest. The graph view can use `lens` to decide which node perspective to highlight
when the active vault's AID matches an issuer or holder in the ecosystem.

---

## 6. Which Primitives We Should NOT Restore

### 6.1 Per-slice Plugin Classes (`ProducerLicensingPlugin`, `CarrierAppointmentPlugin`)

**Why not:** These are explicitly what `ce9d09f` retired. They were per-application
boilerplate wrapping generic `IssueCredentialDialog` calls. The correct design is one
generic `ManifestPlugin` that consumes any `Application` value. Restoring per-type
plugin classes would re-create the O(n) boilerplate problem.

### 6.2 `pyproject.toml` Entry Points for Per-Application Plugins

**Why not:** Restoring slice-level entry points would require `pip install -e .` for
every new application type. The manifest format's value is that new application
definitions don't require code deployment — they're data. A generic plugin reads any
conformant `Application` value.

### 6.3 `CommandDef` + `PreconditionsDef` in their current free-text form

**Why not yet:** `CommandDef.payload` is `dict[str, str]` (field name → type hint
string, e.g., `"linesOfAuthority": "array<string>"`). `PreconditionsDef.state` is
`list[str]` (plain English predicates, e.g., `"no active license with this licenseNumber
exists in registry"`). The module docstring acknowledges these need to be tightened
into a UEL (Universal Expression Language). Until that tightening happens, these fields
are documentation-grade prose, not machine-executable. Restoring them as-is would
suggest they are evaluable, which they are not.

Restore them only in a clearly-marked `description`-only capacity, with explicit
comments that state and temporal predicates are documentation only until a predicate
evaluator is wired up.

### 6.4 `CommitsTo` in isolation

**Why not yet:** `CommitsTo` describes what cryptographic commitments a TEL event
carries. This is correctly specified but is only useful when the wallet generates or
validates TEL events. The ecosystem viewer is a read-only display plugin (at the time
of this research); it has no event-generation path. Restoring `CommitsTo` +
`EventDef` makes sense when the wallet adds an `ApplicationDoer` that actually writes
to registries based on manifest commands.

---

## 7. Cross-Reference with vLEI Research

The vLEI research (`2026-05-08-vlei-ecosystem-patterns.md`) and the deleted
`applications/` directory converge on the same three structural insights:

| vLEI research concept | `applications/` equivalent | Current `EcosystemRecord` gap |
|---|---|---|
| Schema-SAID-constrained edge (§5, Primitive 1) | `EdgeDef.target_credential_id` + schema `const` in JSON | No edge concept at all |
| Role as "holder of valid credential of schema X" (§2.2) | `AuthorizationDef(principal="holder_of(...)") ` | AID whitelist (`permitted_issuers`), not credential-based |
| Revocation propagation is EGF-dependent (spec §1112) | `SubscriptionDef` + `PolicyDef` pair | No subscription or policy concept |
| Authorization credential as delegation primitive (§4.3) | `EdgeDef` chaining + `AuthorizationDef` | No delegation model |
| Schema SAID as stable qualification anchor (§3.4) | `schema_path` → derivable SAID, shared across instances | SAIDs stored but with no structural metadata |

The `applications/` manifest format was independently arriving at the same primitives
the vLEI documents as generic EGF patterns. The key difference: vLEI expresses these
as a governance document; the `applications/` format expressed them as Python data
structures that a wallet can load and render without a governance document parser.
