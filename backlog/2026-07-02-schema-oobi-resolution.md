# Feature request: automatic schema resolution via trusted schema-OOBI resolvers

**Status:** backlog · **Raised:** 2026-07-02 (during the Stage-2 DOI→Carrier admit demo)
**Priority:** high for the credential-holder UX (blocks "admit just works")

## Problem

An ACDC credential references its schema by **SAID** (a content hash, e.g.
`ELK09oTcRiiv-Zmxl-rjKo6EVyOLV-5o4SK96g1kSUie`) — deliberately **not** a URL, so the
reference is location-independent and tamper-proof. But that means the credential tells
the wallet *which* schema, not *where* to get it. Today Locksmith has **no automatic way
to fetch an unknown schema**, so a holder must **manually Load Schema from a file** before
they can admit a credential. In a real ecosystem the holder won't have the file.

## Current behavior (verified in code, 2026-07-02)

- **No auto-resolution on admit.** When a grant arrives with an unknown schema SAID,
  nothing tries to fetch it. The only schema-from-OOBI path is the **manual** Load
  Schema → *OOBI* option (`core/credentialing.py:_load_from_oobi`), where the user pastes
  a URL themselves.
- **A root/API OOBI mechanism exists but is inert.** `core/apping.py`
  `_resolve_default_oobis_if_needed()` resolves a single `root_oobi` (+ `root_aid`) and a
  single `api_oobi` (+ `api_aid`) once on vault-open — but the defaults are empty
  (`configing.py`: `DEFAULT_ROOT_OOBI = ""`, etc.) and there's a standing
  `TODO(KERI Foundation): Populate ... will no-op until those values are set`. Even when
  set, this resolves a *trust anchor / API AID*, **not** an arbitrary schema by SAID.
  (The KERI-Foundation "ROOT url" config screen that set these was removed; it was
  already inert in this fork.)
- **This also causes the "Unknown Credential" label** (`ui/vault/notifications/list.py:
  _resolve_schema_title` → `verifier.resolver.resolve(said)` reads the **local** schema
  store only). No local schema → no title → notifications show "Unknown Credential".

## Proposed feature (KERI-native)

Maintain a small, configurable list of **trusted schema-OOBI resolver endpoints**. When
the wallet encounters a schema SAID it doesn't have locally (on admit, or when rendering a
notification/credential):

1. Try each configured resolver in turn: `GET <resolver>/oobi/<schema-said>`.
2. **Verify the returned schema's SAID matches** the requested SAID (self-addressing means
   *any* server's response is cryptographically checkable — you cannot be spoofed and it
   doesn't matter which server answers).
3. Load the first valid match into the local schema store; fall through to the next
   resolver on miss/mismatch; surface a clear error if all fail.

This is the "try trusted resolvers, verify by hash" pattern the user proposed. Because
verification is by SAID, the resolver list is a **discovery convenience, not a trust
dependency** — a malicious/wrong server simply fails the hash check.

## KERI-native rationale

- Schema identity is a SAID (content hash), not a URL — location-independent + integrity by
  construction. Do **not** embed a mutable URL in the credential; keep the SAID and resolve
  the location separately. (Same philosophy as KEL/AID resolution via OOBI.)
- This is the schema-side analogue of the witness-less-issuer problem hit in the same demo:
  the issuer's KEL and the credential's schema should **both** be OOBI-resolvable so the
  holder wallet pulls them transparently. In the demo both had to be hand-fed.

## Related bugs (surfaced in the same session; see .superpowers/sdd/progress.md)

- **#7** — notifications show "Unknown Credential" instead of the schema title when the
  schema isn't local (fixed for free once auto-resolution lands, or by resolving the title
  through the same resolver).
- **#9** — `AcceptGrantDialog` fails to open at all when the schema is missing:
  `_parse_schema_fields` detects "Schema not found" and calls `show_error(...)` during
  `__init__`, which crashes on `AttributeError: '_base_height'` (accept_grant.py:404). Even
  independent of this feature, that path should surface a clean "schema not loaded — resolve
  it?" prompt instead of a silent no-op.

## Acceptance criteria

- Admitting a credential whose schema is unknown auto-resolves the schema from a configured
  resolver, verifies SAID match, loads it, and proceeds — no manual file load.
- A settings surface to view/edit the trusted schema-resolver list.
- SAID mismatch from a resolver is rejected (and logged), never loaded.
- Notification titles resolve for not-yet-local schemas (fixes #7).
- Missing/unresolvable schema shows a clear, non-crashing message (fixes #9).

## Companion: the publish side — a schema server (`schema.keri.host`)

The resolve side above assumes schemas are *fetchable by SAID* — which means someone must
**host** them. Design the host as a **SAID resolver for public SADs** (ACDC **schemas** first),
with two different trust models on its two sides:

### Reads — open + trustless
`GET /oobi/<said>` returns the SAD; the client verifies `hash(content) == SAID`. Fully public /
CDN-able. The server is trusted only for **availability, not integrity** — a wrong/malicious
answer fails the client's hash check. So you can run **several redundant servers** and clients
try each + verify (this is the "trusted resolvers, verify by SAID" list from the resolve side —
no single point of trust).

### Writes — gated (it's a Service-AID)
Not for integrity (SAID-addressing already prevents forge/overwrite) but for **accountability,
anti-spam/DoS, curation, and a verifiable publish log**:

- **AuthN** — publish as a **signed request/exn from your app's AID** (keripy CESR-signed
  request); the server verifies the signature against the app's KEL (via the discoverability
  oracle — same key-state source as everything else). No API keys / OAuth / shared secrets.
- **AuthZ (BE KERI NATIVE)** — gate on a **"schema-publisher" ACDC** issued by the ecosystem
  governance root (possession + chain to root), *not* an app-logic allowlist or API key.
  Maturity path mirrors the Service-AID gated-retrieval a→b: **MVP** = app-AID signature +
  small allowlist (the "a" gate); **mature** = publisher ACDC (the "b" gate).
- **Publish log / provenance** — **anchor each published schema SAID as a seal in the
  server-AID's KEL** (same pattern as the release publisher's `publish.anchor_release`): an
  ordered, tamper-evident, KERI-verifiable record of *which SAID, published by which app AID,
  when*. (Or a TEL registry per schema if you want issuance/revocation semantics.)
- **Idempotent by construction** — POST content → server verifies SAID self-consistency
  (`hash == claimed SAID`, reject garbage) → stores under `<said>` → `GET /oobi/<said>`
  retrieves. Same content = same SAID = dedup/no-op.

### Scope — schemas / public SADs ONLY
Host ACDC **schemas** and other public-by-design SADs (rules / Ricardian text, edge & operator
defs). **Never ACDC *instances*** — those carry private subject attributes and are
holder-controlled via IPEX; a public CAS keyed by SAID would leak them to anyone who learns the
SAID (defeats graduated disclosure). Credential instances are a *different*, access-controlled
concern, not this server.

### Realization
The server **is a Service-AID** — a `publish_schema` role: `verify(signed by app AID) →
authorize(publisher credential) → store + host + anchor SAID in KEL`. It reuses the Service-AID
pipeline, the credential-gate (`project_gated_retrieval_credential_gate`), the discoverability
oracle (`project_kel_public_shared_oracle`), and the release-anchoring pattern — and sits in the
keri.host infra alongside mailbox / witness / releases. Reads remain the trustless
`GET /oobi/<said>` side.

## References

- `core/credentialing.py` (`_load_from_oobi`, the Loader) · `core/apping.py`
  (`_resolve_default_oobis_if_needed`) · `core/configing.py` (`root_oobi`/`api_oobi`) ·
  `core/remoting.py` (`resolve_oobi_sync`) · `ui/vault/credentials/received/accept_grant.py`
  (#9) · `ui/vault/notifications/list.py` (`_resolve_schema_title`, #7).
