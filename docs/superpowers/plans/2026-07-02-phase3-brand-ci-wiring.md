# Phase 3: Multi-Brand Release CI Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a single signed release tag build, sign, and upload **both** the Locksmith and Usurance brands (macOS DMG + Windows MSI), each to its own brand-namespaced S3 path — closing the deferred "Phase 3: CI wiring" gap in the white-label engine.

**Architecture:** The white-label engine (Phases 1+2) already provides `scripts/brand_apply.py` (stages assets, writes `brand.json`, recompiles `resources_rc.py`, renders `wix`/`dmg`, injects trust material) and `scripts/check-brand-complete.py` (fail-closed gate), and the PyInstaller specs already resolve the active brand via `$LOCKSMITH_BRAND` (`name=_BRAND_NAME`). Nothing invokes them from CI. This plan (1) makes the two platform **build scripts** brand-parameterized — today they hardcode `Locksmith` artifact/app names and would fail on any other brand — and (2) converts the two release jobs into a **brand matrix** (`locksmith`, `usurance`) that runs `brand_apply` + the gate before each build and brand-derives every hardcoded name/path.

**Tech Stack:** GitHub Actions (`.github/workflows/release.ci.yml`), Bash (`packaging/build-macos.sh`), PowerShell (`packaging/build-windows.ps1`), Python 3.14 (`packaging/brandlib.py`, `scripts/*.py`), PyInstaller, WiX v4, create-dmg, pytest.

## Global Constraints

- **Shared publisher.** Both brands use the same keri.host publisher AID/anchor. CI injects the one `LOCKSMITH_PUBLISHER_ANCHOR` secret for every brand; there is no per-brand AID. (Ref: user decision "use the same publisher, I am just adding a brand.")
- **One version, one tag, both brands.** A single signed `vX.Y.Z` tag (matching `pyproject.toml`, verified by `scripts/check-version.py`) builds both brands at that version. Do NOT change the tag format or `check-version.py`.
- **Committed tree stays the Locksmith baseline.** `brand_apply` is a build-time step; the repo never commits an applied/branded tree. `brand.json`, `assets/custom/*` overwrites, recompiled `resources_rc.py`, rendered `wix`/`dmg`, and injected trust files remain gitignored/regenerated.
- **No personal domains or AIDs committed.** Trust material and CDN/federation domains arrive via the existing secrets (`LOCKSMITH_PUBLISHER_ANCHOR`, `LOCKSMITH_DEPLOY_CONFIG`). Brand `[urls]` in `brands/<brand>/brand.toml` are the only committed brand endpoints and are already real (usurance.com / releases.keri.host).
- **Brand identity values are authoritative from `brands/<brand>/brand.toml`.** App name = `[brand].display_name`; artifact prefix = `[identity].artifact_prefix`; bundle id = `[identity].bundle_id`. Never hardcode `Locksmith`/`Usurance` in scripts or CI — always resolve via `brandlib`.
- **Scope boundary — publish is OUT.** This plan covers build + sign + upload of artifacts to S3. Appcast generation + KEL anchoring stay the separate off-CI `locksmith-publisher` step, run per brand with `LOCKSMITH_BRAND=<brand>` (documented in Task 6, not implemented here).

---

## File Structure

- `packaging/brandlib.py` — add a tiny CLI/print helper so shell + PowerShell can read brand identity values (app name, artifact prefix, bundle id) without duplicating TOML parsing.
- `packaging/build-macos.sh` — parameterize every `Locksmith`/`Locksmith.app`/`Locksmith-<v>.dmg`/`--volname` reference off the resolved brand.
- `packaging/build-windows.ps1` — parameterize `dist\Locksmith`, `Locksmith.exe`, `Locksmith-<v>.msi` off the resolved brand.
- `.github/workflows/release.ci.yml` — add `strategy.matrix.brand`, a `brand_apply` + anchor-into-brand-dir + `check-brand-complete` preamble, and brand-derived env/artifact/S3 names; make artifact + `upload-artifact` names brand-unique so matrix legs don't collide.
- `tests/unit/branding/test_brandlib_identity_cli.py` — new; covers the brandlib identity helper.
- `tests/packaging/test_build_scripts_brand_parameterized.py` — new; grep-style guard (mirrors `tests/packaging/test_spec_macos.py`) that the build scripts contain no hardcoded `Locksmith` artifact/app tokens and do resolve the brand.

---

### Task 1: `brandlib` identity helper for shell/PowerShell

**Files:**
- Modify: `packaging/brandlib.py`
- Test: `tests/unit/branding/test_brandlib_identity_cli.py`

**Interfaces:**
- Consumes: `brandlib.load_brand_manifest(brand_id)` (existing), `brandlib.active_brand_id()` (existing).
- Produces: a module CLI — `python -m brandlib id <field>` (run with `packaging/` on `sys.path`) that prints a single identity value for the active brand (`$LOCKSMITH_BRAND`) with no trailing decoration, exit 2 on unknown field. Fields: `display_name`, `artifact_prefix`, `bundle_id`, `data_dir`, `id`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/branding/test_brandlib_identity_cli.py`:

```python
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PKG = REPO / "packaging"


def _run(field, brand):
    return subprocess.run(
        [sys.executable, "-m", "brandlib", "id", field],
        cwd=PKG, env={"LOCKSMITH_BRAND": brand, "PATH": ""},
        capture_output=True, text=True,
    )


def test_locksmith_identity_fields():
    assert _run("display_name", "locksmith").stdout.strip() == "Locksmith"
    assert _run("artifact_prefix", "locksmith").stdout.strip() == "Locksmith"
    assert _run("bundle_id", "locksmith").stdout.strip() == "host.keri.locksmith"


def test_usurance_identity_fields():
    assert _run("display_name", "usurance").stdout.strip() == "Usurance"
    assert _run("artifact_prefix", "usurance").stdout.strip() == "Usurance"
    assert _run("bundle_id", "usurance").stdout.strip() == "com.usurance.wallet"


def test_unknown_field_exits_nonzero():
    assert _run("nope", "locksmith").returncode == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_brandlib_identity_cli.py -q --import-mode=importlib`
Expected: FAIL — `brandlib` has no `__main__` handling (`No module named brandlib.__main__` or nonzero from argparse).

- [ ] **Step 3: Implement the CLI in `packaging/brandlib.py`**

Append at the end of `packaging/brandlib.py` (uses existing `load_brand_manifest`/`active_brand_id`):

```python
def _identity_value(field: str, brand_id: str | None = None) -> str:
    m = load_brand_manifest(brand_id)
    if field == "id":
        return m["brand"]["id"]
    if field == "display_name":
        return m["brand"]["display_name"]
    ident = m.get("identity", {})
    if field not in ident:
        raise KeyError(field)
    return ident[field]


def _main(argv: list[str]) -> int:
    # Minimal CLI for shell/PowerShell: `python -m brandlib id <field>`.
    if len(argv) == 3 and argv[1] == "id":
        try:
            print(_identity_value(argv[2]))
            return 0
        except KeyError:
            print(f"unknown brand identity field: {argv[2]}", file=sys.stderr)
            return 2
    print("usage: python -m brandlib id "
          "<display_name|artifact_prefix|bundle_id|data_dir|id>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
```

Ensure `import sys` is present at the top of `brandlib.py` (add if missing).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_brandlib_identity_cli.py -q --import-mode=importlib`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add packaging/brandlib.py tests/unit/branding/test_brandlib_identity_cli.py
git commit -m "feat(branding): brandlib identity CLI for build scripts"
```

---

### Task 2: Brand-parameterize `packaging/build-macos.sh`

**Files:**
- Modify: `packaging/build-macos.sh`
- Test: `tests/packaging/test_build_scripts_brand_parameterized.py` (macOS assertions)

**Interfaces:**
- Consumes: `python -m brandlib id <field>` (Task 1); `$LOCKSMITH_BRAND` (default `locksmith`); existing env `VERSION`, `KC_PROFILE`, `DEVELOPER_ID_APP_CERT`.
- Produces: a DMG at `dist/${ARTIFACT_PREFIX}-${VERSION}.dmg` where `ARTIFACT_PREFIX` = brand `artifact_prefix`; the app bundle is `dist/${APP_NAME}.app` where `APP_NAME` = brand `display_name` (matches the spec's `name=_BRAND_NAME`).

- [ ] **Step 1: Write the failing test**

Create `tests/packaging/test_build_scripts_brand_parameterized.py`:

```python
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MACOS = REPO / "packaging" / "build-macos.sh"
WINDOWS = REPO / "packaging" / "build-windows.ps1"


def test_macos_resolves_brand_names():
    s = MACOS.read_text()
    # Resolves app name + artifact prefix from brandlib (no hardcoded product).
    assert "brandlib" in s
    assert "APP_NAME" in s and "ARTIFACT_PREFIX" in s


def test_macos_no_hardcoded_app_or_dmg_name():
    s = MACOS.read_text()
    # The literal build outputs must be brand-derived, not "Locksmith.app" /
    # "Locksmith-<v>.dmg". Comments may still say Locksmith; code must not.
    code = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))
    assert 'dist/Locksmith.app' not in code
    assert 'Locksmith-${VERSION}.dmg' not in code
    assert '"Locksmith"' not in code  # --volname etc.


def test_windows_resolves_brand_names():
    s = WINDOWS.read_text()
    assert "brandlib" in s
    assert "AppName" in s and "ArtifactPrefix" in s


def test_windows_no_hardcoded_exe_or_msi_name():
    s = WINDOWS.read_text()
    code = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))
    assert 'dist\\Locksmith' not in code
    assert 'Locksmith.exe' not in code
    assert 'Locksmith-$Version.msi' not in code
```

- [ ] **Step 2: Run test to verify it fails (macOS assertions)**

Run: `.venv/bin/python -m pytest tests/packaging/test_build_scripts_brand_parameterized.py -q --import-mode=importlib -k macos`
Expected: FAIL — script has no `APP_NAME`/`brandlib`, and contains `dist/Locksmith.app`.

- [ ] **Step 3: Implement — resolve brand names near the top of `build-macos.sh`**

After the existing env validation (near the `KC_PROFILE` check, before the PyInstaller call), insert:

```bash
# Resolve brand identity (build-time white-label). Default brand = locksmith.
export LOCKSMITH_BRAND="${LOCKSMITH_BRAND:-locksmith}"
APP_NAME="$(cd packaging && python -m brandlib id display_name)"
ARTIFACT_PREFIX="$(cd packaging && python -m brandlib id artifact_prefix)"
echo "build-macos: brand=$LOCKSMITH_BRAND app=$APP_NAME.app prefix=$ARTIFACT_PREFIX"
```

Then replace the hardcoded references (exact current tokens on the right):

- `pyinstaller ... packaging/Locksmith.macos.spec` — the spec filename stays `Locksmith.macos.spec` (it is brand-agnostic; it reads `_BRAND_NAME` internally). No change.
- `dist/Locksmith.app` → `"dist/${APP_NAME}.app"` (every occurrence: the existence check, the Sparkle copy target, the sign target, the create-dmg `--icon`/`--hide-extension`/source args, and the python `icons["Locksmith.app"]` lookups → `icons["%s.app" % APP_NAME]`; render that literal via the surrounding python by reading an env var, see below).
- `DMG_NAME="Locksmith-${VERSION}.dmg"` → `DMG_NAME="${ARTIFACT_PREFIX}-${VERSION}.dmg"`.
- `--volname "Locksmith"` → `--volname "${APP_NAME}"`.

For the embedded python block that reads `icons["Locksmith.app"]` from `layout.json`, pass the app name through the environment so the heredoc stays literal:

```bash
APP_NAME="$APP_NAME" python - <<'PY'
import json, os
name = os.environ["APP_NAME"]
layout = json.load(open("packaging/dmg/layout.json"))
icons = {i["name"]: i for i in layout["icons"]} if isinstance(layout["icons"], list) else layout["icons"]
pos = icons[f"{name}.app"]["pos"]
print(pos[0]); print(pos[1])
PY
```

> Adapt the exact extraction to the current script's parsing shape — the invariant is: look up the app icon by `"${APP_NAME}.app"`, not the literal `"Locksmith.app"`. `layout.json` is rendered by `brand_apply` (Task 4 runs it first) so its `icons[].name` already equals `${APP_NAME}.app` for the active brand.

- [ ] **Step 4: Run test to verify it passes (macOS assertions)**

Run: `.venv/bin/python -m pytest tests/packaging/test_build_scripts_brand_parameterized.py -q --import-mode=importlib -k macos`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packaging/build-macos.sh tests/packaging/test_build_scripts_brand_parameterized.py
git commit -m "build(macos): brand-parameterize app/dmg/volume names"
```

---

### Task 3: Brand-parameterize `packaging/build-windows.ps1`

**Files:**
- Modify: `packaging/build-windows.ps1`
- Test: `tests/packaging/test_build_scripts_brand_parameterized.py` (windows assertions — already written in Task 2)

**Interfaces:**
- Consumes: `python -m brandlib id <field>` (Task 1); `$env:LOCKSMITH_BRAND` (default `locksmith`); existing param `-Version`, `-Stage`.
- Produces: `dist/${AppName}/${AppName}.exe` (PyInstaller stage) and `build/windows/${ArtifactPrefix}-${Version}.msi` (WiX stage), where `AppName`/`ArtifactPrefix` are brand-derived.

- [ ] **Step 1: Run the windows assertions to confirm they fail**

Run: `.venv/bin/python -m pytest tests/packaging/test_build_scripts_brand_parameterized.py -q --import-mode=importlib -k windows`
Expected: FAIL — script has `dist\Locksmith`, `Locksmith.exe`, `Locksmith-$Version.msi`, no `AppName`.

- [ ] **Step 2: Implement — resolve brand names near the top of `build-windows.ps1`**

After `$repoRoot`/`$packagingDir` are established (before the PyInstaller stage), insert:

```powershell
# Resolve brand identity (build-time white-label). Default brand = locksmith.
if (-not $env:LOCKSMITH_BRAND) { $env:LOCKSMITH_BRAND = "locksmith" }
$AppName        = (& python -m brandlib id display_name).Trim()
$ArtifactPrefix = (& python -m brandlib id artifact_prefix).Trim()
Write-Host "[build] brand=$($env:LOCKSMITH_BRAND) app=$AppName.exe prefix=$ArtifactPrefix"
```

Note: `& python -m brandlib` must run with `packaging/` importable. Since the script runs from `$repoRoot`, invoke as `(& python -m brandlib id display_name)` after `Push-Location $packagingDir` / `Pop-Location`, or pass `-C`:

```powershell
Push-Location $packagingDir
$AppName        = (& python -m brandlib id display_name).Trim()
$ArtifactPrefix = (& python -m brandlib id artifact_prefix).Trim()
Pop-Location
```

Then replace (exact current tokens):

- `$distDir = Join-Path $repoRoot "dist\Locksmith"` → `$distDir = Join-Path $repoRoot "dist\$AppName"`.
- `& pyinstaller ... "Locksmith.windows.spec"` — spec filename unchanged (brand-agnostic). No change.
- `$exePath = Join-Path $distDir "Locksmith.exe"` → `$exePath = Join-Path $distDir "$AppName.exe"`.
- `$msiName = "Locksmith-$Version.msi"` → `$msiName = "$ArtifactPrefix-$Version.msi"`.
- The WiX invocation source `"Locksmith.wxs"` stays (that filename is fixed; `brand_apply` renders brand content into `packaging/wix/Locksmith.wxs`). No change to the filename.

- [ ] **Step 3: Run the windows assertions to verify they pass**

Run: `.venv/bin/python -m pytest tests/packaging/test_build_scripts_brand_parameterized.py -q --import-mode=importlib -k windows`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add packaging/build-windows.ps1
git commit -m "build(windows): brand-parameterize exe/msi/dist names"
```

---

### Task 4: Matrix the release workflow over brand (build + gate + apply)

**Files:**
- Modify: `.github/workflows/release.ci.yml`

**Interfaces:**
- Consumes: Tasks 1–3 (brandlib CLI + parameterized scripts); existing secrets `LOCKSMITH_PUBLISHER_ANCHOR`, `LOCKSMITH_DEPLOY_CONFIG`, all Apple/Azure/AWS secrets; `scripts/brand_apply.py`, `scripts/check-brand-complete.py`.
- Produces: for each `brand ∈ {locksmith, usurance}` × `{macos, windows}` a signed artifact uploaded to a brand-namespaced S3 key (Task 5), and (windows) a brand-unique `upload-artifact` name.

- [ ] **Step 1: Add the matrix to both jobs**

For `build-macos` and `build-windows`, add under the job key:

```yaml
    strategy:
      fail-fast: false
      matrix:
        brand: [locksmith, usurance]
```

Set the brand env for the whole job so the specs + scripts pick it up. In `build-macos.env` and `build-windows.env` add:

```yaml
      LOCKSMITH_BRAND: ${{ matrix.brand }}
```

Make `APP_ID`/`KC_PROFILE` (macOS) brand-derived rather than the literal `host.keri.locksmith` — set them in a step after checkout+install (they feed notarytool profile + entitlements). Replace the static `env: APP_ID:`/`KC_PROFILE:` with a step:

```yaml
      - name: Resolve brand identity into env
        run: |
          source /tmp/venv/bin/activate
          BID="$(cd packaging && python -m brandlib id bundle_id)"
          echo "APP_ID=$BID" >> $GITHUB_ENV
          echo "KC_PROFILE=$BID" >> $GITHUB_ENV
```

(Place it after "Install requirements" so `brandlib`/PySide deps exist. `notarytool store-credentials "$KC_PROFILE"` then uses the per-brand profile name — fine, they are independent keychain labels signed by the same Apple identity.)

- [ ] **Step 2: Add the brand preamble (apply + trust into brand dir + gate) before each build**

Insert BEFORE the build step in each job (macOS: before "Build, sign, notarize, staple DMG"; windows: before "Build .exe (PyInstaller stage)"), and REPLACE the two existing "Inject publisher trust anchor" / "Inject deploy config" steps with this brand-aware sequence:

```yaml
      - name: Inject shared trust material (both brands use the keri.host publisher)
        shell: bash
        env:
          PUBLISHER_ANCHOR: ${{ secrets.LOCKSMITH_PUBLISHER_ANCHOR }}
          DEPLOY_CONFIG: ${{ secrets.LOCKSMITH_DEPLOY_CONFIG }}
        run: |
          # check-brand-complete + brand_apply read brands/<brand>/publisher_anchor.json;
          # write the shared anchor there (gitignored) so the gate passes and
          # brand_apply copies it to release/. deploy_config goes straight to release/.
          mkdir -p "brands/${LOCKSMITH_BRAND}" src/locksmith/release
          printf '%s' "$PUBLISHER_ANCHOR" > "brands/${LOCKSMITH_BRAND}/publisher_anchor.json"
          printf '%s' "$DEPLOY_CONFIG"    > src/locksmith/release/deploy_config.json
          python -c "import json; json.load(open('src/locksmith/release/deploy_config.json')); print('deploy_config OK')" \
            || { echo '::error::LOCKSMITH_DEPLOY_CONFIG missing or invalid JSON'; exit 1; }

      - name: Apply brand (stages assets, brand.json, resources_rc, wix/dmg, trust)
        shell: bash
        run: |
          source /tmp/venv/bin/activate 2>/dev/null || true
          python scripts/brand_apply.py --brand "$LOCKSMITH_BRAND"
          python scripts/check-brand-complete.py --brand "$LOCKSMITH_BRAND"
          python scripts/check-anchor-present.py --anchor src/locksmith/release/publisher_anchor.json
```

> Rationale for the anchor-into-brand-dir move: today CI writes the anchor only to `src/locksmith/release/`. `check-brand-complete` validates `brands/<brand>/publisher_anchor.json`, and `brand_apply` copies that file into `release/`. Writing the shared secret into the (gitignored) brand dir satisfies both, uniformly, for either brand. `brands/<brand>/publisher_anchor.json` and `deploy_config.json` must already be covered by `.gitignore` (verify in Step 5).

- [ ] **Step 3: Brand-derive artifact names in build + upload steps**

- macOS build step already calls `packaging/build-macos.sh`, which now (Task 2) emits `dist/${ARTIFACT_PREFIX}-${VERSION}.dmg`. Update the upload step to compute the prefix:

```yaml
      - name: Resolve artifact prefix
        id: prefix
        shell: bash
        run: |
          source /tmp/venv/bin/activate 2>/dev/null || true
          echo "value=$(cd packaging && python -m brandlib id artifact_prefix)" >> "$GITHUB_OUTPUT"
```

Then in the macOS upload step, replace `Locksmith-${VERSION}.dmg` (both the object key and the `--file`) with `${{ steps.prefix.outputs.value }}-${VERSION}.dmg`, and use the brand-namespaced object key from Task 5.

- Windows: `packaging/build-windows.ps1` now emits `build/windows/${ArtifactPrefix}-${Version}.msi`. Add the same `prefix` step (pwsh or bash), and in "Build .msi", "Sign the MSI itself" (`files-folder: build/windows` filter `msi` is unaffected), "Upload MSI", and "Capture MSI artifact", replace `Locksmith-${VERSION}.msi` with `${{ steps.prefix.outputs.value }}-${VERSION}.msi`.

- [ ] **Step 4: Make matrix artifacts non-colliding**

The windows `Capture MSI artifact` step's `name:` must include the brand so the two matrix legs don't overwrite each other:

```yaml
        with:
          name: ${{ steps.prefix.outputs.value }}-${{ steps.set_version.outputs.version }}-msi
          path: build/windows/${{ steps.prefix.outputs.value }}-${{ steps.set_version.outputs.version }}.msi
```

- [ ] **Step 5: Verify gitignore + YAML validity (no unit test; CI is the real test)**

```bash
git check-ignore brands/usurance/publisher_anchor.json src/locksmith/release/deploy_config.json
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.ci.yml')); print('workflow YAML OK')"
```
Expected: both paths print (gitignored); YAML parses. If `brands/*/publisher_anchor.json` is NOT ignored, add `brands/*/publisher_anchor.json` and `brands/*/deploy_config.json` to `.gitignore` in this step and re-check.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/release.ci.yml .gitignore
git commit -m "ci(release): matrix both brands — apply + gate + brand-derived names"
```

---

### Task 5: Brand-namespaced S3 upload paths

**Files:**
- Modify: `.github/workflows/release.ci.yml` (upload steps only)

**Interfaces:**
- Consumes: `steps.prefix.outputs.value` (artifact prefix), `steps.set_version.outputs.version`, `matrix.brand`.
- Produces: S3 object keys that match each brand's appcast base so the (off-CI) publisher's appcast points at real objects.

**Decision to confirm with maintainer before running a real cut:** the object-key convention must match what each brand's `deploy_config.json` / appcast expects. Proposed convention (keeps Locksmith back-compatible, namespaces Usurance under its appcast root `releases.keri.host/usurance/...`):

- locksmith → `releases/${VERSION}/${PREFIX}-${VERSION}.dmg|.msi` (UNCHANGED — existing appcast keeps working).
- usurance → `usurance/releases/${VERSION}/${PREFIX}-${VERSION}.dmg|.msi`.

- [ ] **Step 1: Add a brand→S3-prefix mapping step to both jobs**

```yaml
      - name: Resolve S3 key prefix for brand
        id: s3prefix
        shell: bash
        run: |
          case "$LOCKSMITH_BRAND" in
            locksmith) echo "value=releases" >> "$GITHUB_OUTPUT" ;;
            *)         echo "value=${LOCKSMITH_BRAND}/releases" >> "$GITHUB_OUTPUT" ;;
          esac
```

- [ ] **Step 2: Use it in the upload object keys**

macOS and Windows upload steps:

```
--object-key "${{ steps.s3prefix.outputs.value }}/${VERSION}/${{ steps.prefix.outputs.value }}-${VERSION}.dmg"   # or .msi
```

- [ ] **Step 3: Verify (YAML + convention note)**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.ci.yml')); print('OK')"
```
Expected: OK. Add a comment in the workflow above the s3prefix step stating the convention must match `deploy_config.json`/appcast for each brand, and that the maintainer must confirm the usurance object base equals its appcast artifact base before the first real cut.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.ci.yml
git commit -m "ci(release): brand-namespaced S3 upload keys"
```

---

### Task 6: Document the per-brand publish step (no code)

**Files:**
- Modify: `CLAUDE.md` (Release publisher section) — one paragraph.

**Interfaces:** none (docs only).

- [ ] **Step 1: Add the publish note**

Append to the "Release publisher + update verification" section of `CLAUDE.md`:

```markdown
- **Multi-brand cuts (Phase 3).** One signed `vX.Y.Z` tag builds BOTH brands via
  the `brand` matrix in `release.ci.yml`; each brand's DMG/MSI lands under its own
  S3 prefix (`releases/…` for locksmith, `usurance/releases/…` for usurance).
  Publishing (appcast + KEL anchor) stays off-CI and is run **once per brand**:
  `LOCKSMITH_BRAND=<brand> locksmith-publisher anchor …` then `… publish …`, so
  each brand's appcast (its `[urls].appcast_*`) points at that brand's artifacts.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: multi-brand cut + per-brand publish note"
```

---

## Self-Review

**Spec coverage:**
- "Both brands per cut" → Task 4 matrix. ✅
- Build scripts fail on non-Locksmith brands → Tasks 2+3 parameterize them. ✅
- `brand_apply`/gate never invoked → Task 4 preamble. ✅
- Shared-anchor gate wrinkle → Task 4 Step 2 (anchor into `brands/<brand>/`). ✅
- Artifact/S3 collisions between matrix legs → Task 4 Step 4 + Task 5. ✅
- Publish remains off-CI, per brand → Task 6 (documented, not automated). ✅

**Type/name consistency:** the brandlib CLI field names (`display_name`, `artifact_prefix`, `bundle_id`) are used identically in Tasks 1/2/3/4. Env var is `LOCKSMITH_BRAND` throughout (matches `brandlib.active_brand_id`). Step output ids (`prefix`, `s3prefix`, `set_version`) are referenced consistently.

**Open items flagged, not silently assumed:**
- The exact Usurance S3 object base MUST equal its appcast artifact base in `deploy_config.json` (gitignored) — Task 5 requires maintainer confirmation before the first real cut.
- `check-version.py` is intentionally unchanged: one tag = one version for both brands.
- CI is the only real integration test for the workflow YAML; the pytest guards (Tasks 1–3) cover the scripts/CLI, and Task 4/5 steps include local YAML-parse + gitignore checks. A dry-run on a throwaway pre-release tag is recommended before a production cut.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-phase3-brand-ci-wiring.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
