# Ecosystem Viewer

A wallet plugin for exploring ACDC schemas, issuer AIDs, and the
relationships among them — at the **domain level**, not the byte level.

## Why this exists

KERI is new. Real ecosystems mostly don't exist yet. The ones that will
exist (a state DOI, the NFL, a city's permitting office, a carrier's
appointment registry) need to be modelable, explorable, and composable
*before* they go live, so that designers and early adopters can:

1. Build proxy / example deployments that stand in for real organizations
   until those organizations bootstrap KERI presence.
2. Author and publish ACDC schemas, with edge dependencies among them
   that capture chain-of-authority structure (DOI → broker license →
   carrier appointment → policy quote, for example).
3. Discover and accumulate ecosystems over time as they encounter them
   — the wallet becomes a personal map of the KERI universe the user
   has touched.
4. Reason about ecosystems at the level of *meaning*, not bytes:
   "what credentials does this ecosystem issue, who issues them, what
   are their privacy properties, how do they chain?"

Existing tooling (keripy, the wallet's vanilla credential views)
operates at the byte/field level. That's correct for those layers — they
should be field-precise. But for *exploration* and *authoring*,
operating at the byte layer means re-deriving domain semantics on every
read, which is exactly where misunderstandings and bugs creep in.

This plugin closes that gap.

## What "ecosystem" means here

Importantly: **the ACDC spec does not define "ecosystem" as a primitive.**
It defines schemas (content-addressed by SAID), credentials (instances of
schemas, issued by AIDs), edges (chain-of-authority structure), and the
EGF (Ecosystem Governance Framework) — but the EGF is explicitly
per-ecosystem, defined out-of-band by the people running it.

So in this plugin, an "ecosystem" is a **user construct**: a named
grouping of schemas + issuer AIDs that the user (or a published
manifest) considers to be working together. It's not in the wire
protocol; it's a layer the wallet adds for the user's mental model.

Examples:

- *Insurance regulation, California (proxy era)*: schemas
  `ProducerLicense`, `CarrierAppointment`, `PolicyQuote`; issuer AIDs
  for proxy DOIs, real carriers, and producers as they participate.
- *NFL sports network*: schemas `CertifiedTrainer`, `ApprovedVendor`,
  `RegisteredEvent`; issuer AIDs for NFL HQ proxy and any local
  affiliates that adopt the same schemas.
- *Springfield MO municipality*: schemas `BusinessLicense`,
  `BuildingPermit`, `CommunityOrgRecognition`; issuer AID for the
  city's proxy office.

The same `CertifiedTrainer` schema (same SAID) might appear in multiple
ecosystems — say, NFL's and Pop Warner's. The schemas are
content-addressed and shared; what distinguishes ecosystems is *who's
issuing* and *how the user has chosen to group them*.

## Design rationale

### DB-first, not file-first

Schemas resolved via OOBI land in `vault.hby.db.schema`. Remote AIDs'
KELs land in `vault.hby.kevers` and contact metadata in `vault.org`.
Credentials in `vault.rgy.reger`. **The viewer reads from those
existing wallet stores** — there is no separate "schema templates as
files" concept. Files in this plugin are dev/example seed data only,
not the source of truth.

For ecosystem-level concepts the wallet doesn't already track —
groupings, annotations, discovery history — the plugin owns its own
LMDB store via an `EcosystemBaser` (planned). Same pattern as
`KFBaser` in the kerifoundation plugin: per-vault, namespaced, plugin-
specific concerns kept out of core wallet stores.

The promise: as the user resolves more OOBIs and annotates what they
find, the wallet's database accumulates a richer and richer map of the
KERI ecosystems they've encountered. The plugin is the lens over that
accumulating map.

### Domain layer, not byte layer

A separate module — `locksmith.acdc` — exposes ACDC primitives as
domain types (variants, disclosure tiers, edge operators, etc.) that
the viewer renders directly. See `src/locksmith/acdc/inspector.py` for
the read side and (eventually) `src/locksmith/acdc/builder.py` for the
authoring side.

Operating in domain terms — "this is a targeted private credential
with selective disclosure, chained to a producer license via I2I" —
is what makes the viewer *ecosystem-literate*, not just a JSON
renderer.

### Three layers of artifact

```
┌─────────────────────────────────────────────────────────────────────┐
│ ECOSYSTEM (user construct, plugin-DB)                                │
│   Named grouping: schemas[], issuer_aids[], notes, provenance        │
└──────────────────┬──────────────────────────────┬───────────────────┘
                   │                              │
┌──────────────────▼─────────────────┐ ┌─────────▼─────────────────────┐
│ SCHEMA (ACDC, content-addressed)   │ │ ISSUER (KERI AID + KEL)        │
│   Same SAID across all who use it  │ │   Issues instances of schemas  │
│   Lives in vault.hby.db.schema     │ │   Lives in kevers + org        │
└──────────────────┬─────────────────┘ └─────────┬─────────────────────┘
                   │                              │
                   └────────────────┬─────────────┘
                                    │
                       ┌────────────▼──────────────┐
                       │ CREDENTIAL (ACDC instance)│
                       │   In vault.rgy.reger      │
                       └───────────────────────────┘
```

Schemas are **shared by content** — anyone using the same JSON has the
same SAID. Ecosystems are **shared by convention** — they're how the
user (or a published manifest) chose to group things. The viewer
respects this distinction.

## Layered architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Ecosystem Viewer plugin                                       │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Pages: schema inspector, ecosystem graph, ...        │    │
│  └────────────────────┬─────────────────────────────────┘    │
│                       │                                       │
│  ┌────────────────────▼─────────────────────────────────┐    │
│  │ EcosystemBaser (plugin LMDB)                         │    │
│  │  ecosystems / annotations / history / provenance     │    │
│  └────────────────────┬─────────────────────────────────┘    │
└───────────────────────┼─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│ locksmith.acdc — domain layer (shared with future Skill)     │
│  inspector.py  → read-side classification of ACDCs/schemas   │
│  builder.py    → write-side composition (planned)            │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│ Wallet core — keripy + Locksmith stores                      │
│  vault.hby.db.schema       vault.hby.kevers / vault.org      │
│  vault.rgy.reger           vault.signals                     │
└─────────────────────────────────────────────────────────────┘
```

Each layer has one job:

- **Wallet core**: persist schemas, KELs, credentials, contacts. Already
  exists. The viewer *reads* from here.
- **Domain layer**: classify what the wallet stores at the spec's
  domain layer (variant, targeting, disclosure, edges). Pure functions
  over field maps. Reusable beyond this plugin.
- **Plugin store**: the user's grouping/annotation/discovery state.
  Things the wallet doesn't natively know.
- **Plugin pages**: render everything the user wants to see, using all
  the layers below.

## What's in this initial commit

The smallest cohesive thing that establishes the architecture and is
useful on its own:

- `locksmith.acdc.inspector` — full domain classification for ACDC
  instances and schemas, spec-grounded (citations in module docstring).
- The plugin scaffold — registers a sidebar entry and a basic page that
  enumerates all schemas currently in the wallet and renders the
  inspector's classification of each. Same for known issuer AIDs from
  contacts.
- This README documenting the design.

What's deliberately deferred:

- `locksmith.acdc.builder` — the write-side companion. Useful when we
  start authoring credentials programmatically (Skill output, automated
  fixtures); not needed for the viewer's read path.
- `EcosystemBaser` — the plugin's LMDB store for groupings,
  annotations, discovery history. Useful once the viewer has multiple
  pages that benefit from cross-page state.
- Ecosystem graph view — directed-graph visualization of edge
  relationships between schemas. Most valuable feature; non-trivial UI
  work.
- Ecosystem editing UI — assigning schemas/AIDs to user-named
  ecosystems, annotating them, browsing by ecosystem.

## Roadmap

Roughly in priority order:

| Stage | Description |
|------:|-------------|
| 1 | (this commit) Inspector layer + plugin scaffold + schema list page |
| 2 | Per-schema detail page (full inspection rendered, edge requirements followed) |
| 3 | EcosystemBaser + UI for creating named ecosystems and annotating members |
| 4 | Ecosystem graph view (directed graph of edge relationships) |
| 5 | Cross-issuer view ("everyone who issues schema X") |
| 6 | First-person view ("given my held credentials, what can I do in this ecosystem?") |
| 7 | ACDC builder (`locksmith.acdc.builder`) for authoring credentials in domain language |
| 8 | Ecosystem export/import — share ecosystem definitions across wallets |

## Spec-vs-convention discipline

After an ACDC spec audit caught several hallucinated primitives in
earlier work, this plugin's code is careful to distinguish:

- **Spec primitives** (called out as such in code comments, with
  citations): top-level field set, variant via `u`, targeting via
  `a.i`, edge operators (I2I/NI2I/DI2I/NOT), edge-group operators
  (AND/OR/NAND/NOR/AVG/WAVG), section forms, disclosure tiers.
- **Convention overlay** (called out as such): the names "ecosystem,"
  "is_private," "disclosure_tier" as a single label, and the user
  constructs in `EcosystemBaser`.

If a future spec change moves a primitive from one column to the other
— or invalidates one we're using — that distinction makes the rework
local and obvious.

## Spec source of truth

Authoritative reference: `kswg-acdc-specification/spec/spec-body.md`
(the ACDC spec body). Inspector docstrings cite specific spec sections
where appropriate. When in doubt, also consult the `keri:chat` skill,
which returns spec-grounded answers with line-number citations.

The `keri:acdc` skill is the entry point for spec primitives in any
session that touches ACDC code.
