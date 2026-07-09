# Publisher v2 reset + SAID-native release seal

**Date:** 2026-07-09
**Domain:** release publisher ↔ verifier contract × KERI v2 (full-CESR)
**Supersedes the (mis-diagnosed) backlog:** `backlog/2026-07-09-release-seal-not-v2-cesr-serializable.md`

## Problem (corrected root cause)

`locksmith-publisher anchor` fails at `kli interact` with `ERR: Invalid value while
serializing`, blocking the v0.2.20 *publish* (the build + S3 artifacts are fine).

The backlog blamed the seal shape ("nested dict not v2-CESR-serializable"). **That is
wrong** — verified this session: the exact seal serializes fine via `eventing.interact`,
`hab.interact`, and a real `kli interact` on a *clean v2* hab. The real cause: the
`publisher` hab's KEL is **v1** (`KERI10JSON` icp + the v1 0.2.18/0.2.19 ixns), and on
the v2 base `kli interact` (no `--version`) appends a **v2 ixn onto the v1 KEL** — a
protocol-version mismatch mid-KEL that breaks the witness-receipt path
(`agenting.Receiptor.receipt` → `hab.msgOwnEvent`). A KEL cannot change protocol version
mid-stream.

## Decision: reset to v2 (greenfield)

Nobody is using v1 yet, so the only objection to a new publisher identity — breaking
release verification for deployed apps bound to the old v1 publisher AID — is moot.
Re-incept the publisher as a **clean v2 AID** and, while doing it right, move the release
seal to the **SAID-native** shape (per BE-KERI-NATIVE: a seal references a digest, not
free-form app data). This replaces the earlier "pin the publisher to v1" idea.

Scope is **publisher-only**. The wallet's ACDC/IPEX/serviceaid v1 holds are **not**
in scope — they are blocked by *missing upstream v2 code* (v2 ACDC issuance/registry/IPEX
don't exist in keripy yet), not by v1 users, and "starting over" cannot build primitives
that aren't written. See `docs/keri-v2-hold-registry.md`.

## Architecture

### 0. Validate-early gate (do FIRST, before any rework)

Re-incept a **throwaway** v2 AID against the real federation and confirm the witnesses
**receipt a v2 publisher's ixn** (`kli incept --version 2.0 --wit … --toad … --receipt-endpoint`
then `kli interact --receipt-endpoint` with a digest-seal anchor). This is the exact path
that failed. If the federation cannot receipt v2 events, **stop and reassess** — the scope
then grows to a federation-v2 decision (keri_cdk witnesses), out of this spec. Touches
live infra → run in the main session, user-gated.

### 1. Publisher → clean v2 AID + re-issued trust anchor

- Re-incept `publisher` as a v2 AID (destroy/replace the v1 `publisher` keystore;
  `kli incept --version 2.0`, witnessed, `--receipt-endpoint`).
- Regenerate `src/locksmith/release/publisher_anchor.json` (gitignored, build-injected)
  to bind the **new v2 publisher AID** (via `anchor_doc.py`).
- Old v1 anchors (0.2.18/0.2.19) become moot; the in-app verify gate is dark, and
  greenfield means nothing verifies them.

### 2. SAID-native seal + release SAD

- **Release SAD** (self-addressing; `ver`, never the reserved `v`):
  ```
  {"d": <said>, "brand": <brand>, "ver": <version>,
   "artifacts": [{"platform": <p>, "sha256": <hex>}, ...]}
  ```
  `keri.core.coring.Saider.saidify` fills `d` (a bare `d`-only SAD saidifies cleanly — no
  `v`/`t` needed; verified this session).
- **KEL anchor** = a digest seal carrying the SAID **plus** the freeze-defense scalars:
  ```
  {"d": <said>, "brand": <brand>, "ver": <version>}
  ```
- **Why brand+ver stay in the KEL seal (not only in the SAD):** the multibrand
  downgrade/freeze defense (`highest_version_for_brand`) must be **omission-resistant** —
  it must see every version ever published from the *tamper-proof* KEL. Versions in only
  the mutable appcast could be omitted to force a downgrade. So brand+ver are read from
  the KEL; `d` binds the full per-platform artifact detail (which moves into the SAD).
  This is more native than today (a real digest seal + flat scalars) while preserving the
  security property.

### 3. SAD lives in the appcast (JSON feed)

The verifier already fetches the JSON appcast, so each release's SAD is embedded there
(no new S3 object). Tampering the appcast SAD breaks `saidify(SAD) == d` against the
tamper-proof KEL anchor. `build_appcast` embeds the SAD per release entry; the Sparkle
XML feed is unchanged (KERI-agnostic).

### 4. Verifier rework

- `update/kel_replay.py` `extract_release_seal`: return the digest seal `{d, brand, ver}`
  (find the event whose SAID == anchor_said; return the `a` entry that has a `d`).
- `update/kel_replay.py` `highest_version_for_brand`: read `brand`/`ver` from the digest
  seals in the KEL (unchanged behavior, new field names — `ver` not `release.v`).
- `update/verify.py`: from the KEL seal take `brand`/`ver` (freeze-defense) + `d`; resolve
  the release SAD from the appcast; assert `saidify(SAD) == d`; read the per-platform
  `sha256` from the SAD; cross-check the downloaded artifact + the appcast sha256 (as
  today, the downgrade defense).

### 5. Housekeeping

- Correct `backlog/2026-07-09-release-seal-not-v2-cesr-serializable.md` (real cause =
  v1-hab/v2-interact mismatch; resolution = publisher v2 reset).
- Update `docs/keri-v2-hold-registry.md`: move the release-seal row from 🟢 actionable to
  ✅ ON-V2 (publisher reset to v2).
- Re-run the 0.2.20 publish (artifacts already in S3, `/tmp/promote-0.2.20/promote.sh`).

## Files to touch

- Publisher (`tools/publisher/src/locksmith_publisher/`): `seal.py` (build SAD + saidify;
  build the digest seal), `publish.py` (`anchor_release` anchors `{d,brand,ver}`, records
  the SAD), `cli.py` (embed SAD in `build_appcast`), `anchor_doc.py` (new v2 publisher
  anchor). `kli.py` interact no longer needs a version hack (the hab is v2).
- Verifier (`src/locksmith/update/`): `kel_replay.py`, `verify.py`, `appcast.py` (+ the
  `Appcast` aggregate to carry the SAD).
- Config: `src/locksmith/release/publisher_anchor.json` (regenerated, gitignored).
- Docs: the backlog + the registry.

## Testing

- **Unit round-trip on the v2 base:** `build_release_seal` → SAD + `saidify` → anchor the
  `{d,brand,ver}` digest seal via `kli interact` on a **v2** hab → verifier
  `extract_release_seal` + resolve SAD from a built appcast + `saidify(SAD)==d` → same
  brand/ver/per-platform sha256s. No mocks — real temp v2 `Habery`.
- **Multibrand freeze-defense:** two anchored versions for a brand → verifier rejects the
  lower; `highest_version_for_brand` reads from the KEL digest seals (omission-resistant).
- **Live witness-receipt gate (task 0):** throwaway v2 AID receipts on the real
  federation (main session, user-gated).
- **Acceptance:** the real 0.2.20 publish succeeds — publisher v2 AID anchors the digest
  seal, appcast carries the SAD, and a verify pass binds the artifact.

## Risks / notes

- **Federation v2-readiness** is the load-bearing unknown — task 0 gates everything.
- Re-inception + trust-anchor re-issue + the real publish touch live infra + the real
  publisher key (bran) → main session, explicit user go-ahead per step; nothing pushed
  or published without it.
- BE-KERI-NATIVE: the digest seal `{d,...}` references a SAD; the `brand`/`ver` scalars
  are the minimal identifying metadata the KEL-native freeze-defense requires, not
  free-form app payload (which lives in the SAD).

## Out of scope

- Wallet ACDC/IPEX/serviceaid v1 holds (upstream-blocked; registry-tracked).
- Federation (witness/mailbox) v2 posture — only *probed* by task 0; a federation reset
  is a separate decision if task 0 fails.
- Peer-blob import → v2 (the other actionable-now item; separate investigation).
