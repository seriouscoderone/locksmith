# Release seal not v2-CESR-serializable — publisher anchor fails on the v2 base

**Filed:** 2026-07-09 (blocks the v0.2.20 *publish*; build is fine)
**Domain:** publisher ↔ verifier seal contract × KERI-v2 (full-CESR) serialization
**Severity:** release-blocking for publish (the in-app KERI gate has nothing to verify without a KEL anchor)

## Symptom
`locksmith-publisher anchor` fails at `kli interact`:
```
kli interact --name publisher --alias publisher --base publisher --receipt-endpoint
  --data {"release": {"brand": "locksmith", "v": "0.2.20", "artifacts":
          [{"platform": "macos", "sha256": "…"}, {"platform": "windows", "sha256": "…"}]}}
  failed (255):
ERR: Invalid value while serializing
```
Raised at `keri/core/mapping.py:611` → `SerializeError("Invalid value while serializing")` (from an `InvalidValueError` in the v2 field-map serializer).

## Root cause
The release seal is a **v1-style free-form nested dict** (`tools/publisher/src/locksmith_publisher/seal.py`, `build_release_seal`):
```python
{"release": {"brand": brand, "v": version,
             "artifacts": [{"platform": plat, "sha256": hex}, ...]}}
```
Under the **v2 full-CESR** base, the ixn `a` (anchor/seal) field is serialized via `keri/core/mapping.py`. A value that is a **nested dict / list-of-dicts** is not CESR-serializable there → `Invalid value while serializing`. This is not a kli-version problem: both the venv `kli` and the homebrew `kli` resolve keri from `~/code/keripy/src` (the v2 fork `6ab5019e`), so both reject it. 0.2.18/0.2.19 anchored the same shape only because they published on the pre-v2 keri.

## Scope of the fix (publisher AND verifier — they're one contract)
1. **Publisher** (`seal.py` `build_release_seal`, `publish.py` `anchor_release`): emit a seal value that v2-CESR can serialize. Options to evaluate:
   - Anchor a **SAID/digest** of the release payload (publish the full payload separately, anchor only its digest) — most v2-native.
   - Or JSON-encode the release payload into a **single scalar string** value the mapping serializer accepts, and parse it back on read.
   - Or use the v1-serialization hold the migration already applies elsewhere (`feat/keri-v2-migration` pinned hab inception + exns to v1 — an anchor-event v1-hold may be the smallest change).
2. **Verifier** (`src/locksmith/update/kel_replay.py` `extract_release_seal`, and `verify.py` which reads `seal["release"]["v"|"brand"|"artifacts"]`): read whatever new shape the publisher emits. This is the brand-aware verifier from the 2026-07-03 work — keep `brand`/version/artifact-digest binding intact.
3. Add a round-trip test on the **v2 base**: `build_release_seal(...)` → anchor via `kli interact` (or the v2 serializer directly) → `extract_release_seal(...)` returns the same version/brand/artifact digests. This is the test that was missing (the publisher runs off-CI and wasn't re-tested against v2).

## Constraints / notes
- Must preserve the brand-aware verify semantics (per `docs/superpowers/specs/2026-07-02-multibrand-verify-brand-aware.md`): seal carries `brand`; verifier does version-based-per-brand stale defense + per-(brand,platform) artifact-digest binding.
- The v0.2.20 built artifacts already exist in S3 (`releases/0.2.20/…`, `usurance/releases/0.2.20/…`) — once the seal is v2-serializable, re-run the publish (`/tmp/promote-0.2.20/promote.sh`); no rebuild needed. The publisher KEL is unchanged (interact failed before writing).
- Decide who owns this: it's the publisher+verifier contract (release-tooling) intersecting v2-CESR serialization (the migration). Coordinate.

## Repro
```
LOCKSMITH_PUBLISHER_BRAN=<bran> LOCKSMITH_BRAND=locksmith \
  .venv/bin/locksmith-publisher anchor --name publisher --base publisher --version 0.2.20 \
  --macos /tmp/promote-0.2.20/Locksmith-0.2.20.dmg --windows /tmp/promote-0.2.20/Locksmith-0.2.20.msi --out-dir /tmp/x
```
→ `SerializeError: Invalid value while serializing`.
