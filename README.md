# Locksmith
This is the KERI Foundation open port of the Locksmith wallet

to update assets, in locksmith directory run
```bash
python scripts/brand_apply.py --brand locksmith
```
This builds a self-contained bundle into the gitignored `src/locksmith/release/`
(`assets.rcc` + `brand.json`); no tracked file is touched. The app registers
that bundle's `assets.rcc` at startup and fails loud if it's missing.

To run the app:
```bash
python ./src/locksmith/main.py
```
## To run with local witness, watchers

### in witness-hk

```
witopnet marshal start \
  --config-dir ./scripts \
  --host 0.0.0.0 \
  --http 5632 \
  --boothost 127.0.0.1 \
  --bootport 5631
```

### in watcher-hk

```
watopnet marshal start \
  --config-dir ./scripts \
  --host 0.0.0.0 \
  --http 7632 \
  --boothost 127.0.0.1 \
  --bootport 7631
```

### in locksmith

```
python ./src/locksmith/main.py
```

KERI Foundation plugin documentation lives in
[`docs/kerifoundation-plugin.rst`](docs/kerifoundation-plugin.rst).

## HOA build mode

Building with `LOCKSMITH_BRAND=usurance` produces the Higher-Order Application base —
the wallet pages are peeled (brand-gated) and the app boots into a single default
vault + AID, retaining KERI primitives and the plugin host. The default `locksmith`
brand is unchanged.

### Building the usurance HOA (macOS / Windows)

Every white-label build is two steps: build the brand's bundle, then run the
existing per-platform packaging pipeline (which reads that bundle).

1. **Build the brand bundle** — `brand_apply --brand <x>` writes a
   self-contained bundle to `src/locksmith/release/<x>/` (the default
   `locksmith` brand instead writes flat to `src/locksmith/release/`, with no
   `<x>/` subdir): `assets.rcc` (compiled Qt resources — neutral assets +
   that brand's logos/splash), `brand.json` (runtime config, including the
   `[bootstrap]` table), `Locksmith.wxs` + `dmg-layout.json` (rendered from
   `brands/usurance/brand.toml`'s `[identity]`), `banner.png` + `dialog.png`
   (the Windows installer's WiX chrome, rendered from the brand's symbol and
   its optional `[wix]` palette), staged `AppIcon.icns`/`.ico`, the brand's own
   `license.rtf` if it ships one, and `egf/` if the brand has one. Nothing
   tracked is touched — the working tree stays clean:

   ```bash
   python scripts/brand_apply.py --brand usurance
   ```

2. **Package** — the standard macOS / Windows build scripts, unchanged; they
   resolve the app name / artifact prefix / bundle id / upgrade code, and read
   the wxs/dmg-layout/icons/assets.rcc, from the bundle built above via
   `packaging/brandlib.py` (they also re-run `brand_apply` themselves, so step
   1 is there for local inspection rather than strictly required):

   ```bash
   # macOS (produces dist/Usurance.app + dist/Usurance-<version>.dmg)
   LOCKSMITH_BRAND=usurance packaging/build-macos.sh

   # Windows (produces build/windows/Usurance-<version>.msi)
   $env:LOCKSMITH_BRAND = "usurance"; pwsh packaging/build-windows.ps1
   ```

Producing **signed** installers additionally requires the org's Apple
Developer ID application cert + notarytool profile (macOS) or a code-signing
cert (Windows) — those are CI/manual steps requiring credentials that don't
belong on a dev machine; see `.github/workflows/release.ci.yml` for the full
signed pipeline. Do not attempt to build signed installers outside of CI
without the relevant certs.

### Running a non-default brand from source

The no-env dev launch (`python ./src/locksmith/main.py`) boots the flat
`src/locksmith/release/` bundle, i.e. `locksmith`. To run a different brand
from source without packaging it, point at that brand's staged `brand.json`;
its `assets.rcc` sibling in the same directory makes the branding atomic
(config and assets always come from the same build):

```bash
LOCKSMITH_BRAND_CONFIG=src/locksmith/release/usurance/brand.json python ./src/locksmith/main.py
```
