# schema.keri.host — a `publish_schema` Service-AID + trustless schema-OOBI host

**Status:** design · **Date:** 2026-07-07
**Supersedes design sketch:** `backlog/2026-07-02-schema-oobi-resolution.md` ("Companion: the publish side")
**Sibling:** `backlog/2026-07-02-ecosystem-discoverability.md` (the wallet-side resolve leg — **out of scope here**)

## Goal

Stand up **schema.keri.host**: a public, trustless host that serves ACDC **schemas** by SAID
(`GET /oobi/<said>`), plus a gated **`publish_schema` Service-AID** that accepts signed publish
commands, stores the schema in a content-addressed store, and records every publication as a
KEL-anchored, enumerable **attribution ledger** — optionally handing the publisher a verifiable
**publication receipt** credential.

## Context and guiding thesis

A credential references its schema by **SAID** (a content hash), not a URL — so a wallet knows
*which* schema it needs but not *where* to get it. Today Locksmith has no way to auto-fetch an
unknown schema; a holder must manually load the file. schema.keri.host is the ecosystem's answer to
"where": a SAID-addressed resolver for public SADs.

Two framings shape the whole design:

1. **A Service-AID is abstract, configurable compute inside a KERI ecosystem.** Its pipeline
   (Verify → Authz → Idempotency → Compute → **effect** → Issue → Deliver) is the *full* shape; a
   given service *configures* each stage. `publish_schema` is **not** "the pipeline with Issue/Deliver
   deleted" — it configures the compute effect to *store an artifact* and configures Issue/Deliver to
   mint an optional receipt. The configurable surface is the product; schema.keri.host is one
   instantiation.
2. **BE KERI NATIVE.** Publication accountability, ordering ("first published here"), provenance,
   and receipts are all expressed with KERI primitives — KEL anchoring, ACDC credentials, a TEL
   registry, IPEX delivery, OOBI discovery — never app-logic substitutes.

## Implementation location (not this repo)

The build lands in the **keripy fork** (`~/code/keripy`), not Locksmith:
- `keri_serviceaid/` — framework additions (a new `ArtifactStore` provider + a `publish` reply/effect).
- `keri_cdk/` — deployment construct (Service-AID + S3/CloudFront + custom domain).
- `ecosystems/keri_host/` — the schema.keri.host service definition + the receipt ACDC schema.

Locksmith is **untouched** in this spec (the wallet-side auto-resolution is the sibling
discoverability build). The spec lives here because the design conversation and the originating
backlog items live here; the implementation plan will target the keripy fork.

---

## Architecture: two planes, one hostname

```
                      schema.keri.host  (CloudFront distribution)
                        /                                  \
        GET /oobi/<said>                                    (CESR POST) /schema/cmd/publish
        -> S3 bucket origin (CAS)                           -> API Gateway -> publish_schema Lambda
        application/schema+json                                (Service-AID: the write plane)
        trustless, CDN-cached, no Lambda
```

- **Read plane — trustless, static.** `GET /oobi/<said>` returns the schema JSON with
  `Content-Type: application/schema+json` and `$id == <said>`. The client re-hashes and rejects any
  mismatch, so *any* server (or a wrong one) is cryptographically checkable — the host is trusted
  only for **availability, not integrity**. Reads never touch the Service-AID. Served by **S3 +
  CloudFront** (objects keyed by SAID). This matches keripy's `Oobiery.processClients`
  (`keri/app/oobiing.py`) content-type branch that parses `application/schema+json` into a `Schemer`
  and pins it into `db.schema`, and Locksmith's `core/credentialing.py:_load_from_oobi`
  (`requests.get(oobi)` → `scheming.Schemer(raw=...)`).

- **Write plane — gated, accountable.** A CESR-signed `exn` command on route
  `/schema/cmd/publish` reaches the `publish_schema` Service-AID (keripy `keri_serviceaid`
  pipeline, `handler.py` → `pipeline.py`). The Lambda validates + stores the schema and records the
  publication. Writes are safe to expose because SAID-addressing prevents forge/overwrite; the gate
  is for **accountability, anti-spam, and a verifiable publish log**, not integrity.

- **One CloudFront distribution at `schema.keri.host`** with path-based origins: `GET /oobi/*` → S3;
  the write route (CESR POST) → API Gateway → Lambda. One hostname, one mental model, reads and
  writes separated by path + method. (Rejected: two hostnames — extra DNS/cert surface and a second
  endpoint to know.)

---

## The framework capability layer vs. the schema.keri.host instantiation

The framework gains a **configurable capability surface** so *any* Service-AID can be configured for
store-and-attest work. schema.keri.host is one configuration of it.

### Framework config surface (reusable capabilities added by this work)

| Knob | Meaning | Values |
|---|---|---|
| compute **effect** | what the command *does* | issue-ACDC (existing) · **store-artifact (new)** · none · revoke |
| `receipt_policy` | whether a receipt credential is delivered back | `none` · `on_request` · `always` |
| `receipt_form` | how the receipt is anchored | `none` · **TEL-registry ACDC** (existing `IpexGrantIssuer`) · direct-anchored ACDC (future) |
| `first_seen` | record + report first-publisher per artifact SAID | `track` · `ignore` |
| `lineage` | accept + record origin metadata | on/off |

### schema.keri.host v1 instantiation (locked)

| Dimension | Value |
|---|---|
| Read plane | S3 + CloudFront; `GET /oobi/<said>` → `application/schema+json`, `$id == said` |
| Write route | `/schema/cmd/publish` (CESR-signed `exn`) |
| Verify | `OracleVerifier` (tier `receipts`) confirms sender key-state |
| Authz | **`Allowlist`** of publisher app AIDs (the "a" gate); publisher-credential ("b") gate = documented follow-on |
| Accepted type | **ACDC schemas only** (engine SAD-general; validator asserts `$id == SAID` + valid JSON Schema); **never** private ACDC instances |
| Compute effect | **store schema bytes → S3 CAS** (idempotent by SAID) via the new `ArtifactStore` provider |
| Issue | **TEL registry** — `publication_receipt` ACDC issued per publish (`rip` once at inception + `iss` each), KEL-anchored. The registry TEL **is** the enumerable attribution ledger. |
| `first_seen` | `track` — duplicate SAID → receipt names prior contributor + its OOBI |
| `receipt_policy` | **always mint + `iss` into the registry**; IPEX-**deliver** only `on_request` |
| `lineage` | accept `{origin_ecosystem, origin_oobi}` → recorded in receipt attributes |
| trusted-time | server-asserted `dt` in the receipt; external time anchor **deferred** (slot reserved) |
| wallet client | **out** (belongs to the discoverability build) |

---

## KERI grounding (why the ledger lives in a KEL/TEL, not a blob table)

- **The KEL holds key events; the interaction (`ixn`) event is the non-establishment one whose job
  is anchoring.** KEL event set is `icp/rot/ixn/dip/drt`; `ixn` field order is `[v,t,d,i,s,p,a]` — no
  key material — and the spec states it *"just anchors seals via `a`"*
  (`keri:spec/event-model.md:45,53`). So committing data to a KEL without rotating keys is the
  built-in primitive, not a hack.
- **A seal is a digest commitment, not the data.** *"Seals anchor external data to key state"*; a
  `SealDigest [d]` commits to a SAID; *"when sealed data is a SAD, the digest SHOULD be its SAID"*
  (`event-model.md:83,87,95`). The schema bytes live in the CAS; only the SAID is anchored.
- **This is exactly how ACDCs anchor.** *Direct*: seal = ACDC SAID in KEL, no registry
  (`keri:acdc/disclosure-ipex.md:167`). *Indirect (chosen)*: a **TEL registry** whose inception
  (`rip`) and every update are anchored in the issuer's KEL (`disclosure-ipex.md:171-172`); *"TEL
  events do not need signing — the signed seal digest in the KEL is cryptographically equivalent"*
  (`acdc/tel-registry.md:66`). keripy's release publisher (`publish.anchor_release`) is the same
  anchoring move for release manifests.
- **Reger ≠ TEL.** The `Reger` (keripy `vdr/eventing.py:2255`) is the VDR *database*; it holds both
  the TEL event logs (`.tvts`, `.tels`, `.states`, `.regs`, KEL anchors in `.ancs`) **and** the
  credential store + indexes (`.creds` `SerderSuber(klas=SerderACDC)` at `:2400`, `.saved` `:2420`,
  `.schms`/`.subjs`/`.issus` at `:2422-2426`). The registry TEL is what makes the ledger ordered,
  KEL-anchored, and **enumerable** by issuer/subject/schema.

---

## Components

### 1. Read plane — `SchemaCas` (S3) + CloudFront + OOBI contract

- **S3 bucket** = the content-addressed store. Object key = the schema SAID (qb64); body = the
  schema JSON bytes; `Content-Type: application/schema+json`. Private bucket; public read only
  through CloudFront (Origin Access Control). Written **only** by the publish Lambda's role.
- **CloudFront** at `schema.keri.host`: behavior `GET /oobi/*` maps the SAID to the S3 object
  (`/oobi/<said>` → object `<said>`), long cache TTL (content-addressed = immutable). ACM cert +
  Route53 alias (pattern from `keri_cdk/mailbox_stack.py:351-413`).
- **Contract:** `200` + `application/schema+json` + body whose `$id == <said>`; `404` if absent.
  Verifiable by any KERI client (`Schemer(raw=body)` checks `schemer.said == said`).

### 2. Write plane — `publish_schema` Service-AID

Declared in `ecosystems/keri_host/` using the framework contract
(`keri_serviceaid/contract.py`):

```python
svc = ServiceAid(
    alias="schema-publisher",
    authz=Allowlist([<publisher app AIDs>]),      # the "a" gate (v1)
    artifact_store=S3ArtifactStore(bucket=...),   # NEW provider (see §3)
    # verifier/resolver/issuer/deliverer/idempotency default (issuer = TEL-registry IpexGrantIssuer)
)

@svc.command(
    route="/schema/cmd/publish",
    issues=<publication_receipt schema SAID>,
    publishes_artifact=True,                       # NEW: routes the Reply through ArtifactStore
)
def publish_schema(req: Request) -> Reply:
    sad = req.payload["schema"]                    # the ACDC schema being published
    validate_public_schema(sad)                    # $id == SAID, valid JSON Schema, not an instance
    return Reply.publish(                           # NEW reply kind (see §4)
        artifact_said=said_of(sad),
        artifact_bytes=canonical_bytes(sad),
        recipient=req.sender,
        attributes={                                # base receipt attributes; first-seen + dt merged later
            "schemaSaid": said_of(sad),
            "schemaKind": "ACDC-schema",
            "publisher": req.sender,
            "origin": req.payload.get("origin"),   # optional lineage (publisher-supplied)
            # NOTE: dt is NOT taken from the payload — the server stamps its own recorded-at
            # time at Issue (a publisher-asserted time is meaningless for attribution).
        },
    )
```

The pipeline (`pipeline.py`) then runs, per stage:

1. **Verify** — `OracleVerifier` confirms the sender's key-state (drop on fail).
2. **Dispatch** — route → `publish_schema`.
3. **Idempotency** — `seen(exn.said)`: a re-delivered *request* replays the same receipt (exactly-once
   on the message). Distinct from content-idempotency (same schema SAID), handled by `ArtifactStore`.
4. **Authz** — `Allowlist` membership (drop on deny).
5. **Compute** — validate + shape base receipt attributes; return `Reply.publish(...)`.
6. **Store effect (NEW)** — `ArtifactStore.store(said, bytes, by=sender)` persists to S3
   (idempotent) **and** claims first-seen; returns `{firstSeen, priorContributor}`, merged into the
   receipt attributes.
7. **Issue** — `IpexGrantIssuer` stamps the server's recorded-at `dt`, mints the
   `publication_receipt` ACDC, and `iss`es it into the registry (KEL-anchored). This is the ledger
   entry — always happens.
8. **Record** — idempotency ledger records the receipt for replay.
9. **Deliver** — `PostmanDeliverer` IPEX-grants the receipt to the publisher's mailbox **only if**
   `receipt_policy` says so for this request (`on_request` flag in the exn); otherwise no-op.

### 3. `ArtifactStore` provider (NEW, framework)

`keri_serviceaid/providers/artifact_store.py`:

- **Protocol** `ArtifactStore.store(said: str, raw: bytes, by: str) -> FirstSeenResult` where
  `FirstSeenResult = {created: bool, firstSeen: bool, firstPublisher: str, firstAt: str}`.
- **`S3ArtifactStore`** (prod): `PutObject` to the CAS bucket with
  `ContentType=application/schema+json` (idempotent — same SAID = same bytes), **and** a **DynamoDB
  conditional-write** first-seen claim keyed by artifact SAID in the service's namespace (see §5).
  The conditional write is the serializable primitive; the storage stays a generic verb, so the
  "first publisher" meaning is composed one layer up (no concept leak into storage).
- **`LocalArtifactStore`** (test): in-memory dict + a lock, same contract.

### 4. `Reply.publish` reply kind (NEW, framework)

`keri_serviceaid/contract.py` gains `Reply.publish(artifact_said, artifact_bytes, recipient,
attributes)` (kind `"publish"`). `pipeline.py` branches on it: run `ArtifactStore` → merge
first-seen → `Issue` → `Record` → `Deliver`. Symmetric with the existing `Reply.acdc` /
`Reply.revoke` branches.

### 5. First-seen store (serializable, in the shared DynamoDB core table)

- A first-seen record per artifact SAID, written with a **conditional-put** (`attribute_not_exists`)
  in the service's private namespace on the shared `keri-core` table (namespaces `{alias}:kel`,
  `{alias}:tel`, `{alias}:proc` already exist; add `{alias}:pub` for publication metadata).
- The conditional write is atomic → first writer wins → `firstSeen=true` + record `{by, dt}`. A
  loser reads the existing record → `firstSeen=false`, `priorContributor = {aid, oobi}`.
- This is KERI's *"first seen, always seen, never unseen"* invariant (`keri:spec` key invariants)
  realized at the publication-registry layer, using the same serializable conditional-write pattern
  as the witness DDB first-seen work.

### 6. `publication_receipt` ACDC schema (NEW, self-hosted)

Attributes: `schemaSaid`, `schemaKind`, `publisher` (= issuee AID), `firstSeen` (bool),
`priorContributor` (`{aid, oobi}`, present iff `!firstSeen`), `origin` (`{origin_ecosystem,
origin_oobi}`, optional), `dt` (server-asserted; reserved for a future external time-proof).
Issuer = the schema-publisher AID; issuee/holder = the requester. The receipt's own schema is
**published to schema.keri.host itself** at deploy (self-hosting) so it is OOBI-resolvable.

### 7. Deployment construct (`keri_cdk`)

A `SchemaHostStack` (or an extension of `ServiceAidFunction`) composing:
- `ServiceAidFunction(alias="schema-publisher", handler_ref="schema_host:svc", core_table=...)` — the
  writer Lambda, inception CR (creates AID + registry once), keeper secret `keri/schema-publisher/keeper`.
- The **CAS S3 bucket** + **CloudFront** distribution + ACM cert + Route53 alias at `schema.keri.host`
  (path-routed: `/oobi/*` → S3, write route → API Gateway).
- IAM: Lambda role gets `s3:PutObject` on the CAS bucket + conditional-write on the `{alias}:pub`
  namespace; CloudFront OAC gets S3 read.

---

## Data flow

### Publish (happy path, first publisher, receipt requested)

1. Publisher app signs an `exn` on `/schema/cmd/publish` carrying `{schema, origin?,
   want_receipt: true}`, CESR-POSTs to `schema.keri.host` → API Gateway → Lambda → **204**. (No
   publisher-supplied `dt`; the server stamps its own recorded-at time at Issue.)
2. Verify (key-state) → Authz (allowlist) → Compute (validate; `Reply.publish`).
3. `S3ArtifactStore.store` → S3 `PutObject(<said>)` + first-seen conditional write → `firstSeen=true`.
4. `IpexGrantIssuer` mints + `iss`es the `publication_receipt` ACDC into the registry (KEL-anchored).
5. `PostmanDeliverer` IPEX-grants the receipt to the publisher's mailbox.
6. Anyone can now `GET https://schema.keri.host/oobi/<said>` and get the schema (SAID-verified).

### Publish (duplicate SAID, not first)

Same, except the first-seen conditional write fails → `firstSeen=false`; the receipt reads
`priorContributor = {aid, oobi}` (the first publisher and where to resolve them). S3 store is a
no-op (same SAID = same bytes). Honest "you were not first; X was, here's their OOBI."

### Publish (receipt not requested)

Identical through step 4 (the `iss` into the registry is the always-on ledger entry); step 5 is
skipped. The publisher confirms success by `GET /oobi/<said>` and/or by the registry being
publicly enumerable.

### Read

`GET /oobi/<said>` → CloudFront → S3 → `200 application/schema+json` (`$id == said`) or `404`.
Client verifies the hash.

---

## AuthN / AuthZ

- **AuthN** = the CESR signature on the publish `exn`, verified against the sender's KEL via the
  oracle (`OracleVerifier`). No API keys, OAuth, or shared secrets.
- **AuthZ (v1)** = `Allowlist` of publisher app AIDs (the "a" gate).
- **AuthZ (follow-on, "b")** = a **schema-publisher ACDC** issued by the ecosystem governance root,
  enforced via the framework `CredentialGate` (`providers/credgate.py`) — possession + chain to root.
- **Accountability** = every publish is an `iss` in the KEL-anchored registry, attributable to the
  signing AID and tamper-evident — the verifiable publish log.

## Attribution ledger semantics

- The registry TEL is an **ordered, KEL-anchored, enumerable** record of every publication, queryable
  by issuer/subject/schema (`Reger.issus`/`subjs`/`schms`). "Who provably published SAID X, and in
  what order" is answered by the ledger.
- **Scope honesty:** the claim is *"first recorded in **this** publish log,"* never "first created in
  the universe" — a SAID is a global content hash anyone can compute.
- **Trusted-time honesty:** KERI has no native trusted clock; `dt` is server-asserted (only as
  trustworthy as the operator's signature). Cryptographic **ordering** (first-seen) is strong;
  wall-clock **date** proof needs an external time anchor — deferred, `dt` slot reserved.

## Scope boundaries

- **Schemas only** in v1; the engine is SAD-general (keyed by SAID) so `rule`/`edge`/other *public*
  SADs are a later validator + content-type addition, not a storage change.
- **Never** privacy-sensitive SADs (ACDC **instances**, presentations) — a public CAS keyed by SAID
  would leak subject attributes and defeat graduated disclosure. Enforced by the type-allowlist +
  publisher accountability (not byte-detectable).
- Wallet client-side auto-resolution is **out** (the sibling discoverability build; it also fixes the
  "Unknown Credential" label #7 and the missing-schema dialog crash #9).

## Error handling

| Condition | Behavior |
|---|---|
| Verify fails (bad key-state) | drop (framework default) |
| Authz deny (not allowlisted) | drop |
| Invalid schema (`$id != SAID`, not JSON Schema, or instance-shaped) | reject + log; no store, no issue |
| Duplicate SAID | store no-op; `firstSeen=false`; receipt names prior contributor |
| Request replay (same `exn.said`) | idempotent — same receipt |
| **Publish failure feedback** | v1 **log-only** (framework returns 204 + async effects); a signed **nack `exn`** to the publisher is a documented follow-on. Success is observable via the delivered receipt and/or `GET /oobi/<said>`. |

## Testing

- **Unit (framework):** `ArtifactStore` idempotency + concurrent first-seen race (two claims → exactly
  one `firstSeen=true`); `Reply.publish` pipeline branch (store → merge → issue → deliver-on-request);
  receipt attribute shaping (firstSeen / priorContributor / origin / dt).
- **Unit (service):** schema validation — accept a valid schema; reject `$id` mismatch, non-schema
  JSON, and instance-shaped SADs.
- **Unit (read contract):** `GET /oobi/<said>` returns `application/schema+json` with `$id == said`;
  a keripy `Schemer(raw=body)` verifies and would pin into `db.schema`.
- **Integration (hermetic, counterpart to `grant_license_e2e.sh`):** a publisher AID sends
  `/schema/cmd/publish` → assert (a) schema stored + retrievable via the read contract, (b) a
  `publication_receipt` `iss` in the registry TEL, (c) `firstSeen=true`; a second publisher of the
  same SAID → `firstSeen=false` + `priorContributor` set; receipt delivered only when requested.

## Deployment / ops notes

- keripy CDK conventions: py3.14 arm64 Lambda + `KeriRuntimeLayer`; run `build_layer.sh` before
  `cdk deploy`; deploy by stack name; `AWS_PROFILE=personal`. Keeper is a KMS-encrypted Secrets
  Manager secret minted once at inception (`keri/schema-publisher/keeper`).
- Seed the `publication_receipt` ACDC schema into the CAS bucket at deploy (self-hosting).
- Publisher app AIDs for the allowlist come from a gitignored ecosystem config (no personal AIDs in
  git), matching the federation config-injection pattern.

## Open questions / deferred (not v1)

1. Publisher-credential ("b") authz gate via `CredentialGate` + a schema-publisher ACDC.
2. External trusted-time anchor (RFC-3161 TSA or public-chain) for legal date proof.
3. Broader public SAD kinds (rules, edges, Ricardian text) — validator + content-type per kind.
4. Wallet client-side auto-resolution on admit (discoverability build).
5. Signed **nack `exn`** for publish failures (publisher UX).
6. Direct-anchored receipt issuer as an alternate `receipt_form` (framework capability; not needed
   for schema.keri.host, which chose the TEL registry).

## Repos / branches

- keripy fork — a feature branch off `development` for the framework + CDK + ecosystem additions.
- Locksmith — none in v1.
- Push policy: keripy → the **seriouscoderone fork only** (never WebOfTrust); no pushes without
  explicit approval.
