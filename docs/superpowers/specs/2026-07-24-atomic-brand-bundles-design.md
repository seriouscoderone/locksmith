# Atomic runtime-resolved brand bundles — Design

**Date:** 2026-07-24
**Status:** Approved (brainstorm) — ready for implementation plan
**Repo:** locksmith (`~/code/locksmith`, branch `development`)
**Builds on:** `docs/superpowers/specs/2026-06-23-white-label-branding-engine-design.md` (the manifest + build-time generation engine this refactor hardens). Not a publish blocker — `brand_apply` already produces correct published builds today; this is a robustness/DX refactor.
**Boundary:** vanilla-Locksmith / packaging (studio-side) work, domain-neutral. Framework code stays brand-agnostic; all brand specifics ride in the per-brand bundle + EGF (owner law, HOA domain-neutrality).

## Problem

A brand is applied by `scripts/brand_apply.py --brand <x>`, which today:

1. copies brand assets **over** the TRACKED `assets/custom/*` slots (icons/logos/splash),
2. rewrites the TRACKED, generated `src/locksmith/resources_rc.py` via `pyside6-rcc resources.qrc`,
3. writes gitignored `src/locksmith/release/brand.json` (runtime config subset) + packaging files (`packaging/wix/Locksmith.wxs`, `packaging/dmg/layout.json`) + stages `release/egf/`.

Logos are loaded through the compiled `:/assets/custom/*` bundle (`ui/toolbar.py:92`, `ui/home.py:52`, `ui/styles.py:76`, `ui/vaults/drawer.py:126`); there is no runtime asset resolution. This yields four concrete defects:

1. **Two brand layers with mismatched override semantics.** `brand.json` is runtime-overridable via `LOCKSMITH_BRAND_CONFIG` (`core/branding.py`), but logos are compile-time baked into `resources_rc.py`. This structurally allows a partial "Frankenstein" brand — **verified live**: launching the usurance brand via `LOCKSMITH_BRAND_CONFIG` after a `git checkout` (default `resources_rc`) produced a window titled "Usurance" showing the Locksmith logo. A brand should be atomic.
2. **`brand_apply` mutates version-controlled files in place** (`assets/custom/*`, `packaging/wix/Locksmith.wxs`, `packaging/dmg/layout.json`). Applying a brand dirties the working tree, forces `git checkout -- .` between brands, blocks parallel brand builds, and is the root of the known "no-env launch boots the wrong brand" gotcha (`release/brand.json` overwritten — documented across HOA #2/#4).
3. **A generated blob is tracked in git** — `src/locksmith/resources_rc.py` is compiled `pyside6-rcc` output (~123k lines) under version control; its committed state is just "whichever brand ran last," and every brand build produces a spurious diff. Its git history is pure branding churn.
4. **Silent-wrong-logo failure mode** — if `pyside6-rcc` isn't found, `brand_apply._recompile_resources` prints a WARNING and continues with STALE logos, yielding a runnable-but-mis-branded app.

## Goals / Non-goals

- **Goal:** a brand is a **self-contained bundle resolved at runtime**; applying/selecting a brand never modifies tracked files (working tree stays clean across brand builds).
- **Goal:** logos + config are always consistent for a given brand — no env-override path can yield a mismatched logo. One atomic override surface makes the partial-brand state (defect 1) unrepresentable.
- **Goal:** the generated resource blob is no longer tracked; builds regenerate it.
- **Goal:** a missing build tool (`pyside6-rcc`) FAILS the brand build loudly rather than shipping stale logos.
- **Goal:** the default (reference) build and the usurance white-label build both launch with correct, complete branding from their bundles, proven by an automated `.rcc`-registration test and a live windowed launch.
- **Goal:** update the living publishing/release docs to match the new model.
- **Non-goal:** runtime brand *switching* without relaunch (registration happens once at startup).
- **Non-goal:** a brand registry/marketplace; changing the `brand.json` schema or `Brand` dataclass fields; touching KERI/ACDC/EGF trust semantics.

## Locked decisions (from brainstorm)

1. **Self-contained per-brand `.rcc`** (over a layered neutral + logo-overlay): `brand_apply` builds ONE `<out>/assets.rcc` containing the full asset tree (neutral icons/fonts + that brand's logos + splash). The app registers exactly one `.rcc` at startup. One brand = one resource = atomic. Bundle size ~1–2 MB (gitignored). No call-site changes.
2. **Fix the packaging-file mutation too** (in scope): `Locksmith.wxs` + `dmg-layout.json` render into `<out>/` from tracked `.in` templates — required to fully meet "the working tree stays clean across brand builds."
3. **Runtime `.rcc` registration** via `QResource.registerResource()` is the mechanism (validated — see §Feasibility). This preserves the single-file / frozen-app benefit of compiling into a resource while dropping the mutation + partial-brand hazard.

## Feasibility (de-risked during brainstorm)

PySide6 6.10.3. `pyside6-rcc --binary <qrc> -o out.rcc` produces a compact binary resource; `QResource.registerResource(path)` / `unregisterResource(path)` both exist. End-to-end smoke test: before registration `QImage(":/assets/custom/logo.png")` is null; after `registerResource("brandA.rcc")` it resolves brand A's bytes; after `unregisterResource` it is null again; after `registerResource("brandB.rcc")` it resolves brand B's bytes. **Consequence:** existing `:/assets/custom/*` call sites resolve from a registered `.rcc` with **zero code changes** when the brand `.rcc` uses the same prefixes/aliases. Registration is static (no `QApplication` needed); `QPixmap`/`QImage` construction needs `QApplication`.

## Architecture

```
brand_apply --brand X [--out <dir>]        (default <dir> = src/locksmith/release/ for locksmith,
                                             src/locksmith/release/<X>/ otherwise)
   ├─ generate a per-brand aliased qrc: neutral files → assets/… ;
   │     the 8 :/-accessed brand slots (splash + 7 logo SVGs) → brands/X/…
   │     (else reference default in brands/locksmith/…), preserving the
   │     _VARIANT_FALLBACK white/black-from-standard rule as alias-target selection
   ├─ pyside6-rcc --binary <qrc> → <dir>/assets.rcc          FAIL LOUD on missing rcc / null output
   ├─ brandlib.runtime_brand_json(manifest) → <dir>/brand.json
   ├─ stage <dir>/{AppIcon.icns,AppIcon.ico}                  (packaging inputs — embedded at freeze, not in the rcc)
   ├─ render <dir>/Locksmith.wxs, <dir>/dmg-layout.json      (from tracked packaging *.in templates)
   ├─ stage <dir>/egf/                                        (if brands/X/egf/ exists)
   └─ inject <dir>/{publisher_anchor,deploy_config}.json      (if present in brands/X/)
   → touches NOTHING tracked; `git status --porcelain` stays empty

runtime (branding.register_brand_resources()):
   resolve brand source dir  (LOCKSMITH_BRAND_CONFIG parent → packaged release/ → error)
   → QResource.registerResource(<dir>/assets.rcc)             FAIL LOUD if absent/unreadable
   → load_brand() reads <dir>/brand.json ; egf_local_dir() = <dir>/egf   (unchanged sibling pattern)
```

The Qt resource system is the **single atomic override surface**: logos (`:/assets/custom/*`) and config (`brand.json`) are both sourced from the same brand directory, resolved together at startup. There is no path by which config says "Usurance" while logos say "Locksmith" — the defect-1 class is eliminated by construction.

## Repo reorganization

- **`brands/locksmith/`** gains the reference logos + `SplashScreen.png` + `AppIcon.icns/.ico` (moved out of `assets/custom/`), becoming a full brand exactly like `brands/usurance/`. The default brand stops being special — its assets no longer live in a shared mutated slot.
- **`assets/`** becomes the strictly brand-**neutral** shared pool: `material-icons/`, `fonts/`, `kerifoundation/` (the KF mark stays deliberately outside `custom/` and brand-independent — keep `test_kf_icon_brand_independent`), `cloud_lock.svg`, and the neutral `custom/*.png` nav glyphs + `custom/flags/` + `custom/step-icon-*.png` + `dmgBackground.jpeg` + `connector.png`. Never mutated by any brand build.
- **`src/locksmith/resources_rc.py`** is deleted and gitignored (defect 3). Nothing imports it anymore.
- **`resources.qrc` / `scripts/generate_qrc.py`** become the neutral-asset source of truth; `brand_apply` extends the generator to emit a per-brand aliased qrc (neutral verbatim + logo-slot aliases to the brand dir).
- `.gitignore` gains the generated outputs under `src/locksmith/release/` (`assets.rcc`, `*.wxs`, `dmg-layout.json`, per-brand subdirs) alongside the existing `release/brand.json`, `release/publisher_anchor.json`, `release/deploy_config.json` entries.

Call sites are **unchanged** — the per-brand `.rcc` registers the same `:/assets/custom/SymbolLogo.svg`, `SymbolLogoWhite.svg`, `SymbolLogoBlack.svg`, `FullLogo*.svg`, `NameLogo*.svg` prefixes the logo sites already use.

## `brand_apply.py` rewrite

- Replaces "copy over tracked slots + recompile the tracked blob" with "emit a per-brand aliased qrc and compile it to `<out>/assets.rcc`." No `shutil.copyfile` over `assets/custom/*`.
- The qrc maps canonical resource paths to sources: neutral files → `assets/…`; the 8 `:/`-accessed brand slots (`splash`, `symbol_logo`, `symbol_logo_white`, `symbol_logo_black`, `name_logo`, `name_logo_black`, `full_logo`, `full_logo_black`) → `brands/X/<file>` when present, else the reference default from `brands/locksmith/`. `_VARIANT_FALLBACK` (white/black derived from the standard mark when a brand omits them) is preserved as which source file an alias points at. The two `app_icon_icns`/`app_icon_ico` slots are **staged as files** into `<out>/` (embedded into the `.app`/`.exe` at freeze time and referenced by the installer) — they are never accessed via `:/`, so they are not compiled into the `.rcc`.
- Default `--out` = `src/locksmith/release/` for the locksmith brand (so a no-env `python -m locksmith.main` finds `release/brand.json` + `release/assets.rcc`, preserving today's packaged-default launch); other brands → `src/locksmith/release/<brand>/`.
- **Fail loud (defect 4):** missing `pyside6-rcc`, a null/empty `.rcc`, or a non-zero `rcc` exit → the build exits non-zero with a clear message. The old "WARNING + continue with stale logos" branch is removed.
- Packaging outputs render into `<out>/` from the tracked `.in` templates — never over `packaging/wix/Locksmith.wxs` or `packaging/dmg/layout.json` (defect 2). Build scripts (`packaging/build-macos.sh`, `build-windows.ps1`) read the rendered files from `<out>/`; the brand-aware publisher path is updated to match.
- `--check` (dry-run) reports intended outputs and writes nothing (preserved).

## Runtime registration (`core/branding.py` + `main.py`)

- New `branding.register_brand_resources()`: resolves the brand source dir (same order as `load_brand()` — `$LOCKSMITH_BRAND_CONFIG` parent, then packaged `release/`), then `QResource.registerResource(<dir>/assets.rcc)`. **Raises loudly** if the `.rcc` is absent or unreadable — the runtime counterpart to defect 1 (no silent fallback to a mismatched baked-in logo).
- `main.py:121`'s static `from locksmith import resources_rc` is replaced by a `register_brand_resources()` call that runs **before** the first `:/` access (`set_global_styles` at `main.py:212`). A single registration chokepoint keeps every UI entry path covered.
- **Splash** moves into the bundle: `_make_splash()` loads `QPixmap(":/assets/custom/SplashScreen.png")` after registration (splash is created after `QApplication` at `main.py:211`, so ordering holds) instead of the `_asset_root()/assets/custom/` disk path — making the splash atomic with the brand.
- Runtime **window icon** (`ui/styles.py:62-76`) uses `:/assets/custom/SymbolLogo.svg`; the `.icns/.ico` app-**bundle** icon (dock/taskbar, embedded at freeze time) stays a packaging output in `<out>/`.
- **Frozen builds** bundle `release/assets.rcc` + `release/brand.json` (+ `egf/`) and drop the now-redundant loose `assets/` tree from the PyInstaller specs; `register_brand_resources()` resolves the packaged `release/` dir when frozen.

## Error handling / failure modes

| Failure | Old behavior | New behavior |
|---|---|---|
| `pyside6-rcc` missing at build | WARNING, ships stale logos | **Build fails, non-zero exit** |
| `rcc` produces null/empty output | (silent) | **Build fails, non-zero exit** |
| `.rcc` missing/unreadable at launch | (N/A — baked in) | **Startup raises with a clear message** |
| Partial brand (config without matching logos) | **Possible** (verified live) | **Unrepresentable** — one source for both |
| Brand build dirties tracked files | Always | **Never** — outputs are gitignored |

## Testing (Principle VII — 100% coverage, AI-runnable, headless)

Run headless + focused: `QT_QPA_PLATFORM=offscreen`, `--import-mode=importlib`. Never the full suite / `tests/peer` / subprocess-spawning suites (they crash macOS). After entry-point edits, `pip install -e . --no-deps`.

- **Atomicity test (headline "Done when"):** build the usurance bundle, register its `.rcc` in-process, assert `QResource`/`QFile(":/assets/custom/SymbolLogo.svg")` bytes == `brands/usurance/SymbolLogo.svg` **and** `load_brand().display_name == "Usurance"` — logo and config proven to come from the same source. Repeat for locksmith. A negative test asserts that with only `LOCKSMITH_BRAND_CONFIG` set (usurance `brand.json`) and its sibling `assets.rcc`, no path yields a Locksmith logo — the live bug can no longer reproduce.
- **Clean-tree test:** `brand_apply --brand usurance` then assert `git status --porcelain` over tracked paths is empty.
- **Fail-loud tests:** `pyside6-rcc` absent (PATH stubbed) → build exits non-zero; missing `.rcc` at launch → `register_brand_resources()` raises.
- **Migrate existing branding tests** (`tests/unit/branding/`, `tests/packaging/`, `tests/core/test_usurance_*`): `test_brand_apply` and `test_usurance_brand_apply` assert the new `<out>/assets.rcc` + no-tracked-mutation contract; the "render == committed" packaging test (`test_render_packaging.py`) becomes "render == golden fixture" since the rendered `wxs` is no longer tracked. Keep `test_kf_icon_brand_independent`, `test_usurance_egf_bundle` (EGF SAID re-derivation).
- **Live verification** per the HOA #4 runbook harness (`ugard docs/demos/2026-07-21-hoa-multi-role-live-demo.md`): build locksmith + usurance bundles, launch each windowed (per-app `LOCKSMITH_CONTROL_SOCKET`, fresh `HOME`, `LOCKSMITH_BRAND_CONFIG=<dir>/brand.json`), confirm complete correct branding (title + toolbar/home/drawer favicon + splash) via the `ui_tester` dev-control socket.

## Docs to update

- `docs/developer-guide.rst:26-32` and `README.md:6` — replace the manual `pyside6-rcc resources.qrc -o resources_rc.py; mv …` setup with `python scripts/brand_apply.py --brand locksmith` as the one-time resource-build step (produces `release/assets.rcc` + `release/brand.json`).
- `README.md:48-77` — rewrite the white-label build section for the `release/<brand>/` bundle model (stage the brand → per-platform packaging reads the bundle from `<out>/`).
- ugard `docs/demos/2026-07-21-hoa-multi-role-live-demo.md` — **delete the obsolete GOTCHA #2 `cp`+`rm` dance**; update launch commands to point `LOCKSMITH_BRAND_CONFIG` at `release/<brand>/brand.json` (with `assets.rcc` as its sibling), and note the admin runs the default bundle (`src/locksmith/release/`) without env.
- `CLAUDE.md` build/brand notes as needed.

## Migration / rollout

1. Move reference logos/splash/app-icons `assets/custom/` → `brands/locksmith/`; trim `assets/custom/` to neutral glyphs.
2. Land the `brand_apply` rewrite + `branding.register_brand_resources()` + `main.py`/`styles.py` boot changes together (they are interdependent — the app cannot boot without a `.rcc` once `resources_rc.py` is removed).
3. Delete + gitignore `resources_rc.py`; add a session-scoped pytest fixture (or `make resources`) that builds the default locksmith bundle once so tests importing resources still resolve `:/…`.
4. Update PyInstaller specs, build scripts, brand-aware publisher.
5. Update docs. Verify locksmith + usurance live launches.

## Out of scope / noted

`scripts/` has both `check-brand-complete.py` and a near-empty `check_brand_complete.py` (hyphen vs underscore) — flagged, not touched here.
