# Brand-Aware Update Verification (multi-brand shared publisher KEL)

**Date:** 2026-07-02
**Status:** Design approved; ready for implementation plan.

## Problem

The in-app update verifier (`src/locksmith/update/verify.py`) decides whether a
release is "current" by **KEL position**: the appcast's anchor event must be the
**tip** of the publisher KEL, else it raises `StaleAppcastError`
(`verify.py:166–197`, the stale/downgrade defense). This assumes **one monotonic
release line per publisher KEL**.

The white-label model publishes **both brands into ONE shared publisher AID/KEL**
(`EHjWPRGoY9PV_tjNUJ7_XgwXLWg77fDm3BSGHd3lDFhD`). Each `locksmith-publisher anchor`
adds one `ixn`. On the v0.2.18 cut: Locksmith → sn=12, Usurance → sn=13. Usurance
(last-anchored) is the tip and verifies; **Locksmith (sn=12) fails** as
`StaleAppcastError: appcast points at sn=12 but KEL tip is sn=13`. With a shared KEL
only ONE brand can ever sit at the tip — re-ordering just flips which brand fails.

The conflict is **not** in KERI and **not** in sharing a KEL. A KEL anchor is a
permanent, self-proving commitment regardless of its position; requiring it to be the
tip is an **app-level heuristic** the verifier added. That heuristic is the bug.

**Current blast radius:** none for live users. The injected trust anchor
(`src/locksmith/release/publisher_anchor.json`) has `kel_sn=null`/`kel_said=null`, so
`verify_artifact` actually raises `TypeError` rather than enforcing — the in-app KERI
check is non-enforcing today, and Sparkle/WinSparkle deliver updates independently via
OS code-signing. The conflict bites the moment a complete (pinned sn/said) trust anchor
is injected and the check is enabled.

## Goal

Make **every brand's release pass the in-app KERI verify check** while keeping ONE
shared publisher AID. Preserve the freeze and downgrade defenses. Ship without
re-anchoring the already-published v0.2.18.

## Chosen approach (Approach B)

Keep the single shared publisher AID. Tag each release anchor with its brand, and
change the verifier's "is this current?" test from **KEL-position-based** to
**version-based, scoped to the brand**:

> A release is current for brand *B* if **no anchor for brand *B* in the KEL commits
> to a higher semantic version** than the one the appcast points at.

Rejected alternatives (recorded in memory
`project_multibrand_shared_kel_verifier_conflict.md`): **Approach A** (one combined
anchor per version covering all brands) — smaller verifier change but bakes in "brands
never diverge in version"; **separate publisher AID per brand** — zero verifier change
but a second trust root + a second inception ceremony, walking back the single-publisher
model.

### BE-KERI-NATIVE alignment

Trust and integrity remain 100% KERI: the release commitment lives in the KEL's anchored
seal, verified by KEL replay + witness-receipt (`toad`) checks. `brand` and `v` are
ordinary anchored seal data (committed and verified via the KEL). The "highest version
for this brand" comparison is a **projection/state-guard over already-verified KEL data**
— permitted app logic, not a substitute for a KERI primitive.

## Design

### 1. Release seal gains `brand`

`build_release_seal` (`tools/publisher/src/locksmith_publisher/publish.py`) currently
emits:

```json
{"release": {"v": "0.2.18", "artifacts": [{"platform": "macos", "sha256": "…"}, …]}}
```

Add the active brand id:

```json
{"release": {"brand": "usurance", "v": "0.2.18",
             "artifacts": [{"platform": "macos", "sha256": "…"}, …]}}
```

- `tools/publisher/src/locksmith_publisher/brand.py` — add `brand_id()` returning
  `_brandlib_id("id")` (the existing `python -m brandlib id id` field; e.g.
  `"locksmith"`, `"usurance"`). Fail-loud like the other resolvers.
- `publish.py` `anchor_release` / `build_release_seal` — accept the brand id and place
  it at `seal["release"]["brand"]`.
- `tools/publisher/src/locksmith_publisher/cli.py` `anchor_cmd` — resolve
  `brand.brand_id()` and pass it into `anchor_release`.
- `assert_kel_anchors_release` (publisher self-verify) is unaffected — it keys on the
  version being present in the anchored seal.

### 2. The running app names its own brand

The `Brand` dataclass (`src/locksmith/core/branding.py`) has no `id`. Add one:

- `Brand` gains `id: str` (default `"locksmith"`), `_from_dict` reads
  `doc.get("id", _DEFAULT.id)`, and `_DEFAULT.id = "locksmith"`.
- `packaging/brandlib.py` `runtime_brand_json` writes `"id"` into the generated
  `brand.json` so injected brands carry their id at runtime.

An app with no `brand.json` (baked-in default) is brand `"locksmith"`.

### 3. Verifier: version-per-brand stale defense

`src/locksmith/update/kel_replay.py` — add:

```python
def highest_version_for_brand(state: KelState, brand: str) -> str | None:
    """Highest semver among release seals in the KEL whose brand == `brand`
    (a seal with no `brand` field counts as brand 'locksmith'). None if none."""
    versions = []
    for ev in state.events:
        for s in ev.seals:
            if isinstance(s, dict) and "release" in s:
                rel = s["release"]
                if rel.get("brand", "locksmith") == brand and "v" in rel:
                    versions.append(rel["v"])
    return max(versions, key=_semver_key) if versions else None
```

`_semver_key` is the existing ordering helper in
`src/locksmith/update/appcast.py`; promote it to a shared location (or import it) so
both modules use one implementation. Numeric `x.y.z` only (releases are numeric — no
`-rc` in artifact versions).

`src/locksmith/update/verify.py` `verify_artifact`:

- Signature gains `embedded_brand: str = "locksmith"` (default = reference brand, so
  existing single-brand callers/tests are unchanged).
- **Remove** the KEL-position stale block (`verify.py:166–197`, the
  `if anchor_event.sn < state.current_sn:` branch). Replace with, after the anchor is
  located and its seal extracted:
  1. `anchor_brand = seal["release"].get("brand", "locksmith")`; if
     `anchor_brand != embedded_brand` → `SignatureError` (a cross-brand anchor was
     served to this app).
  2. Downgrade check `seal["release"]["v"] == rel.version` → else `DowngradeError`
     (unchanged behavior, kept).
  3. Freeze check: `hi = highest_version_for_brand(state, embedded_brand)`; if
     `hi is not None` and `_semver_key(hi) > _semver_key(rel.version)` →
     `StaleAppcastError(f"a newer {embedded_brand} release (v{hi}) exists; appcast "
     f"points at v{rel.version}")`.
- The anchor-present check (SAID must exist in the replayed KEL), the fetched-anchor
  SAID match, and the artifact digest binding all stay unchanged.

### 4. App gate plumbing + "half-filled anchor → off" (folded-in fix)

`src/locksmith/core/apping.py`:

- `_run_verify_artifact` passes `embedded_brand=branding.brand().id` into
  `verify_artifact`.
- The on/off decision (today: `_anchor_and_appcast_or_dark` returns `None` = off only on
  `FileNotFoundError`) is extended: when the loaded trust anchor has `kel_sn is None` or
  `kel_said is None`, also return `None` (off). This makes a half-filled anchor cleanly
  turn the check **off** instead of feeding `None` into `verify_artifact` and raising
  `TypeError`. `verify_artifact` keeps requiring complete (`int`) `embedded_kel_sn`; the
  on/off gate is the single owner of that decision.

## Error handling

| Situation | Result |
|---|---|
| `seal.brand` ≠ app brand (cross-brand anchor served) | reject — `SignatureError` |
| A higher version for this brand exists in the KEL (freeze) | reject — `StaleAppcastError` |
| Appcast version ≠ seal version | reject — `DowngradeError` (unchanged) |
| Anchor SAID not present in the replayed KEL | reject — `StaleAppcastError` (unchanged) |
| Downloaded artifact digest ≠ seal digest | reject (unchanged) |
| Trust anchor half-filled (`kel_sn`/`kel_said` null) | **off** — check skipped cleanly |
| Legacy anchor with no `brand` field | counts as brand `locksmith` |

## Testing

- **Load-bearing:** reproduce today's state — Locksmith's anchor is NOT the KEL tip
  (Usurance sn is higher) yet `verify_artifact(..., embedded_brand="locksmith")`
  **passes**, because no higher-version Locksmith anchor exists. Same fixture: Usurance
  passes.
- Genuine freeze rejected: an appcast at v0.2.17 when a v0.2.18 anchor for that brand
  exists → `StaleAppcastError`.
- Downgrade rejected (unchanged).
- Cross-brand anchor rejected: `embedded_brand="usurance"` but the pointed anchor's
  seal is `brand="locksmith"` → `SignatureError`.
- Legacy brand-less anchor counts as `locksmith`.
- `apping.py`: a half-filled anchor (null `kel_sn`/`kel_said`) yields the off path (no
  `verify_artifact` call, no `TypeError`).
- `highest_version_for_brand`: correct max per brand; brand-less → locksmith; empty → None.
- Publisher: `build_release_seal` includes `brand`; `brand.brand_id()` resolves via
  brandlib.
- Regression: existing single-brand verify tests pass unchanged (defaults hold).

## Migration / backward-compat

- **No re-anchoring of the shipped v0.2.18.** The new check is version-based, and both
  brands are at v0.2.18, so neither is "superseded by a higher version for its brand" —
  both pass once the new verifier ships.
- Legacy anchors (no `brand` field, everything ≤ sn=13) count as brand `locksmith`.
- `embedded_brand` and `Brand.id` both default to `"locksmith"`, so every existing
  single-brand caller and test is unchanged.
- Appcast format is unchanged (no brand field needed — the seal's `brand` plus the
  app's `embedded_brand` bind it, and each brand fetches its own appcast URL).

## Out of scope

- **Enabling the KERI check in production.** That requires injecting a *complete* trust
  anchor (pinned `kel_sn`/`kel_said`) via the publisher `gen-anchor` flow — an ops task,
  separate from this brand-awareness fix. This spec only ensures multi-brand releases
  *would* pass, and that a half-filled anchor stays cleanly off.
- Separate publisher AID per brand (rejected above).
- Brand-specific version divergence workflow (supported by this design, but no CI/tag
  changes are in scope — the one-tag-both-brands cut is unchanged).
