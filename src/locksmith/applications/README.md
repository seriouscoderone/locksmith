# Applications

KERI-native applications declared as loadable manifests, organized as
**templates** (industry archetypes) and **instances** (specific
deployments). The split makes cross-organization composability concrete:
multiple instances of the same template share schema SAIDs and therefore
interoperate without explicit integration work.

## Layout

```
applications/
├── types.py                 # the manifest format (Application, CredentialDef, ...)
├── templates/               # industry archetypes — exemplars, not factories
│   └── insurance_regulation/
│       ├── schemas/         # saidified ACDC schemas — content-addressed, shared
│       ├── doi_role.py      # exemplar Application for the DOI role
│       └── carrier_role.py  # exemplar Application for the Carrier role
└── instances/               # concrete deployments
    ├── usurance_proxy_doi_ca/   # DOI role → Usurance, California
    │   └── manifest.py
    └── acme_insurance_ca/       # Carrier role → Acme Insurance, California
        └── manifest.py
```

## How templates and instances relate

A **template** captures the *recurring shape* of an application across
deployments: the schemas, the registries, the commands, the events, the
projections — generic prose, no specific organization named.

An **instance** is a *full copy* of a template's exemplar Application
value, customized for one specific deployment: organization name in
prose, jurisdiction, AID alias hint, proxy disclosure if applicable.
Instances reference the template's schemas via `schema_path` because
schemas are content-addressed — same SAID across all instances, which
is the whole point of shared schemas.

Templates are **exemplars, not factories.** No `make_application(state,
issuer)` parameterized constructors. The manifest is plain Python data;
divergences between deployments stay readable at the source level
because they're literal text differences, not runtime parameters.

## Why content-addressed schemas matter

Two instances of the same template (e.g., a hypothetical Texas DOI proxy
and the existing California Usurance proxy) issue against the *same*
`ProducerLicense` schema SAID. A relying party verifying a license has
the schema once; the issuer's AID distinguishes whose ledger the license
lives in. Cross-state interop emerges from byte-identical schemas, not
from anyone explicitly integrating.

## Adding a new template

1. Pick an industry vertical (sports organization, municipality, supply
   chain, healthcare credentialing, etc.).
2. Author the schemas under `templates/<vertical>/schemas/`. Saidify with
   `scripts/saidify_acdc_schema.py`.
3. Define one Python module per role under `templates/<vertical>/`,
   each exporting an Application value with generic prose.
4. Add a per-template README describing the role chain and any cross-
   role dependencies (edges, subscriptions, policies).

## Adding a new instance

1. Pick a template and a role within it.
2. Create `instances/<deployment_name>/manifest.py` as a full copy of
   the template's exemplar Application, with deployment-specific prose.
3. Set `ISSUER_ALIAS` to the AID alias the deployment uses.
4. If the deployment is a proxy (modeling a real-world entity that
   doesn't yet have a KERI presence), add explicit proxy disclosure to
   the credential rule prose and cite the migration plan doc.

## Note on runtime use

Today nothing in the wallet loads these manifests at runtime — the
plugins that consumed them earlier were retired (see
`refactor(applications): retire slice plugins, keep manifests as data`).
The manifests exist as data artifacts: a future generic ManifestPlugin
or a Skill emitting new instances both consume the same shape.
