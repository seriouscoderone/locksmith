# ACDC spec conformance notes

Notes on how this repo's manifests, schemas, and code map to the ACDC
specification. Compiled after a conformance audit that caught several
hallucinated facts in the early producer-licensing and
carrier-appointment slices. Citations point to lines in the canonical
spec at `kswg-acdc-specification/spec/spec-body.md`.

## Edge operators are about chain-of-authority, not revocation

ACDC unary edge operators (`spec-body.md:1099-1108`):

- **I2I** (default for targeted ACDCs) — the issuer of *this* credential
  must equal the issuee of the chained credential.
- **NI2I** — relaxes the I2I constraint; useful for chains that don't
  require the upstream-issuee/downstream-issuer relationship.
- **DI2I** — admits delegated AIDs.
- **NOT** — inverts validity.

Edge-group m-ary operators (`spec-body.md:1188-1196`): `AND` (default),
`OR`, `NAND`, `NOR`, `AVG`, `WAVG`. Apply at the edge-group level, not
on individual edges.

**Operators are not the mechanism for revocation propagation.** Whether
revocation of a chained credential invalidates a dependent credential
is **EGF-dependent** (Ecosystem Governance Framework — `spec-body.md:1112`).
Each ecosystem defines its own rules about timeliness, propagation, and
relying-party expectations.

In this repo we model revocation propagation via the manifest's
`SubscriptionDef` + `PolicyDef` pair. The carrier-appointment slice
illustrates the pattern: the carrier subscribes to `ProducerLicense`
lifecycle events and reacts to revocations with a
`SuspendDependentAppointments` policy. The schema's edge to
`ProducerLicense` uses the default I2I operator and does not encode
any revocation semantics.

(Earlier drafts of carrier-appointment used a fabricated
`MUST_NOT_REVOKED` operator. That has been removed.)

## Top-level field set

ACDC top-level field order (`spec-body.md:32`): `[v, t, d, u, i, rd, s,
a, A, e, r]`. Required-set (`spec-body.md:36`): `[v, d, i, s]`.

Our schemas mark `[v, d, i, ri, s, a]` (and for `CarrierAppointment`,
also `e`) as required. This is **stricter than the spec** — `a` and
`ri` aren't required at the ACDC level, but they are domain-required
for our credential types (a `ProducerLicense` without an attribute
block is meaningless). Domain-strictness is fine; spec-strictness in
the other direction would be wrong.

Notable fields we don't currently surface:

- `t` — message type, distinguishes ACDC variants. Not yet meaningful
  for our slices but spec-conformant authoring should declare it.
- `u` — UUID/nonce, used in selective-disclosure contexts.
- `A` — selectively-disclosable aggregate section. Distinct from `a`.

These can be added when a slice actually needs them.

## `ri` vs `rd` for the registry SAID field

Latest spec (`spec-body.md:83`, `:1975`, `:2017`) names the top-level
registry-SAID field **`rd`**. Our schemas use **`ri`**. Reason: keripy
1.3.4 still emits and accepts `ri` as of this writing; switching to
`rd` ahead of keripy would break issuance. The field will migrate when
keripy follows.

## Edge-internal field set

Spec edge fields (`spec-body.md:1140-1149`): `[d, u, n, s, o, w]` with
only `n` (node SAID) required. We currently declare `[n, s]` as
required and lock `s` via JSON Schema `const` to the chained
credential's schema SAID. We don't declare `u` (blinding nonce) or
`w` (weight, for WAVG-class group operators) — out of scope for slice
2 but additive when needed. We removed `o` from the schema entirely;
when omitted, the default I2I operator applies.

## Registry / TEL structural model

A registry is a TEL anchored to the issuer's KEL via a `vcp` (registry
inception) event. ACDC issuance and revocation events for credentials
of that registry's purpose are appended to **the same TEL** — there is
not a separate nested TEL per credential. There is per-credential
transaction state within the registry's TEL, but the data structure is
one log per registry, not one log per credential.

(Earlier conversational explanations in this repo's history described
"a VC State TEL nested under each registry per credential." That was
misleading — corrected here.)

## Process discipline

Going forward, before any new ACDC schema or manifest claim:

1. **Consult the spec.** Source of truth is
   `kswg-acdc-specification/spec/spec-body.md` (or the
   keri:chat skill, which returns spec-grounded answers with citations).
2. **Use the `keri:acdc` skill** when working on ACDC code. It exists
   to load the spec primitives into context.
3. **Don't propagate sketch vocabulary as if normative.** NORTH-STAR
   and similar design documents propose primitives that may resemble
   spec ones but aren't authoritative.
4. **Validate non-trivial claims via `keri:chat`** before committing
   them to code or to user-facing explanation.

## What this repo got right (for symmetry)

- Compact-vs-full duality of ACDC sections via JSON Schema `oneOf` —
  correct mechanism.
- Locking the schema SAID of a chained credential via JSON Schema
  `const` on the edge's `s` field — valid and useful constraint.
- Schemas as content-addressable artifacts: any byte change yields a
  new identity. The recursive saidifier in
  `scripts/saidify_acdc_schema.py` honors this.
- Subscription + policy as the mechanism for cross-slice reaction to
  events (e.g., carrier suspending appointments on license
  revocation) — KERI-native, no central process manager.
