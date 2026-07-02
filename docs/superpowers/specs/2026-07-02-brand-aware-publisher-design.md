# Brand-Aware Release Publisher — Design

**Date:** 2026-07-02
**Status:** Approved (brainstorm) — pending spec review → writing-plans
**Branch:** `feat/white-label-logos` (worktree `~/code/locksmith-branding`)

## Problem

Phase-3 CI now cuts **both** brands from one signed tag and uploads each brand's artifacts to a brand-namespaced S3 prefix (`releases/…` for locksmith, `usurance/releases/…` for usurance — CI `s3prefix` step). But the **off-CI release publisher** (`tools/publisher/`) is not brand-aware: it hardcodes the `releases/` S3 path in six places and a `locksmith.app` release-notes URL, so a `LOCKSMITH_BRAND=usurance locksmith-publisher …` run would enumerate, anchor, and build the appcast against `releases/…` and **never find** the Usurance artifacts at `usurance/releases/…`. This is the last gap before the first Usurance production cut (flagged by the Phase-3 final review). Locksmith's path must remain byte-identical (no regression to the live pipeline).

## Decision: the two per-brand values are **brand identity**

Locksmith and Usurance share **one** publisher (same keri.host AID, KEL, witnesses, S3 bucket, CDN). The only values that differ per brand are:
- **artifact prefix** — `Locksmith` vs `Usurance` (already in `brand.toml [identity].artifact_prefix`)
- **S3 release prefix** — `releases` vs `usurance/releases`

These are treated as **brand identity**, resolved from the active brand. `deploy_config.json` stays **one shared infra file** (bucket / CDN / KEL / witnesses / toad); it is NOT split per brand, and the publisher stops depending on it for `artifact_prefix`. (Rejected: per-brand `deploy_config` — would duplicate brand identity into infra config and add a per-brand secret, for no benefit while the publisher/infra is shared.)

## Architecture: `brandlib` is the single brand-identity source

`packaging/brandlib.py` already reads `brand.toml` and backs the `brandlib id <field>` CLI (built in Phase-3 Task 1 for the shell/PowerShell build scripts). It becomes the **one** place that answers "what is this brand's artifact prefix / S3 release prefix / website?" — and **both** CI and the publisher ask it. One implementation, no drift.

```
LOCKSMITH_BRAND ─▶ brandlib.id ─┬─▶ artifact_prefix  (Usurance)
                                ├─▶ release_prefix    (usurance/releases)
                                └─▶ website           (https://usurance.com)
        │                                   │
   CI s3prefix step                    publisher (shell-out)
   (release.ci.yml)                    (tools/publisher/)
```

## Components

### 1. `packaging/brandlib.py` — extend the `id` resolver
Add two computed fields to `brandlib id <field>` (alongside the existing `display_name|artifact_prefix|bundle_id|data_dir|id`):
- **`release_prefix`** (derived, not a `brand.toml` field): `"releases"` when `brand.id == "locksmith"`, else `f"{brand.id}/releases"`. This is exactly CI Task-5's current rule, relocated to brandlib as the source. No new `brand.toml` field (YAGNI); a future brand needing a bespoke S3 layout can add an explicit field then.
- **`website`** (from `brand.toml [urls].website`): needed to brand-derive the release-notes URL.

Unknown field still exits 2 (existing contract).

### 2. `.github/workflows/release.ci.yml` — CI folds into brandlib
Replace the Task-5 `s3prefix` bash `case` statement (both jobs) with `python -m brandlib id release_prefix`. CI and the publisher now compute the prefix from the same code. Artifact filenames (Task-4 `prefix` step) and everything else are unchanged. Locksmith still resolves `releases`, so its S3 keys stay byte-identical.

### 3. `tools/publisher/` — become brand-aware
The publisher already runs from the repo (it locates `src/locksmith/release/`), so `packaging/` is present. Add a small helper (e.g. `brand.py` or a function in `cli.py`) that shells out to brandlib — mirroring how the build scripts call it — and returns a field for the active brand:

```python
# repo_root is already located by the publisher (for src/locksmith/release/)
subprocess.run([sys.executable, "-m", "brandlib", "id", field],
               cwd=repo_root / "packaging", capture_output=True, text=True).stdout.strip()
```

Then:
- **Resolve `artifact_prefix` + `release_prefix` (+ `website`) from the active brand**, not from `deploy_config`/hardcode. `_DEFAULT_ARTIFACT_PREFIX` stays only as a last-resort fallback if brandlib is somehow unavailable.
- **Replace the six hardcoded `releases/`** with `{release_prefix}/`:
  - `s3_client.py:113` — `paginate(… Prefix=f"{release_prefix}/")`
  - `appcast.py:182` — anchor read key `f"{release_prefix}/{v}/release-anchor-{v}.cesr"`
  - `appcast.py:222/226` — appcast artifact + anchor URLs `f"{cdn_base}/{release_prefix}/{v}/…"`
  - `cli.py:67` (`_artifact_url`) and `cli.py:296` (anchored artifact key) — `f"…/{release_prefix}/{version}/{prefix}-{version}.{ext}"`
- **Brand-derive the release-notes URL** (`appcast.py:229`): `f"{website}/releases/{v}"` (was hardcoded `https://locksmith.app/releases/{v}`; locksmith's website is `https://locksmith.app`, so its value is unchanged).

### 4. `deploy_config.json` — unchanged shape, narrower role
Remains shared infra (bucket / CDN / KEL / witnesses / toad). `artifact_prefix` in the config becomes vestigial (publisher no longer reads it); leave the key in the example for now, or drop it — decided at plan time (low stakes).

## Data flow (usurance publish)

1. Operator: `LOCKSMITH_BRAND=usurance locksmith-publisher anchor … / publish …` from the repo.
2. Publisher resolves `release_prefix=usurance/releases`, `artifact_prefix=Usurance`, `website=https://usurance.com` via brandlib.
3. `enumerate` / anchor-read / appcast-build / `_artifact_url` all use `usurance/releases/…` — matching where CI uploaded the DMG/MSI + anchor.
4. Shared infra (bucket `releases.keri.host`, publisher KEL, witnesses) comes from the shared `deploy_config`.

## Error handling
- brandlib `id release_prefix` for an unknown/missing brand → falls back to default brand (`active_brand_id` default `locksmith` → `releases`), preserving today's behavior. Unknown *field* still exits 2.
- Publisher: if the brandlib shell-out fails (non-zero / empty), fail loudly with a clear message (don't silently fall back to `releases/` for a non-locksmith brand — that would upload/anchor to the wrong place). `artifact_prefix` may fall back to `_DEFAULT_ARTIFACT_PREFIX` only for locksmith.

## Testing
- **brandlib:** extend `tests/unit/branding/test_brandlib_identity_cli.py` — assert `release_prefix` (`locksmith`→`releases`, `usurance`→`usurance/releases`) and `website`.
- **Publisher** (run from `tools/publisher/`): the string-builders are the target —
  - `test_artifact_url.py` — `_artifact_url` includes the brand prefix.
  - `test_appcast_build.py` / `test_appcast_xml.py` — appcast URLs + anchor key use the brand prefix; release-notes URL uses the brand website.
  - `test_cli.py` — the anchored artifact key uses the brand prefix.
  Parameterize/mock the brand resolver so tests don't shell out per-assertion (inject the resolved prefix, or stub the helper).
- **Worktree caveat (CLAUDE.md):** the publisher bare-imports `locksmith.*`, which resolves to the MAIN checkout from a worktree. The new logic is brand-string construction (no new `locksmith` import), so its unit tests are validatable in isolation; full cross-tree validation is by merging to `development` and running there.
- **Locksmith regression:** a test (brandlib and/or publisher) pins that `locksmith` yields `releases` and the locksmith artifact/appcast keys are byte-identical to today.

## Constraints
- **Locksmith path byte-identical** — no regression to the live pipeline (its S3 keys, appcast URLs, and info URL are unchanged).
- **Shared publisher** — one keri.host AID/KEL/witnesses/bucket/CDN for both brands; no per-brand AID.
- **Single source of truth** — `release_prefix` lives only in brandlib; CI and publisher both call it.
- **No new `brand.toml` field** — `release_prefix` is a convention.

## Out of scope
- Per-brand `deploy_config` / per-brand publisher AID / separate infra.
- Making the in-app updater brand-aware (already done — brand.json appcast feeds).
- The pre-cut throwaway matrix dry-run (operational, recommended separately).
- Creating the actual `usurance.com/releases/<v>` release-notes page (the URL may 404 until the brand builds it; it's only the appcast "more info" link).
