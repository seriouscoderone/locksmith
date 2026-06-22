# Publisher Operator CLI + Trust-Root Bootstrap — Design

**Date:** 2026-06-22
**Status:** Approved (brainstorm) — ready for implementation plan
**Repo:** locksmith (`~/code/locksmith`); publisher tool at `tools/publisher/`
**Depends on:** the witness HA federation being live (done — 5×5 CDK, reserved_concurrency dropped, 3-of-5 receipts proven).

## Summary

Build the deferred operator-facing invocation CLI for the publisher's kli pipeline, then use it to (Phase 1) mint the production publisher AID + generate the real trust root, and (Phase 2) ship the first Locksmith version that *trusts* that AID so the in-app KERI update gate goes live. The pipeline **library** (`seal` + `kli` + `publish.anchor_release` + `appcast` + `s3_client`) is already built and proven by a real-witness round-trip test; what is missing is the operator commands that drive it (the `incept`/`anchor`/`sign`/`submit` CLI commands are retired stubs) and a `publisher_anchor.json` generator. This spec adds that thin glue and sequences the two-phase rollout.

## The trust model (why the sequencing is what it is — grounded in the code)

- **KERI is the SOLE update-verification trust.** Sparkle's native EdDSA verification is OFF (`sparkle_bridge.py`: *"Sparkle is used as an orchestrator only … all trust flows through the [`verify_artifact`] gate"*; WinSparkle: `win_sparkle_set_dsa_pub_pem(None)`). There is no second signature to fall back on.
- **The gate trusts only the anchor baked into the running build.** `apping.py:_make_update_verifier` verifies a staged update against the *build-injected* `publisher_anchor.json`. With no real anchor injected it **stays dark — returns `True` without verifying** (never blocks). Installed v0.1.6 shipped gate-dark.
- **An installed app can only verify against the AID it was built with.** Therefore re-anchoring the already-served v0.1.6 helps nobody: no installed build trusts the new AID, and a "0.1.6 that trusts the new AID" would be a *different binary* than the one served. The trust root only matters from the first build that bakes it in, forward.
- **Bootstrap is trust-on-first-use, covered by OS code-signing.** The hop from a dark build to the first gate-live build cannot itself be KERI-verified by the old build. OS code-signing (Apple Developer-ID notarized DMG, Azure-signed MSI → Gatekeeper/SmartScreen) covers that one hop; KERI verifies every update after it. This is inherent to adding verification to an already-shipped app.

## Locked decisions (from brainstorm)

1. **Command granularity: one command per pipeline phase** (`incept`, `gen-anchor`, `anchor`, `publish`; keep existing `appcast`), each a thin wrapper over a tested library function. Auditable, independently testable, clean one-time-vs-recurring split. (Composite/single-command alternatives rejected as harder to test/audit.)
2. **Custody: `kli` keystore + bran.** Single Ed25519 key, pre-rotation committed at inception so the publisher can rotate to hardware later WITHOUT changing the AID. The bran is the secret the operator holds.
3. **Retire the orphaned custody modules** `yubikey.py` + `software_key.py` (+ their tests) — leftovers from the old bespoke design that don't integrate with the kli pipeline. (Confirm no live imports first.)
4. **First anchored release = a NEW bootstrap version (0.1.7) built with the new anchor injected**, NOT a re-anchor of 0.1.6.
5. **Both phases in one plan:** Phase 1 (CLI + mint + trust root), Phase 2 (bootstrap release + gate activation).
6. **No change to the verifier** (`src/locksmith/update/`) or the tested pipeline functions — they are correct.

## Architecture — the operator CLI

A `locksmith-publisher` Click group (replacing the retired stubs in `cli.py`), each command sequencing already-tested library functions. The only new library primitive is an OOBI-resolve wrapper (the pipeline's `kli_incept` does not resolve witness endpoints, which `kli incept --receipt-endpoint` needs).

| Command | When | Sequences |
|---|---|---|
| `incept` | one-time ceremony (operator runs; bran via prompt/`--bran-env`) | `kli init` → **new** `kli_resolve_oobi` × the configured witnesses (from `deploy_config`) → `kli_incept(wits=[5 aids], toad=3, pre-rotation)` → export inception KEL. Emits the publisher AID. |
| `gen-anchor` | one-time, after `incept` | writes `src/locksmith/release/publisher_anchor.json` = `{publisher_aid, toad:3, witness_oobis:[5 from deploy_config], embedded_kel_sn:0, embedded_kel_hash:<inception said>}`. |
| `anchor` | per release | `publish.anchor_release(name, alias, bran, base, version, artifacts, out_dir)` → `<aid>-kel.cesr` + anchor event locally. Artifacts hashed are the **served** `releases/<version>/` dmg+msi (download-or-verify-local). |
| `publish` | per release | `s3_client.upload_release` (KEL → `publisher/v1/kel.cesr`, anchor events → `publisher/v1/anchors/<said>.cesr`) + regenerate/upload appcast (existing `appcast` glue). |
| `appcast` | existing, unchanged | regenerate per-platform appcasts from S3. |

**New library primitive:** `kli.kli_resolve_oobi(*, name, base, bran, oobi: str)` → `kli oobi resolve` subprocess wrapper (mirrors the existing thin wrappers). `incept` calls it once per configured witness before `kli_incept`.

**Reuse, do not reimplement:** `seal.build_release_seal`, `kli.kli_incept`/`kli_interact`, `publish.anchor_release`, `appcast.build_appcast`/`generate_and_upload_appcasts`, `s3_client.S3.upload_release`, `witnesses.default_witness_pool` (the 5 OOBIs/AIDs from `deploy_config`). All exist + are tested.

## Data flow

**One-time ceremony (Phase 1):** operator → `incept` (controlled machine, bran stays local) → publisher AID witnessed 3-of-5 → `publish` the inception KEL to `publisher/v1/kel.cesr` → `gen-anchor` writes `publisher_anchor.json`.

**Recurring release (Phase 2 and onward):** a tagged release → CI builds + signs + notarizes + uploads the dmg/msi to `releases/<version>/` → operator (or CI with keystore+bran as secrets) runs `anchor <version>` (hash the served artifacts → seal → `kli interact` → export KEL) → `publish` (KEL + anchor + appcast). The installed gate-live app polls the appcast, fetches the KEL + anchor, and `verify_artifact` confirms the new release was anchored by the pinned publisher AID at toad before installing.

## Phase 1 — KERI identity + trust root (this effort, runnable now)

1. Build the operator CLI (`incept`/`gen-anchor`/`anchor`/`publish`) + `kli_resolve_oobi` + retire `yubikey.py`/`software_key.py` + tests.
2. **Operator runs `incept`** on a controlled machine (bran held by operator; never enters an agent session). Verify the publisher AID is witnessed 3-of-5 via the public witness side (no bran needed).
3. `publish` the inception KEL → `publisher/v1/kel.cesr` (replacing the stale 2026-06-02 old-publisher content).
4. `gen-anchor` → the real `src/locksmith/release/publisher_anchor.json` (gitignored per the privacy rule; committed template stays `example.com`).

## Phase 2 — bootstrap release + gate activation

5. Bump version to **0.1.7**; ensure the release build injects the real anchor (existing loader order: `$LOCKSMITH_PUBLISHER_ANCHOR` → gitignored `publisher_anchor.json` → example). The release CI must provide the real anchor (a `$LOCKSMITH_PUBLISHER_ANCHOR` GitHub secret, or the gitignored file in the build context). **This is the build that "trusts the new AID."**
6. CI builds + signs + notarizes the 0.1.7 dmg/msi and uploads to `releases/0.1.7/` (the existing release-tag workflow).
7. Operator runs `anchor 0.1.7` (hashing the served `releases/0.1.7/` artifacts) → `publish`.
8. **Verify e2e:** run `verify.verify_artifact` against the live published KEL + anchor + a downloaded 0.1.7 artifact (the path the keystone test already uses). Gate is now live in the 0.1.7 build → every update after 0.1.7 is KERI-verified against the new AID.

## Custody & secrets

- **Bran:** held by the operator; supplied to `incept`/`anchor` via prompt or an env var named by `--bran-env` (never a literal CLI arg, never printed). The keystore dir + bran are the production signing material; stored in the operator's vault / as CI secrets for later automation.
- **Anchor injection:** `gen-anchor` writes the gitignored `publisher_anchor.json`; the release CI injects it via `$LOCKSMITH_PUBLISHER_ANCHOR` (its content — AID + OOBIs + toad + icp said — is not secret, but stays gitignored under the no-personal-domains rule).
- **Bootstrap anchoring stays operator-driven** (anchor the CI-built, already-signed, already-served artifacts locally with the operator's keystore). Moving keystore+bran into CI for fully-automated per-release anchoring is a later hardening, out of scope here.

## Error handling

- `incept`: if a witness OOBI fails to resolve or `< toad` receipts return, fail loudly (do not produce a half-witnessed AID); the operator re-runs. `kli_resolve_oobi`/`kli_incept` surface kli's stderr (the existing `_run` raises on non-zero).
- `anchor`: if the served artifact digest can't be obtained, or `anchor_release` finds no anchor event for the version, fail (no partial publish).
- `publish`: idempotent re-upload (re-running overwrites the same keys); never deletes prior release anchors.
- `gen-anchor`: refuse to overwrite an existing `publisher_anchor.json` without `--force` (guards against clobbering a live trust root).

## Testing (machine-checkable; real KERI path, no mocks)

- **Keystone (extend `tests/integration/test_publisher_roundtrip.py`):** drive the CLI end-to-end through the existing in-process real witness — `incept` → `anchor` → `publish` → `verify_artifact` — asserting `witness_receipts >= 1` and the verifier accepts the output.
- **Unit:** `gen-anchor` (pure — given an AID + icp said + witness list → exact `publisher_anchor.json` shape); `kli_resolve_oobi` arg construction; CLI arg parsing / bran-env handling / `gen-anchor --force` guard.
- **Regression:** the existing verifier tests + the seal/publish unit tests stay green; confirm retiring `yubikey.py`/`software_key.py` breaks nothing (no live imports).

## Scope

- **In:** the operator CLI (`incept`/`gen-anchor`/`anchor`/`publish`), `kli_resolve_oobi`, the `publisher_anchor.json` generator, tests, retiring the orphaned custody modules, and the two-phase execution (mint + trust root; bootstrap 0.1.7 release + gate activation).
- **Out:** changes to the verifier (`update/`) or the tested pipeline functions; fully-automated CI per-release anchoring (keystore+bran in CI) — a later hardening; hardware (YubiKey) signing — deferred (pre-rotation enables it later without changing the AID); backfilling old releases' anchors (abandoned per the greenfield restart).

## Definition of done

The retired CLI stubs are replaced by working `incept`/`gen-anchor`/`anchor`/`publish` commands wrapping the tested library functions; `yubikey.py`/`software_key.py` removed; the keystone test drives the CLI end-to-end through a real witness; the production publisher AID is minted (witnessed 3-of-5) with its KEL published and `publisher_anchor.json` generated; Locksmith 0.1.7 is built with the anchor injected, anchored by the new publisher, and published; `verify_artifact` validates 0.1.7 against the live stream; the in-app gate is live for 0.1.7-and-later.

## Risks

1. **Bootstrap TOFU.** The dark→0.1.7 hop isn't KERI-verified by the old build. *Mitigation:* OS code-signing (notarized DMG / signed MSI) covers it; documented as a known, inherent property; KERI covers all later updates.
2. **CI anchor injection misconfigured** → 0.1.7 ships gate-dark again (silently unprotected). *Mitigation:* a build-time assertion / release check that a non-placeholder `publisher_anchor.json` is present for tagged release builds; the e2e verify step (8) catches it before announcing.
3. **Served-vs-anchored artifact mismatch.** The seal must hash the exact bytes served. *Mitigation:* `anchor` hashes the artifacts downloaded from `releases/<version>/` (or asserts local == served), never a stale local copy.
4. **Losing the bran** = cannot sign future releases. *Mitigation:* pre-rotation gives recovery to a committed next key; operator stores keystore+bran in their vault; documented custody step.
