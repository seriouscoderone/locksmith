# Usurance as Proxy DOI — naming, scope, and migration

## Why a proxy

The U.S. insurance regulatory model has 50+ state Departments of Insurance
issuing producer licenses today. None of them currently bootstrap a KERI
identifier. Until they do, any KERI-native producer-licensing application
needs an issuer to *stand in* — an explicit proxy that:

- Maintains a parallel ledger of licenses
- Honestly discloses that it is not the real DOI
- Plans for handoff once the real DOI bootstraps an AID

Usurance plays that proxy role. This document describes how the proxy is
named, how it bounds what it claims, and how it migrates out of the proxy
role when the real DOI comes online.

## Naming convention

Proxy AIDs follow the form **`usurance-proxy-doi-<state>`**, e.g.:

- `usurance-proxy-doi-ca`
- `usurance-proxy-doi-tx`
- `usurance-proxy-doi-ny`

The proxy nature is visible in:

1. **The AID alias itself** — every wallet UI, log line, and OOBI URL that
   references the issuer surfaces the proxy framing.
2. **Issued credentials' `r` (rule) section** — every license carries
   prose disclosing the proxy nature and pointing here for migration plans.
3. **Public documentation** — this file plus any published manifest
   description for the producer-licensing application.

The convention does **not** apply to non-proxy roles Usurance plays. A
carrier appointment issued by Acme Insurance through Usurance-the-host
is *not* proxy — Acme is a real legal carrier and its AID is named
straightforwardly (e.g., `acme-insurance-ca`).

## Scope of authority

The proxy:

- **Records and attests** producer licensure facts as Usurance has
  reasonable basis to believe them (e.g., verified against state license
  registries via off-chain checks at issuance time).
- **Does not claim** to be the regulator. It does not have jurisdiction;
  it does not enforce; it does not adjudicate.
- **Defers** ultimately to the real DOI. If the real DOI's records
  contradict the proxy ledger, the real DOI wins.

Relying parties (carriers, insureds, downstream applications) consume
proxy credentials by *opting in*. Carriers that appoint producers based
on a `usurance-proxy-doi-ca`-issued `ProducerLicense` are explicitly
trusting Usurance's proxy attestation, not making a claim of equivalence
with the real DOI's authority.

## Migration paths

When the real California DOI bootstraps a KERI AID, two migration
strategies are available:

### Path A — Reissuance under the real DOI's AID

The real DOI mints fresh `ProducerLicense` credentials for every
currently-licensed producer, issued from its own registry. Producers
hold both the legacy proxy credential and the new real-DOI credential
during a transition window. Relying parties update their authorization
patterns to require the new credential's schema/issuer combination.

**Pros:** clean. Each new credential is anchored in the real DOI's KEL
from inception. No reliance on proxy lineage in the post-migration world.

**Cons:** requires the real DOI to do the work of reissuing every
license. Holders must admit new credentials. Relying parties must
update auth rules.

### Path B — Delegation handoff

The proxy AID rotates under delegation from the real DOI's AID. The
real DOI signs a delegation event making the proxy a delegated child
of the real DOI's authority. Existing credentials remain valid; the
proxy's KEL extends with a delegated rotation event that retroactively
roots its authority in the real DOI.

**Pros:** existing credentials continue to verify without reissuance.
Relying parties don't change their auth rules — the issuer chain just
grows an additional link upward.

**Cons:** the legacy proxy credentials remain in circulation. Their
rule blocks still describe the proxy framing even though authority now
chains to the real DOI. Cleanup is incremental and partial.

### Recommended sequence

1. **Day 1 (now):** Operate as proxy. Document the proxy nature in
   alias + rule + this doc. Issue against the proxy registry.
2. **Real DOI bootstrap (eventually):** Coordinate with the DOI to
   establish their AID. Make the proxy AID delegated under the real DOI
   (Path B) — preserves continuity for everyone already holding
   credentials.
3. **Steady state:** New issuances flow from the real DOI directly
   (Path A semantics), even as legacy credentials continue to verify
   via the delegated proxy.

This is a hybrid: Path B for transition, Path A for new business. The
manifest format does not need to change to support either path —
delegation events are already first-class in KERI; reissuance is just
new credentials on a new registry.

## What changes for whom at migration time

| Party | Before migration | After Path B handoff |
|---|---|---|
| Producer | Holds proxy `ProducerLicense` | Same credential; verification chain now includes real DOI |
| Carrier | Verifies via proxy issuer KEL | Same auth pattern; verification chain now reaches real DOI |
| Relying party | Trusts proxy attestation explicitly | Trust extends transitively to the real DOI via delegation |
| Auditor | Reads proxy rule disclosure | Reads same rule disclosure plus delegation chain |

The substrate (KEL/TEL/ACDC) carries the migration without anyone
re-issuing or re-admitting.

## What this means for ourselves

- Never call the AID `doi-producer-licensing` or anything that
  obscures the proxy nature.
- Never write rule prose that asserts authority equivalent to the real
  DOI.
- When we eventually publish OOBIs (witnesses, mailbox, schemas), the
  proxy state will be visible from the AID alias outward — make sure
  any web-rendered representation of the issuer reflects this.
- Track the real DOI's KERI bootstrap progress; when it's imminent,
  prepare the delegation handoff in advance so transition is a single
  signed event.
