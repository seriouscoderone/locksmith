# insurance_regulation template

Models the basic chain of authority in U.S. insurance regulation:

```
Department of Insurance (state regulator)
  └── issues ProducerLicense
                            └── chained from ──┐
                                                ▼
Insurance Carrier (e.g., Acme Insurance Co.)
  └── issues CarrierAppointment
                                  └── subscribes to ProducerLicense lifecycle events
                                  └── reacts to revocation via SuspendDependentAppointments policy
```

## Roles

### `doi_role.py` — Department of Insurance

A state DOI (or proxy) issues `ProducerLicense` credentials with
line-of-authority designations. This is the foundational credential —
nothing downstream (carrier appointments, policy binding) exists
without it.

### `carrier_role.py` — Insurance Carrier

A carrier issues `CarrierAppointment` credentials authorizing producers
to write the carrier's product lines. Each appointment chains via an
ACDC edge to the producer's `ProducerLicense`.

## Schemas

Saidified with `scripts/saidify_acdc_schema.py`. SAIDs:

- **ProducerLicense** — `ECmEfS_FcGeVLduy-ym1qDx3usSL9J0wwfOlY8kTBg80`
- **CarrierAppointment** — `ELSeXqzFfDo0gn5Lhat_aj5c8Ohe49oU_DgNT3GnlM3r`

Both are exported as constants from this package's `__init__.py` for
cross-template reference.

## Cross-role wiring

The `CarrierAppointment` schema's edge declaration (`e.producerLicense.s`)
is locked to `PRODUCER_LICENSE_SCHEMA_SAID` via JSON Schema `const`. So
issuance of `CarrierAppointment` is structurally bound to the specific
ProducerLicense schema SAID — schema rotation in `doi_role.py` would
require coordinated re-saidification of `carrier_role.py`.

The `carrier_role.py` manifest also declares a `SubscriptionDef` to
ProducerLicense lifecycle events and a `PolicyDef`
(`SuspendDependentAppointments`) for revocation propagation. ACDC has no
built-in operator for revocation propagation (spec-body.md:1112 — EGF-
dependent), so this subscription + policy pair is the explicit mechanism
this template uses.

## Existing instances

- `instances/usurance_proxy_doi_ca/` — Usurance, California proxy DOI
- `instances/acme_insurance_ca/` — Acme Insurance Co., California carrier

## How to deploy a new instance

1. Create `instances/<your_org>/manifest.py` as a full copy of the
   appropriate role's exemplar Application.
2. Set `ISSUER_ALIAS` at the top of the file.
3. Customize the description and rule prose to mention your organization
   and jurisdiction explicitly.
4. If your deployment is a proxy (modeling a real-world body that
   doesn't yet have KERI presence), add proxy disclosure to the rule
   prose and cite the migration-plan doc.
5. Schema paths in your `CredentialDef.schema_path` should point back to
   `../../templates/insurance_regulation/schemas/<file>.json` — sharing
   schema bytes (and therefore SAIDs) across all instances of this
   template is the entire point.
