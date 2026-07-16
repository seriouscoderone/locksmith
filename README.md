# Locksmith
This is the KERI Foundation open port of the Locksmith wallet

to update assets, in locksmith directory run
```bash
python ./scripts/generate_qrc.py; pyside6-rcc resources.qrc -o resources_rc.py; mv resources_rc.py ./src/locksmith;
```

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

Every white-label build is two steps: stage the brand, then run the existing
per-platform packaging pipeline (which reads the staged `brand.json` +
brand-parameterized `.spec`/`.wxs`/dmg-layout produced by the first step).

1. **Stage the brand** — writes `src/locksmith/release/brand.json` (including
   the `[bootstrap]` table), stages `assets/custom/`, and renders
   `packaging/wix/Locksmith.wxs` + `packaging/dmg/layout.json` from
   `brands/usurance/brand.toml`'s `[identity]`:

   ```bash
   LOCKSMITH_BRAND=usurance python scripts/brand_apply.py
   ```

2. **Package** — the standard macOS / Windows build scripts, unchanged; they
   resolve the app name / artifact prefix / bundle id / upgrade code from the
   brand staged above via `packaging/brandlib.py`:

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
