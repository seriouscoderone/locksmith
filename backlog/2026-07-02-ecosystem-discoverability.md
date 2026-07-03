# Ecosystem discoverability — supersedes "Service-AID should push full provenance" (was bug #1)

**Status:** backlog · **Raised:** 2026-07-02 · **Priority:** high (it's the load-bearing item)
**Reframed:** 2026-07-02 — do **not** implement this as "push the whole KEL/TEL"; implement discoverability so receivers pull.

## Original framing (what we saw)

In the Stage-2 demo the Service-AID's deliverer (`keripy/keri_serviceaid/providers/deliver.py`
`PostmanDeliverer`) sent only the IPEX **grant exn** (acdc + iss + anc) to the holder. The
holder (a real wallet) then couldn't verify it — it lacked the **issuer's KEL** (the DOI is
witness-less; its OOBI 404s) and the **registry TEL (vcp)**. The grant escrowed, was dropped
as stale, and we had to **hand-feed** the DOI KEL + registry TEL into the holder's mailbox to
make the admit succeed. The naive conclusion was "bug #1: make the deliverer push the whole
enchilada (KEL + TEL) alongside every grant."

## Reframe — the real fix is discoverability, not bundling

Pushing full provenance on every message is the **workaround for an immature/undiscoverable
ecosystem**, not the target design. A **discoverable + self-freshening** ecosystem lets the
receiver stay **lean** (send the message; the receiver pulls whatever it's missing). Lean +
pull is both more efficient (no re-shipping cacheable KELs) **and more trustworthy** (below).

**Do NOT** make "the Service-AID deliverer bundles KEL+TEL" the primary/default path. Keep
push-provenance **only** as the disconnected-edge fallback: genuinely offline / one-shot /
air-gapped / first-contact-with-no-channel (QR handoff, "Peer (offline)", file import). Rare
in a mature ecosystem, not gone.

## Why lean+pull is *more trustworthy* than the enchilada (the key insight)

- **Verifiability is equal either way.** A KEL is content-addressed (the AID *is* the hash of
  its inception); you can't forge a KEL for an existing AID. Push vs pull doesn't change that.
- **Duplicity/equivocation protection is NOT equal.** A bare, self-signed KEL pushed from a
  **witness-less** issuer carries **no witness receipts** → no protection against the controller
  showing a *different* KEL to different parties (sign two conflicting events at the same sn,
  hand each party one). You'd only catch it by comparing notes out-of-band. **Witnesses** (an
  honest threshold receipting exactly one event per (AID, sn)) turn that into *prevented /
  detected at receipt time.* So a witnessed, discoverable KEL is strictly stronger than a
  hand-pushed bare one.
- **Authority is a separate, governance layer.** A valid KEL proves "this is a self-consistent
  identity," NOT "this AID is the legitimate DOI for a role." That binding (name/role → AID)
  comes from a **trust root / EGF governance**, and applies equally to push and pull. The
  discomfort of "you have to trust the sender beforehand" is real and is answered here, not by
  bundling.

Net: **witnessed + discoverable + governed = verifiable KEL + witness attestation (duplicity
protection) + authority binding** — leaner *and* more secure than the enchilada. The enchilada
is what you do when you don't have that yet.

## The actual work (three legs — all three needed for #1 to dissolve)

1. **Issuer key-state discoverable.** Witness the issuers (Service-AIDs / DOIs) and/or serve
   their current key-state via the shared DDB oracle (already started — the DynamoDBer
   per-store namespace pooling of **key-STATE + reachability**; see project memory
   `project_kel_public_shared_oracle`). The holder pulls current key-state to verify.
2. **Schemas discoverable.** OOBI-resolvable schemas by SAID — see sibling item
   `2026-07-02-schema-oobi-resolution.md` (same class of problem; also fixes the "Unknown
   Credential" label #7 and the missing-schema dialog crash #9).
3. **Wallet wires the escrow→pull reaction.** Today the wallet *escrows* an unverifiable grant
   but doesn't auto-fetch the issuer's KEL/TEL. Wire the escrow cue → resolve the issuer OOBI
   / send a targeted `qry` (`route=logs`/`ksn`/`tels`), then let the escrowed grant reprocess.
   Also address the **stale-escrow-drop timing** we hit (a grant escrowed then got dropped as
   stale *before* the provenance arrived — "Exchange partially signed unescrowed: Stale exn").

## Contract note

A good micro-app / exn contract should **declare its provenance expectation** — what the
receiver is assumed to already have vs. what the sender must supply — so neither side guesses.
Ties to `project_microapp_open_contract`.

## Evidence / references

- Demo: witness-less DOI (`stage2doi`, EO6kWDH…, OOBI 404) + async serverless mailbox → lean
  grant → holder couldn't pull → escrow → drop → hand-fed KEL + registry TEL to complete the
  admit. Full trace in `.superpowers/sdd/progress.md` (git-ignored).
- keripy `sendArtifacts` (`vdr/credentialing.py`) = the recipe for full provenance if ever
  needed for the offline fallback: issuer KEL + registry TEL + credential TEL.
- Related project memories: `project_kel_public_shared_oracle` (the pull source),
  `project_peer_mode_shipped` (direct/offline path), `project_microapp_open_contract`.
- Sibling backlog: `2026-07-02-schema-oobi-resolution.md`.
