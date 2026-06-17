# Greenfield Publisher Rebuild (kli-based) — Design

**Date:** 2026-06-17
**Status:** Approved (brainstorm complete; ready for implementation plan)
**Repos:** `locksmith` (the publisher pipeline, trust-anchor bundling, verifier — already correct). Consumes keripy `kli` **as-is** (no keripy changes).
**Depends on:** the SAM→CDK federation cutover (fresh 5 witnesses must exist before the publisher AID can be incepted/anchored). Separate prerequisite track; this spec can be built and unit-tested before the cutover, but end-to-end validation waits for it.

## Goal

Replace the bespoke `tools/publisher` release-anchoring stack with a **thin pipeline of stock `kli` (KERI CLI) commands** + an S3 upload + appcast update. The publisher AID is a normal KERI controller driven by `kli`; correct witness-receipt collection and KEL export come for free from keripy, which eliminates the wig-attachment bug by construction. Greenfield — no backfill of old versions.

## Background (verified)

- A KERI witness's `/` event POST returns `204`; receipts return on the synchronous `/receipts` endpoint (`agenting.Receiptor`) or via mailbox SSE — never on the event POST. (`WebOfTrust/main`, confirmed this session.)
- **`kli` already does this correctly, opt-in via `--receipt-endpoint`:** `kli incept`/`kli interact` route to `Receiptor` when `--receipt-endpoint` is set (`src/keri/cli/commands/{incept,interact}.py`, the `if self.endpoint:` branch → `Receiptor.receipt(...)`); the default branch uses `WitnessReceiptor`, which hangs over HTTP. **All publisher kli calls MUST pass `--receipt-endpoint`.**
- **`kli export --alias <a> --files`** writes `<aid>-kel.cesr` by iterating `db.clonePreIter(pre)` (`src/keri/cli/commands/export.py:88`), i.e. the full KEL **with wigs/sigs attached inline** — exactly what the verifier replays.
- The verifier side is already correct and stays unchanged: `locksmith/src/locksmith/update/verify.py` (`verify_artifact`) → `update/kel_replay.py` (`replay_kel`: temp `Baser` + `Kevery` + `clonePreIter` + `db.wigs` toad check). It was only ever blocked by the publisher emitting an invalid stream.
- The old `tools/publisher` (PEM signing + JSON state + `witness_client` + standalone-`rct` sidecars + a non-existent `kel.cesr` producer) is what produced the broken/absent stream. It retires.
- **`kli` is the headless Controller-role embodiment.** This is the role-facade idea realized by consuming keripy's reference CLI rather than building a new facade.

## Architecture

The publisher is a **kli-driven controller** plus glue. Three stock kli calls do all KERI work; the rest is non-key plumbing (digest, upload, appcast, bundle):

1. **Inception (one-time, local):**
   `kli init --name publisher --base <dir>` then
   `kli incept --name publisher --alias publisher --receipt-endpoint --wits <5 fresh witness AIDs> --toad 3 --transferable --icount 1 --isith 1 --ncount 1 --nsith 1`
   → fresh publisher AID, **3-of-5** witnessed over HTTP (receipts land in `db.wigs` via `Receiptor`), pre-rotation enabled (`ncount/nsith`).
2. **Per-release anchor (CI):**
   `kli interact --name publisher --alias publisher --receipt-endpoint --data '<release seal>'`
   → an `ixn` at sn=N anchoring the release seal, 3-of-5 witnessed.
3. **KEL export:**
   `kli export --name publisher --alias publisher --files` → `<publisher-aid>-kel.cesr` (wigs inline).
4. **Publish (non-key glue):** upload `kel.cesr` to `releases.keri.host/publisher/v1/kel.cesr` (S3) and update the appcast's `publisher_kel_url` + embedded `{publisher_aid, kel_sn, kel_said, toad}` for the new release.
5. **Trust anchor:** the bundled `publisher_anchor` (publisher AID + witness OOBIs + embedded sn/said + toad) ships in locksmith so the verifier has a root.

### The release seal (what `kli interact --data` anchors)

A seal carrying enough to bind a downloaded artifact to the anchored release: **release version + per-platform binary digests** (e.g. a SAID-addressed release manifest `{v, artifacts:{<platform>:<digest>}}`, with the `ixn` anchoring `[{"d": <manifest-SAID>}]` or the manifest inline in `a`). The exact field layout is pinned in the plan by reading what `verify_artifact(...)` checks (it takes `artifact_path, platform, embedded_kel_sn, embedded_kel_said, …`), so the anchored data must let the verifier match the downloaded artifact's digest for its platform at the embedded event. **The manifest/seal format is the publisher↔verifier contract** and gets a round-trip test.

## Custody posture

- **Incept once on a controlled machine** — the publisher seed/inception never touches CI.
- **Per-release `kli interact` runs in CI** with the keystore + `--bran` provided as CI secrets.
- **Pre-rotation is the safety net:** the AID is incepted with a pre-committed next key (`ncount=1, nsith=1`); if a CI-resident current key leaks, rotate out (`kli rotate --receipt-endpoint`) without losing the AID or its anchored history.
- `kli export` also opens the keystore (read-only) — same secret. The S3 upload + appcast steps need only AWS creds, no KERI keys.

## Privacy (committed vs not)

Per the standing rule — **no personal domains / AIDs / zone-IDs committed**:
- Witness AIDs, witness OOBIs (which contain the real domains), the publisher AID, and the deploy config live in **gitignored** files; committed templates use `example.com` placeholders (the "rename-an-example-to-an-ignored-name" pattern).
- **`publisher_anchor.json` moves to this pattern:** the current `src/locksmith/release/publisher_anchor.json` (real OLD, soon-destroyed AID) is **de-committed**; a committed `publisher_anchor.example.json` holds `example.com` placeholders; the real anchor is a **build-time injected artifact** (gitignored, supplied at release-build from a secret/local file) so the shipped binary carries the real trust root without the repo doing so. This both honors the rule and removes the stale old AID.

## What retires / changes

- **Retire** the custom KERI parts of `tools/publisher`: `release_anchor.py` receipt-sidecar logic, `witness_client.py`, PEM/JSON-state signing, `signing_context.py`'s KERI-event building. (Apple/Azure **code-signing** is separate and untouched.)
- **Keep / repurpose** the non-key glue: `s3_client.py` (upload), `appcast.py` (appcast + `publisher_kel_url`), and any digest/manifest helpers — now orchestrated around kli output.
- **Unchanged:** `update/verify.py`, `update/kel_replay.py` (verifier).
- The in-app updater verify gate (`core/apping.py`, currently stubbed `lambda: True`) is wired to the real `verify_artifact` **only after** a valid `kel.cesr` is published against the fresh federation — i.e. publishing stays dark until the cutover is done and the first real anchor exists.

## Testing / validation

- **Unit/integration (pre-cutover, no network):** a test that incepts a publisher AID against an **in-process real keripy witness over HTTP** (the `setupWitness` + `--receipt-endpoint` pattern, mirroring the ConfirmDoer integration test), runs an `interact` anchor, `kli export`s the KEL, and asserts `verify_artifact`/`replay_kel` validates it (toad met, artifact digest bound). This is the publisher↔verifier round-trip on the real machinery — the thing the old tests faked with manual `db.wigs.put`.
- **Real-AWS (post-cutover):** incept the real publisher against the fresh 5 witnesses, anchor a real release, publish `kel.cesr`, and verify a downloaded artifact end-to-end; then wire the updater gate.

## Out of scope

- The SAM→CDK federation cutover (prerequisite, separate spec).
- Backfill of v0.0.16…v0.1.6 (greenfield — abandoned).
- Any keripy change (`kli` is consumed as-is).

## Provenance

Grounded in `~/code/KERI-COMMUNICATION-MODEL.md`, the verified `kli` source (`incept.py`/`interact.py` `--receipt-endpoint` → `Receiptor`; `export.py` → `clonePreIter`), the publisher-bug investigation, and the maintainer (Kent Bull) confirmation that `Receiptor`/`/receipts` is the correct path.
