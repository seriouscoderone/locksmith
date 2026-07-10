# Release seal fails to anchor on the v2 base — publisher anchor `kli interact` fails

**Filed:** 2026-07-09 (blocked the v0.2.20 *publish*; build was fine)
**Domain:** publisher ↔ verifier seal contract × KERI-v2 (full-CESR)
**Severity:** was release-blocking for publish
**Status:** ✅ RESOLVED via `feat/publisher-v2-reset` (spec/plan `docs/superpowers/{specs,plans}/2026-07-09-publisher-v2-reset*`).

## Symptom
`locksmith-publisher anchor` failed at `kli interact`:
```
kli interact --name publisher --alias publisher --base publisher --receipt-endpoint --data {...}
  failed (255): ERR: Invalid value while serializing
```

## Root cause (CORRECTED — the original theory below was DISPROVEN)

**Original (wrong) theory:** the seal was a v1-style free-form nested dict
(`{"release": {"brand", "v", "artifacts": [...]}}`) and v2 full-CESR's field-map
serializer (`keri/core/mapping.py`) can't serialize a nested dict / list-of-dicts
in the ixn `a` field.

**Why it's wrong (verified this session):** the exact seal serializes fine via
`eventing.interact`, `hab.interact`, and a real `kli interact` on a *clean v2*
hab. The `a` field accepts a mapping value.

**Actual root cause:** the `publisher` hab's KEL is **v1** (`KERI10JSON` icp + the
v1 0.2.18/0.2.19 ixns). On the v2 keripy base, `kli interact` (no `--version`)
appends a **v2 ixn onto the v1 KEL** — a protocol-version mismatch mid-KEL. A KEL
cannot change protocol version mid-stream; the mismatch breaks the witness-receipt
path (`agenting.Receiptor.receipt` → `hab.msgOwnEvent`), surfacing as the generic
serialization error. Nothing to do with the seal *shape*.

## Resolution (SHIPPED)

Greenfield — nobody is bound to the old v1 publisher AID — so the fix is a
**publisher v2 reset**, done right:

1. **Re-incept the publisher as a clean v2 AID** (destroy/back up the v1 keystore;
   `kli incept --version 2.0 --receipt-endpoint`). A fresh v2 KEL takes v2 ixns
   with no mid-stream version change. (`publisher_anchor.json` regenerated to bind
   the new v2 AID.)
2. **SAID-native release seal** (also more BE-KERI-NATIVE — a seal references a
   digest, not free-form app data):
   - Release **SAD** (saidified via `Saider.saidify`):
     `{"d": <said>, "brand", "ver", "artifacts": [{"platform", "sha256"}, ...]}`
     — note `ver`, **never** the reserved `v` label (`deversify` would choke).
   - KEL anchor = a **digest seal** `{"d": <said>, "brand", "ver"}`. `brand`/`ver`
     stay in the KEL seal so the multibrand freeze-defense
     (`highest_version_for_brand`) is omission-resistant (reads from the tamper-proof
     KEL, not the mutable appcast). The SAD carries the per-platform artifact detail
     and is embedded per-release in the JSON appcast.
3. **Genusified KEL export** (`publish.export_kel`): stock keripy `clonePreIter` /
   `cloneEvtMsg` hardcode v1 CESR attachment count codes and emit no genus code, so
   a v2 event body framed with v1 attachments is a self-inconsistent, unparseable
   stream. `eventing.messagize(..., gvrsn=serder.pvrsn, genusify=(sn==0))` prepends
   the genus-version count code, which auto-raises the verifier's
   `Parser(version=Vrsn_1_0)` to v2 — so `update/kel_replay.replay_kel` replays a v2
   publisher KEL **unchanged**.
4. **Verifier** (`update/kel_replay.extract_release_seal`, `update/verify._verify_sad_against_anchor`):
   read the `{d, brand, ver}` digest seal from the KEL, resolve the SAD from the
   appcast, assert `Saider.saidify(SAD)["d"] == seal["d"]`, and bind the per-platform
   sha256. Brand-aware freeze-defense preserved.

## Notes
- The brand-aware verify semantics
  (`docs/superpowers/specs/2026-07-02-multibrand-verify-brand-aware.md`) are preserved:
  seal carries `brand`; version-based-per-brand stale defense + per-(brand,platform)
  artifact-digest binding.
- The v0.2.20 built artifacts already exist in S3; re-run the publish
  (`/tmp/promote-0.2.20/promote.sh`) after the v2 re-inception — no rebuild.
- Registered as ✅ ON-V2 in `docs/keri-v2-hold-registry.md`, with the note that
  stock keripy has no v2 clone-export (`kli export` is clonePreIter-only) — Locksmith
  genusifies its own export.

## Original repro (v1 keystore + v2 base)
```
LOCKSMITH_PUBLISHER_BRAN=<bran> LOCKSMITH_BRAND=locksmith \
  .venv/bin/locksmith-publisher anchor --name publisher --base publisher --version 0.2.20 \
  --macos /tmp/promote-0.2.20/Locksmith-0.2.20.dmg --windows /tmp/promote-0.2.20/Locksmith-0.2.20.msi --out-dir /tmp/x
```
→ `SerializeError: Invalid value while serializing`. Fixed by re-incepting the
publisher at v2 (fresh v2 KEL).
