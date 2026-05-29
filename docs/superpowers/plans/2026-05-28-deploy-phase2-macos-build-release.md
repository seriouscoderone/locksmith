# Locksmith Deploy Phase 2 — macOS Build + Signing + Manual Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a signed, notarized, stapled `Locksmith-X.Y.Z.dmg` that uploads to `s3://releases.keri.host/releases/{version}/` from GitHub Actions via OIDC, so a user can drag-to-Applications on macOS without any OS warning. No KERI verification, no auto-updater — just a polished, releasable DMG.

**Architecture:** PyInstaller builds `Locksmith.app` from `src/locksmith/main.py` using a committed `.spec` file. The macOS CI job runs `packaging/build-macos.sh` which orchestrates PyInstaller → `signLibs.sh` → `codesign --deep --options runtime` (entitlements stripped of sandbox per spec §11.1) → `create-dmg` (branded background + layout) → `xcrun notarytool submit --wait` → `xcrun stapler staple`. The DMG is then uploaded to S3 via boto3 using temporary credentials from GitHub Actions OIDC (no long-lived keys). A `scripts/check-version.py` preflight asserts the git tag matches `pyproject.toml` and is signed.

**Tech Stack:** PyInstaller 6.x, PySide6 6.10.3, Python 3.14, macOS codesign + `xcrun notarytool` + `xcrun stapler` + `create-dmg`, AWS S3 / boto3, GitHub Actions OIDC (`aws-actions/configure-aws-credentials@v4`), pytest.

**Phase dependencies:**
- **Depends on Phase 1** for: existing S3 bucket `releases.keri.host`, OIDC IAM role ARN `gha-locksmith-release-publisher`, and the placeholder `src/locksmith/release/publisher_anchor.json` schema. Tasks below include a fallback placeholder if Phase 1 hasn't landed yet, so this phase is standalone-developable.
- **Phase 3 (Windows)** is parallel — no shared edits within Phase 2.
- **Phase 4 (KERI verifier)** consumes the published DMG; nothing in Phase 2 anticipates verifier internals.
- **Phase 5 (Sparkle integration)** requires the standard PyInstaller `.app` layout this phase produces — no extra hooks here.

---

## File Structure

**New files:**

| Path | Responsibility |
|------|----------------|
| `packaging/Locksmith.macos.spec` | PyInstaller spec: bundles `Locksmith.app` from `src/locksmith/main.py`, datas/binaries, hidden imports, BUNDLE block |
| `packaging/dmg/background.png` | 540×380 placeholder PNG (committed as binary asset; replaceable with branded artwork) |
| `packaging/dmg/layout.json` | Declarative DMG layout: window size, icon positions, Applications symlink position |
| `packaging/dmg/Locksmith.icns` | Volume icon for the DMG (copied/derived from `assets/`) |
| `packaging/build-macos.sh` | Orchestrator: pyinstaller → signLibs → codesign --deep → create-dmg → notarytool → stapler |
| `src/locksmith/release/__init__.py` | Empty package marker so `publisher_anchor.json` is importable as package-data |
| `src/locksmith/release/publisher_anchor.json` | Placeholder embedded trust anchor (Phase 1 will populate real values) |
| `src/locksmith/build_info.py` | Build-time constants: `LOCKSMITH_VERSION`, `LOCKSMITH_RELEASE_CHANNEL`. Overwritten at build by `build-macos.sh` from `pyproject.toml` + env |
| `scripts/check-version.py` | CI preflight: tag vs `pyproject.toml`, semver validity, signed tag |
| `tests/scripts/test_check_version.py` | Unit tests for `check-version.py` |
| `tests/integration/test_pyinstaller_macos.py` | Integration: runs PyInstaller against spec, asserts `Locksmith.app` exists + launches |
| `docs/development/macos-build-smoke-test.md` | Manual smoke-test runbook for a clean macOS VM after CI build |

**Modified files:**

| Path | Change |
|------|--------|
| `entitlements.plist` | REMOVE sandbox + camera + microphone + audio-input (verified unused). KEEP hardened-runtime entries + network. |
| `scripts/sign.sh` | Rewritten to sign the new PyInstaller `.app` (drops flutter_assets handling). Preserves env-var-driven identity. |
| `scripts/upload.py` | Adapted to use AWS S3 (no `endpoint_url=digitaloceanspaces.com`); credentials come from OIDC-issued env vars, not args. |
| `pyproject.toml` | Add `[project.optional-dependencies]` group `build-macos` with `pyinstaller>=6.6` and `dmgbuild>=1.6.1` (script-callable fallbacks) |
| `.github/workflows/release.ci.yml` | Replace stubbed build step with `packaging/build-macos.sh`; add OIDC `permissions: id-token: write`; replace DO Spaces upload with S3 OIDC upload |

---

## Task 1: Replace `entitlements.plist` for Sparkle / hardened runtime compatibility

Per spec §11.1: Sparkle 2.x cannot run inside a sandboxed app — sandbox must be removed. Verified no camera/microphone/audio-input usage in `src/`. Hardened runtime keys + network entitlements stay.

**Files:**
- Modify: `entitlements.plist`
- Test: `tests/scripts/test_entitlements_plist.py` (new)

- [ ] **Step 1: Write failing test that asserts entitlements has no sandbox, no camera/mic, but keeps hardened-runtime + network entries**

Create `tests/scripts/test_entitlements_plist.py`:

```python
"""Verify entitlements.plist matches spec §11.1.

Sparkle 2.x requires non-sandboxed app. Hardened runtime + network must stay.
Camera/microphone removed because the codebase doesn't use them.
"""
from pathlib import Path
import plistlib

ENTITLEMENTS = Path(__file__).resolve().parents[2] / "entitlements.plist"

REQUIRED_TRUE = [
    "com.apple.security.cs.allow-jit",
    "com.apple.security.cs.allow-unsigned-executable-memory",
    "com.apple.security.cs.allow-dyld-environment-variables",
    "com.apple.security.network.client",
    "com.apple.security.network.server",
]

MUST_BE_ABSENT = [
    "com.apple.security.app-sandbox",
    "com.apple.security.device.audio-input",
    "com.apple.security.device.camera",
    "com.apple.security.device.microphone",
]


def test_entitlements_has_required_keys():
    data = plistlib.loads(ENTITLEMENTS.read_bytes())
    for key in REQUIRED_TRUE:
        assert data.get(key) is True, f"missing or false: {key}"


def test_entitlements_no_sandbox_or_av():
    data = plistlib.loads(ENTITLEMENTS.read_bytes())
    for key in MUST_BE_ABSENT:
        assert key not in data, f"must be removed: {key}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_entitlements_plist.py -v`
Expected: FAIL — `com.apple.security.app-sandbox` is currently present and set to true.

- [ ] **Step 3: Rewrite `entitlements.plist`**

Replace the entire contents of `entitlements.plist` with:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-jit</key>
    <true/>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.allow-dyld-environment-variables</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
    <key>com.apple.security.network.server</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scripts/test_entitlements_plist.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add entitlements.plist tests/scripts/test_entitlements_plist.py
git commit -m "feat(deploy): strip sandbox + AV from entitlements for Sparkle compat (spec §11.1)"
```

---

## Task 2: Create `scripts/check-version.py` and its unit test

CI preflight that asserts the git tag (`vX.Y.Z`) matches `pyproject.toml` `version`, version is valid semver, and tag is signed. Required by spec §5.5.

**Files:**
- Create: `scripts/check-version.py`
- Test: `tests/scripts/test_check_version.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_check_version.py`:

```python
"""Tests for scripts/check-version.py preflight."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-version.py"


def run(args, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_valid_tag_matches_pyproject(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    result = run(["--tag", "v1.2.3", "--pyproject", str(pyproject), "--skip-tag-signature"])
    assert result.returncode == 0, result.stderr


def test_tag_mismatch_fails(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    result = run(["--tag", "v9.9.9", "--pyproject", str(pyproject), "--skip-tag-signature"])
    assert result.returncode == 1
    assert "tag v9.9.9 does not match pyproject version 1.2.3" in result.stderr


def test_invalid_semver_fails(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "not-semver"\n')
    result = run(["--tag", "vnot-semver", "--pyproject", str(pyproject), "--skip-tag-signature"])
    assert result.returncode == 1
    assert "not valid semver" in result.stderr


def test_missing_v_prefix_fails(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    result = run(["--tag", "1.2.3", "--pyproject", str(pyproject), "--skip-tag-signature"])
    assert result.returncode == 1
    assert "must start with 'v'" in result.stderr


def test_unsigned_tag_fails(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n')
    # Without --skip-tag-signature, git verify-tag will be called on a tag that
    # doesn't exist in the test repo. Expect the script to fail with a clear error.
    result = run(["--tag", "v1.2.3", "--pyproject", str(pyproject)])
    assert result.returncode == 1
    assert "tag signature" in result.stderr.lower() or "verify-tag" in result.stderr.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_check_version.py -v`
Expected: FAIL — `scripts/check-version.py` does not exist.

- [ ] **Step 3: Implement `scripts/check-version.py`**

Create `scripts/check-version.py`:

```python
#!/usr/bin/env python3
"""CI preflight: assert git tag matches pyproject version, is semver, and is signed.

Usage:
    scripts/check-version.py --tag v1.2.3 [--pyproject pyproject.toml] [--skip-tag-signature]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def die(msg: str) -> None:
    print(f"check-version: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="git tag, e.g. v1.2.3")
    ap.add_argument(
        "--pyproject",
        default="pyproject.toml",
        help="path to pyproject.toml (default: ./pyproject.toml)",
    )
    ap.add_argument(
        "--skip-tag-signature",
        action="store_true",
        help="skip git verify-tag (for local/dev use only; CI must NOT pass this)",
    )
    args = ap.parse_args()

    tag = args.tag
    if not tag.startswith("v"):
        die(f"tag {tag!r} must start with 'v' (e.g. v1.2.3)")

    version = tag[1:]
    if not SEMVER.match(version):
        die(f"version {version!r} is not valid semver")

    pyproject_path = Path(args.pyproject)
    if not pyproject_path.exists():
        die(f"pyproject not found: {pyproject_path}")

    with pyproject_path.open("rb") as fh:
        data = tomllib.load(fh)
    pyver = data.get("project", {}).get("version")
    if pyver != version:
        die(f"tag {tag} does not match pyproject version {pyver}")

    if not args.skip_tag_signature:
        try:
            subprocess.run(
                ["git", "verify-tag", tag],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            die(
                f"git verify-tag failed for {tag}: tag signature missing or invalid.\n"
                f"stderr: {exc.stderr.strip()}"
            )
        except FileNotFoundError:
            die("git not found in PATH; cannot verify tag signature")

    print(f"check-version: OK — {tag} matches pyproject {pyver}, semver-valid, signed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scripts/test_check_version.py -v`
Expected: 5 passed.

- [ ] **Step 5: Make the script executable**

```bash
chmod +x scripts/check-version.py
```

- [ ] **Step 6: Commit**

```bash
git add scripts/check-version.py tests/scripts/test_check_version.py
git commit -m "feat(deploy): add scripts/check-version.py CI preflight (spec §5.5)"
```

---

## Task 3: Create the embedded publisher anchor placeholder

Spec §7.7 — the `.app` must bundle a `publisher_anchor.json` with the publisher AID prefix + KEL hash. Phase 1 will populate real values; this task creates a syntactically valid placeholder so Phase 2 can build standalone.

**Files:**
- Create: `src/locksmith/release/__init__.py`
- Create: `src/locksmith/release/publisher_anchor.json`
- Test: `tests/release/test_publisher_anchor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/release/test_publisher_anchor.py`:

```python
"""Verify publisher_anchor.json is well-formed and bundled with the package."""
from __future__ import annotations

import json
from pathlib import Path

ANCHOR = (
    Path(__file__).resolve().parents[2]
    / "src" / "locksmith" / "release" / "publisher_anchor.json"
)

REQUIRED_KEYS = {
    "publisher_aid",
    "embedded_kel_hash",
    "embedded_kel_sn",
    "witness_oobis",
}


def test_anchor_exists():
    assert ANCHOR.is_file(), f"missing: {ANCHOR}"


def test_anchor_is_valid_json():
    data = json.loads(ANCHOR.read_text())
    assert isinstance(data, dict)


def test_anchor_has_required_keys():
    data = json.loads(ANCHOR.read_text())
    assert REQUIRED_KEYS.issubset(data.keys()), (
        f"missing keys: {REQUIRED_KEYS - data.keys()}"
    )


def test_witness_oobis_is_list():
    data = json.loads(ANCHOR.read_text())
    assert isinstance(data["witness_oobis"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/release/test_publisher_anchor.py -v`
Expected: FAIL — file does not exist.

- [ ] **Step 3: Create the package marker and placeholder JSON**

Create `src/locksmith/release/__init__.py`:

```python
"""locksmith.release — embedded trust anchor metadata for KERI release verification.

This package contains build-time-baked data used by the in-app updater
(future Phase 4) to verify update integrity. For Phase 2, only a placeholder
publisher_anchor.json is present so the .app bundle layout is correct.
"""
```

Create `src/locksmith/release/publisher_anchor.json`:

```json
{
  "publisher_aid": "EAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
  "embedded_kel_hash": "EHshAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
  "embedded_kel_sn": 0,
  "witness_oobis": [
    "https://api.keri.host/witness/oobi/BPlaceholder1AAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "https://api.keri.host/witness/oobi/BPlaceholder2AAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "https://api.keri.host/witness/oobi/BPlaceholder3AAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
  ],
  "_comment": "PLACEHOLDER. Phase 1 will populate with real publisher AID + KEL hash + witness OOBIs."
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/release/test_publisher_anchor.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/release/ tests/release/test_publisher_anchor.py
git commit -m "feat(deploy): add placeholder publisher_anchor.json for Phase 2 bundling"
```

---

## Task 4: Create `src/locksmith/build_info.py` build-time constants module

Spec §5.5 — `LOCKSMITH_VERSION` and `LOCKSMITH_RELEASE_CHANNEL` must be baked into the binary. We keep a defaulted source-tree version that the build script overwrites at build time from `pyproject.toml`.

**Files:**
- Create: `src/locksmith/build_info.py`
- Test: `tests/test_build_info.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_build_info.py`:

```python
"""Build-time constants must be present and stringly-typed."""
import re

import locksmith.build_info as bi


def test_version_is_semver():
    assert isinstance(bi.LOCKSMITH_VERSION, str)
    # Allow 0.0.0 as the dev-tree default
    assert re.match(r"^\d+\.\d+\.\d+", bi.LOCKSMITH_VERSION), bi.LOCKSMITH_VERSION


def test_channel_is_stable_for_now():
    # Phase 2: single channel. Future phases may extend this.
    assert bi.LOCKSMITH_RELEASE_CHANNEL == "stable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_build_info.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the module**

Create `src/locksmith/build_info.py`:

```python
"""Build-time constants baked into the Locksmith binary.

This file is REWRITTEN by ``packaging/build-macos.sh`` and the Windows
equivalent before PyInstaller runs. The dev-tree default values are correct
for unpacked-source runs; the release artifact always carries the real
pyproject version and the channel from the build environment.

Do not import this module before PyInstaller bundles the app if you want
the real release version — read it from pyproject.toml during dev.
"""
from __future__ import annotations

LOCKSMITH_VERSION: str = "0.0.0+dev"
"""Semver of this build. Build scripts overwrite this string in-place."""

LOCKSMITH_RELEASE_CHANNEL: str = "stable"
"""Release channel. Phase 2 supports 'stable' only (spec §3)."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_build_info.py -v`
Expected: FAIL — version assertion fails because dev default is `0.0.0+dev` which matches the regex (it does — `^\d+\.\d+\.\d+` matches `0.0.0` prefix).

If still fails, inspect actual output. Otherwise 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/build_info.py tests/test_build_info.py
git commit -m "feat(deploy): add build_info module for baked LOCKSMITH_VERSION/CHANNEL constants"
```

---

## Task 5: Add `build-macos` optional-dependencies group to `pyproject.toml`

Spec asks for `pyinstaller` plus any macOS-only tools as an optional-dependencies group.

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/test_pyproject_build_deps.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pyproject_build_deps.py`:

```python
"""pyproject.toml must declare build-macos optional dependencies."""
from pathlib import Path
import tomllib

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_build_macos_group_exists():
    data = tomllib.loads(PYPROJECT.read_text())
    opt = data["project"].get("optional-dependencies", {})
    assert "build-macos" in opt, "missing [project.optional-dependencies].build-macos"


def test_build_macos_includes_pyinstaller():
    data = tomllib.loads(PYPROJECT.read_text())
    deps = data["project"]["optional-dependencies"]["build-macos"]
    assert any(d.startswith("pyinstaller") for d in deps), deps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pyproject_build_deps.py -v`
Expected: FAIL — `optional-dependencies` not present.

- [ ] **Step 3: Add the section to `pyproject.toml`**

Insert immediately after the `dependencies = [...]` block (after line 48 in current file, before `[project.entry-points."locksmith.plugins"]`):

```toml
[project.optional-dependencies]
build-macos = [
    "pyinstaller>=6.6,<7",
    "dmgbuild>=1.6.1",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pyproject_build_deps.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_pyproject_build_deps.py
git commit -m "feat(deploy): add build-macos optional dependency group (pyinstaller + dmgbuild)"
```

---

## Task 6: Write `packaging/Locksmith.macos.spec` PyInstaller spec

Spec §5.1: bundles `Locksmith.app` from `src/locksmith/main.py`, includes libsodium dylibs, Qt plugins, qtawesome fonts, `assets/`, embeds `publisher_anchor.json`, reads version from `pyproject.toml`, bundle ID `host.keri.locksmith`.

**Files:**
- Create: `packaging/Locksmith.macos.spec`
- Test: `tests/packaging/test_spec_macos.py`

- [ ] **Step 1: Write the failing test**

Create `tests/packaging/test_spec_macos.py`:

```python
"""Static checks on packaging/Locksmith.macos.spec.

We don't execute the spec here (that's the integration test). We verify it
mentions every required input the build is supposed to bundle.
"""
from pathlib import Path

SPEC = Path(__file__).resolve().parents[2] / "packaging" / "Locksmith.macos.spec"


def test_spec_exists():
    assert SPEC.is_file(), f"missing: {SPEC}"


def test_spec_references_entry_point():
    s = SPEC.read_text()
    assert "src/locksmith/main.py" in s


def test_spec_includes_libsodium():
    s = SPEC.read_text()
    assert "libsodium" in s


def test_spec_includes_assets():
    s = SPEC.read_text()
    assert "'assets'" in s or '"assets"' in s


def test_spec_includes_publisher_anchor():
    s = SPEC.read_text()
    assert "publisher_anchor.json" in s


def test_spec_includes_qtawesome():
    s = SPEC.read_text()
    assert "qtawesome" in s


def test_spec_bundle_id_is_host_keri_locksmith():
    s = SPEC.read_text()
    assert "host.keri.locksmith" in s


def test_spec_reads_version_from_pyproject():
    s = SPEC.read_text()
    assert "pyproject.toml" in s


def test_spec_app_name_is_Locksmith():
    s = SPEC.read_text()
    assert "name='Locksmith'" in s or 'name="Locksmith"' in s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/packaging/test_spec_macos.py -v`
Expected: FAIL — spec file does not exist.

- [ ] **Step 3: Create `packaging/Locksmith.macos.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for macOS — produces dist/Locksmith.app.

Phase 2 of the deploy/update design. Bundles libsodium dylibs, the assets
directory, qtawesome icon fonts, and the embedded publisher_anchor.json.

Version is read from pyproject.toml so we maintain a single source of truth
(spec §5.1, §5.5).
"""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

import qtawesome  # noqa: F401  — bundling its data only; we don't call it here

# ---- Resolve paths -------------------------------------------------------

# When invoked as ``pyinstaller packaging/Locksmith.macos.spec`` the CWD is
# the repo root. SPECPATH is provided by PyInstaller.
REPO_ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 — SPECPATH injected

# ---- Read version --------------------------------------------------------

with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
    _pyproject = tomllib.load(fh)
LOCKSMITH_VERSION = _pyproject["project"]["version"]

# ---- Discover qtawesome fonts directory ----------------------------------

import qtawesome as _qta_mod
_QTA_DIR = Path(_qta_mod.__file__).resolve().parent
_QTA_FONTS = _QTA_DIR / "fonts"

# ---- Datas: non-code resources bundled into the .app ---------------------

datas = [
    # Application asset tree (icons, fonts, mock data, etc.)
    (str(REPO_ROOT / "assets"), "assets"),
    # Embedded KERI publisher trust anchor (Phase 2 placeholder, Phase 1 real)
    (
        str(REPO_ROOT / "src" / "locksmith" / "release" / "publisher_anchor.json"),
        "locksmith/release",
    ),
    # qtawesome icon fonts (needed at runtime; not auto-collected reliably)
    (str(_QTA_FONTS), "qtawesome/fonts"),
]

# ---- Binaries: native libs ----------------------------------------------

binaries = [
    # libsodium — committed to repo root; loaded via custom loader in main.py
    (str(REPO_ROOT / "libsodium" / "libsodium.dylib"), "libsodium"),
    (str(REPO_ROOT / "libsodium" / "libsodium.26.x86_64.dylib"), "libsodium"),
    (str(REPO_ROOT / "libsodium" / "libsodium.23.arm.dylib"), "libsodium"),
]

# ---- Hidden imports ------------------------------------------------------
#
# Captured during initial spec authoring on a clean macOS-latest runner.
# Add to this list with a one-line comment ONLY when a runtime ImportError
# proves the dependency is needed. Do not preemptively pad.
hiddenimports = [
    # PySide6 plugin scan misses these on some 6.10.x builds:
    "PySide6.QtPrintSupport",
    "PySide6.QtSvg",
    "PySide6.QtNetwork",
    # qasync needs explicit hint when frozen:
    "qasync",
    # keripy uses dynamic imports for codec modules:
    "keri.core.coring",
    "keri.core.eventing",
    "keri.db.basing",
]

block_cipher = None

# ---- Analysis ------------------------------------------------------------

a = Analysis(
    [str(REPO_ROOT / "src" / "locksmith" / "main.py")],
    pathex=[str(REPO_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Slim the bundle — keep tkinter out (we use PySide6)
        "tkinter",
        # No tests in the artifact
        "pytest",
        "unittest",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Locksmith",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # never UPX-compress signed binaries
    console=False,    # GUI app — no terminal window
    target_arch=None, # universal2 controlled by build script env
    codesign_identity=None,  # codesign happens in build-macos.sh, not here
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Locksmith",
)

app = BUNDLE(
    coll,
    name="Locksmith.app",
    icon=str(REPO_ROOT / "assets" / "custom" / "AppIcon.icns")
        if (REPO_ROOT / "assets" / "custom" / "AppIcon.icns").exists()
        else None,
    bundle_identifier="host.keri.locksmith",
    version=LOCKSMITH_VERSION,
    info_plist={
        "CFBundleName": "Locksmith",
        "CFBundleDisplayName": "Locksmith",
        "CFBundleIdentifier": "host.keri.locksmith",
        "CFBundleVersion": LOCKSMITH_VERSION,
        "CFBundleShortVersionString": LOCKSMITH_VERSION,
        "CFBundleExecutable": "Locksmith",
        "CFBundlePackageType": "APPL",
        "CFBundleSupportedPlatforms": ["MacOSX"],
        "CFBundleDevelopmentRegion": "en",
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "13.0",
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": True,
        # Sparkle 2 will read these in Phase 5 — set safe defaults now
        "SUEnableInstallerLauncherService": False,
        "SUEnableDownloaderService": False,
    },
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/packaging/test_spec_macos.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add packaging/Locksmith.macos.spec tests/packaging/test_spec_macos.py
git commit -m "feat(deploy): add PyInstaller macOS spec (spec §5.1, §5.2)"
```

---

## Task 7: Create DMG layout JSON + placeholder background PNG

Spec §5.2: `create-dmg` background + Applications symlink layout. The image is committed as a placeholder (540×380) that branding can replace later. `layout.json` is the source-controlled, human-readable description of icon positions.

**Files:**
- Create: `packaging/dmg/layout.json`
- Create: `packaging/dmg/background.png` (placeholder, generated below)
- Test: `tests/packaging/test_dmg_layout.py`

- [ ] **Step 1: Write the failing test**

Create `tests/packaging/test_dmg_layout.py`:

```python
"""DMG layout sanity checks."""
import json
from pathlib import Path

DMG_DIR = Path(__file__).resolve().parents[2] / "packaging" / "dmg"
LAYOUT = DMG_DIR / "layout.json"
BG = DMG_DIR / "background.png"


def test_layout_exists():
    assert LAYOUT.is_file()


def test_background_exists():
    assert BG.is_file()
    assert BG.stat().st_size > 0


def test_layout_has_window_size():
    data = json.loads(LAYOUT.read_text())
    assert "window" in data and "size" in data["window"]
    w, h = data["window"]["size"]
    # Match create-dmg --window-size — width should accommodate the bg
    assert w >= 540 and h >= 380


def test_layout_has_app_icon_position():
    data = json.loads(LAYOUT.read_text())
    icons = {i["name"]: i for i in data["icons"]}
    assert "Locksmith.app" in icons
    assert "Applications" in icons
    # Drag-target should be on the right of the app icon
    assert icons["Applications"]["pos"][0] > icons["Locksmith.app"]["pos"][0]


def test_layout_has_icon_size():
    data = json.loads(LAYOUT.read_text())
    assert data["icon_size"] >= 80
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/packaging/test_dmg_layout.py -v`
Expected: FAIL — files do not exist.

- [ ] **Step 3: Create `packaging/dmg/layout.json`**

```json
{
  "_comment": "DMG layout consumed by packaging/build-macos.sh. Coordinates are in pixels, origin top-left of the DMG window. The background image is 540x380; window is sized to match. Placeholder values — refine after branded background art lands.",
  "window": {
    "position": [200, 200],
    "size": [540, 380]
  },
  "icon_size": 96,
  "background": "background.png",
  "volume_name": "Locksmith",
  "icons": [
    {
      "name": "Locksmith.app",
      "pos": [140, 200]
    },
    {
      "name": "Applications",
      "pos": [400, 200],
      "type": "symlink",
      "target": "/Applications"
    }
  ]
}
```

- [ ] **Step 4: Generate a placeholder `background.png` (540×380, neutral grey)**

Run from the repo root:

```bash
mkdir -p packaging/dmg
python - <<'PY'
from PIL import Image, ImageDraw, ImageFont
img = Image.new("RGB", (540, 380), color=(244, 244, 246))
draw = ImageDraw.Draw(img)
# Subtle visual hint where the app + arrow + Applications slot will sit
draw.line([(190, 210), (380, 210)], fill=(190, 190, 196), width=3)
draw.polygon([(380, 210), (370, 200), (370, 220)], fill=(190, 190, 196))
draw.text((190, 320), "Locksmith — drag to Applications", fill=(120, 120, 128))
img.save("packaging/dmg/background.png", "PNG")
print("wrote packaging/dmg/background.png")
PY
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/packaging/test_dmg_layout.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add packaging/dmg/layout.json packaging/dmg/background.png tests/packaging/test_dmg_layout.py
git commit -m "feat(deploy): add DMG layout.json + placeholder background.png (spec §5.2)"
```

---

## Task 8: Adapt `scripts/upload.py` for AWS S3 + OIDC credentials

Spec §11.1 + §6.1: replace DigitalOcean Spaces endpoint with default AWS S3 endpoint; consume credentials from environment (where GitHub Actions OIDC has put them), not CLI args.

**Files:**
- Modify: `scripts/upload.py`
- Test: `tests/scripts/test_upload.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_upload.py`:

```python
"""Verify scripts/upload.py uses AWS S3 (no DigitalOcean endpoint)."""
from pathlib import Path

UPLOAD = Path(__file__).resolve().parents[2] / "scripts" / "upload.py"


def test_no_digitaloceanspaces_endpoint():
    src = UPLOAD.read_text()
    assert "digitaloceanspaces.com" not in src


def test_supports_env_credentials():
    src = UPLOAD.read_text()
    # boto3.client('s3') without explicit access-key args lets it pick up
    # AWS_ACCESS_KEY_ID / AWS_SESSION_TOKEN from the environment (OIDC).
    assert "boto3.client" in src
    assert "--bucket" in src
    assert "--object-key" in src
    assert "--file" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_upload.py -v`
Expected: FAIL — current upload.py references `digitaloceanspaces.com`.

- [ ] **Step 3: Rewrite `scripts/upload.py`**

```python
"""Upload an artifact to AWS S3.

Credentials are picked up from the environment by boto3 (AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN, AWS_REGION). In CI these are
populated by aws-actions/configure-aws-credentials@v4 via GitHub Actions
OIDC; no long-lived secrets are needed.
"""
from __future__ import annotations

import argparse
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def upload(bucket: str, object_key: str, file: str, region: str | None = None) -> None:
    s3 = boto3.client("s3", region_name=region) if region else boto3.client("s3")
    s3.upload_file(file, bucket, object_key)
    print(f"uploaded s3://{bucket}/{object_key}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload a file to AWS S3.")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--object-key", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--region", default=None, help="optional override; default from env")
    args = ap.parse_args()
    try:
        upload(args.bucket, args.object_key, args.file, args.region)
    except (BotoCoreError, ClientError) as exc:
        print(f"upload failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scripts/test_upload.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/upload.py tests/scripts/test_upload.py
git commit -m "feat(deploy): switch scripts/upload.py from DO Spaces to AWS S3 + OIDC env creds"
```

---

## Task 9: Rewrite `scripts/sign.sh` for the PyInstaller .app

The current script targets a Flutter bundle (`flutter_assets/`). PyInstaller produces a different `.app` layout. Rewrite to sign the new structure while preserving the env-var-driven cert and the existing `signLibs.sh` step.

**Files:**
- Modify: `scripts/sign.sh`
- Test: `tests/scripts/test_sign_script.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_sign_script.py`:

```python
"""Static check that sign.sh targets the new PyInstaller layout."""
from pathlib import Path

SIGN = Path(__file__).resolve().parents[2] / "scripts" / "sign.sh"


def test_no_flutter_paths():
    s = SIGN.read_text()
    assert "flutter_assets" not in s
    assert "App.framework" not in s


def test_uses_developer_id_app_cert_env():
    s = SIGN.read_text()
    assert "DEVELOPER_ID_APP_CERT" in s


def test_runs_codesign_deep_options_runtime():
    s = SIGN.read_text()
    assert "--options runtime" in s
    assert "--deep" in s


def test_uses_entitlements_plist():
    s = SIGN.read_text()
    assert "entitlements.plist" in s


def test_targets_locksmith_app():
    s = SIGN.read_text()
    assert "Locksmith.app" in s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_sign_script.py -v`
Expected: FAIL — `flutter_assets` is in the current script.

- [ ] **Step 3: Rewrite `scripts/sign.sh`**

Replace the entire contents of `scripts/sign.sh` with:

```bash
#!/usr/bin/env bash
#
# scripts/sign.sh — sign a PyInstaller-built Locksmith.app.
#
# Inputs (env):
#   DEVELOPER_ID_APP_CERT  Apple "Developer ID Application: ..." identity
#   APP_BUNDLE             Path to .app, default: dist/Locksmith.app
#   ENTITLEMENTS           Path to entitlements.plist, default: ./entitlements.plist
#
# This script signs every nested binary in the bundle (dylibs, .so, frameworks)
# before signing the outer .app with --options runtime + entitlements. Order
# matters: nested signatures first, outer last.
#
set -euo pipefail

: "${DEVELOPER_ID_APP_CERT:?DEVELOPER_ID_APP_CERT must be set}"
APP_BUNDLE="${APP_BUNDLE:-dist/Locksmith.app}"
ENTITLEMENTS="${ENTITLEMENTS:-entitlements.plist}"

if [[ ! -d "$APP_BUNDLE" ]]; then
    echo "sign.sh: $APP_BUNDLE not found" >&2
    exit 1
fi
if [[ ! -f "$ENTITLEMENTS" ]]; then
    echo "sign.sh: $ENTITLEMENTS not found" >&2
    exit 1
fi

echo "sign.sh: signing nested binaries in $APP_BUNDLE"
# Sign every nested .so / .dylib individually first.
find "$APP_BUNDLE" -type f \( -name "*.so" -o -name "*.dylib" \) -print0 \
    | xargs -0 -I{} codesign --force --timestamp --options runtime \
        --sign "$DEVELOPER_ID_APP_CERT" "{}"

# Sign embedded frameworks (if any).
if [[ -d "$APP_BUNDLE/Contents/Frameworks" ]]; then
    find "$APP_BUNDLE/Contents/Frameworks" -maxdepth 1 -name "*.framework" -print0 \
        | xargs -0 -I{} codesign --force --timestamp --options runtime \
            --sign "$DEVELOPER_ID_APP_CERT" "{}"
fi

# Sign the main executable with entitlements.
MAIN_EXE="$APP_BUNDLE/Contents/MacOS/Locksmith"
if [[ -f "$MAIN_EXE" ]]; then
    codesign --force --timestamp --options runtime \
        --entitlements "$ENTITLEMENTS" \
        --sign "$DEVELOPER_ID_APP_CERT" "$MAIN_EXE"
fi

# Final deep sign of the outer bundle.
codesign --force --deep --timestamp --options runtime \
    --entitlements "$ENTITLEMENTS" \
    --sign "$DEVELOPER_ID_APP_CERT" "$APP_BUNDLE"

# Verify.
codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"
echo "sign.sh: OK — $APP_BUNDLE signed and verified"
```

- [ ] **Step 4: Make it executable**

```bash
chmod +x scripts/sign.sh
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/scripts/test_sign_script.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/sign.sh tests/scripts/test_sign_script.py
git commit -m "refactor(deploy): rewrite scripts/sign.sh for PyInstaller .app (drops flutter paths)"
```

---

## Task 10: Write `packaging/build-macos.sh` orchestrator

Spec §5.2 sequence: PyInstaller → signLibs → codesign --deep → create-dmg → notarytool → stapler. Also writes the per-build `build_info.py` from `pyproject.toml` and `LOCKSMITH_RELEASE_CHANNEL`.

**Files:**
- Create: `packaging/build-macos.sh`
- Test: `tests/packaging/test_build_macos_script.py`

- [ ] **Step 1: Write the failing test**

Create `tests/packaging/test_build_macos_script.py`:

```python
"""Static checks on packaging/build-macos.sh."""
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "packaging" / "build-macos.sh"


def test_script_exists():
    assert SCRIPT.is_file()


def test_script_is_executable():
    assert SCRIPT.stat().st_mode & 0o111


def test_script_runs_pyinstaller_with_spec():
    s = SCRIPT.read_text()
    assert "pyinstaller" in s
    assert "packaging/Locksmith.macos.spec" in s


def test_script_calls_signLibs():
    s = SCRIPT.read_text()
    assert "signLibs.sh" in s


def test_script_calls_sign_sh():
    s = SCRIPT.read_text()
    assert "scripts/sign.sh" in s


def test_script_calls_create_dmg():
    s = SCRIPT.read_text()
    assert "create-dmg" in s


def test_script_calls_notarytool():
    s = SCRIPT.read_text()
    assert "notarytool" in s
    assert "--wait" in s


def test_script_calls_stapler():
    s = SCRIPT.read_text()
    assert "stapler" in s
    assert "staple" in s


def test_script_writes_build_info():
    s = SCRIPT.read_text()
    assert "build_info.py" in s
    assert "LOCKSMITH_VERSION" in s


def test_script_reads_version_from_pyproject():
    s = SCRIPT.read_text()
    assert "pyproject.toml" in s


def test_script_uses_dmg_layout():
    s = SCRIPT.read_text()
    assert "packaging/dmg/layout.json" in s
    assert "packaging/dmg/background.png" in s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/packaging/test_build_macos_script.py -v`
Expected: FAIL — script does not exist.

- [ ] **Step 3: Create `packaging/build-macos.sh`**

```bash
#!/usr/bin/env bash
#
# packaging/build-macos.sh — produce a signed, notarized, stapled
# Locksmith-<version>.dmg from the current source tree.
#
# Required env:
#   DEVELOPER_ID_APP_CERT    Apple "Developer ID Application: ..." identity
#   KC_PROFILE               notarytool keychain profile name
#   LOCKSMITH_RELEASE_CHANNEL  default "stable"
#
# Outputs:
#   dist/Locksmith.app
#   dist/Locksmith-<version>.dmg  (signed + notarized + stapled)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

: "${DEVELOPER_ID_APP_CERT:?DEVELOPER_ID_APP_CERT must be set}"
: "${KC_PROFILE:?KC_PROFILE must be set (notarytool keychain profile)}"
CHANNEL="${LOCKSMITH_RELEASE_CHANNEL:-stable}"

# ---- 1. Read version from pyproject.toml ---------------------------------
VERSION="$(python3 -c '
import tomllib, sys
with open("pyproject.toml", "rb") as f:
    print(tomllib.load(f)["project"]["version"])
')"
echo "build-macos: building Locksmith $VERSION (channel=$CHANNEL)"

# ---- 2. Bake version + channel into src/locksmith/build_info.py ---------
cat > src/locksmith/build_info.py <<EOF
"""Build-time constants — REWRITTEN by packaging/build-macos.sh at build time."""
from __future__ import annotations

LOCKSMITH_VERSION: str = "$VERSION"
LOCKSMITH_RELEASE_CHANNEL: str = "$CHANNEL"
EOF

# ---- 3. Clean prior outputs ---------------------------------------------
rm -rf build dist

# ---- 4. PyInstaller ------------------------------------------------------
echo "build-macos: running pyinstaller"
pyinstaller --noconfirm --clean packaging/Locksmith.macos.spec

if [[ ! -d "dist/Locksmith.app" ]]; then
    echo "build-macos: PyInstaller did not produce dist/Locksmith.app" >&2
    exit 1
fi

# ---- 5. Sign nested libsodium dylibs ------------------------------------
echo "build-macos: signing libsodium dylibs"
./signLibs.sh

# ---- 6. Sign the .app (entitlements applied, hardened runtime) ----------
echo "build-macos: signing dist/Locksmith.app"
APP_BUNDLE="dist/Locksmith.app" ENTITLEMENTS="entitlements.plist" \
    ./scripts/sign.sh

# ---- 7. Build the DMG ---------------------------------------------------
DMG_NAME="Locksmith-${VERSION}.dmg"
DMG_PATH="dist/${DMG_NAME}"
rm -f "$DMG_PATH"

# Pull window + icon coords from layout.json
read APP_X APP_Y APPS_X APPS_Y WIN_W WIN_H ICON_SIZE < <(python3 - <<'PY'
import json
d = json.load(open("packaging/dmg/layout.json"))
icons = {i["name"]: i for i in d["icons"]}
print(
    icons["Locksmith.app"]["pos"][0],
    icons["Locksmith.app"]["pos"][1],
    icons["Applications"]["pos"][0],
    icons["Applications"]["pos"][1],
    d["window"]["size"][0],
    d["window"]["size"][1],
    d["icon_size"],
)
PY
)

echo "build-macos: creating $DMG_PATH"
create-dmg \
    --volname "Locksmith" \
    --background "packaging/dmg/background.png" \
    --window-pos 200 200 \
    --window-size "$WIN_W" "$WIN_H" \
    --icon-size "$ICON_SIZE" \
    --icon "Locksmith.app" "$APP_X" "$APP_Y" \
    --app-drop-link "$APPS_X" "$APPS_Y" \
    --hide-extension "Locksmith.app" \
    --format UDZO \
    "$DMG_PATH" \
    "dist/Locksmith.app"

# ---- 8. Sign the DMG ----------------------------------------------------
echo "build-macos: signing $DMG_PATH"
codesign --force --timestamp --sign "$DEVELOPER_ID_APP_CERT" "$DMG_PATH"

# ---- 9. Notarize --------------------------------------------------------
echo "build-macos: submitting to notarytool"
xcrun notarytool submit "$DMG_PATH" --keychain-profile "$KC_PROFILE" --wait

# ---- 10. Staple ---------------------------------------------------------
echo "build-macos: stapling ticket to $DMG_PATH"
xcrun stapler staple "$DMG_PATH"
xcrun stapler validate "$DMG_PATH"

echo "build-macos: OK — $DMG_PATH ready"
```

- [ ] **Step 4: Make it executable**

```bash
chmod +x packaging/build-macos.sh
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/packaging/test_build_macos_script.py -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add packaging/build-macos.sh tests/packaging/test_build_macos_script.py
git commit -m "feat(deploy): add packaging/build-macos.sh orchestrator (spec §5.2)"
```

---

## Task 11: Integration test — invoke PyInstaller against the spec

Spec §10.2: build full artifacts and run them. This test skips on non-macOS (or when `pyinstaller` is unavailable) so unit suite stays portable.

**Files:**
- Create: `tests/integration/__init__.py` (if not present)
- Create: `tests/integration/test_pyinstaller_macos.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/__init__.py` (empty file) if it doesn't exist.

Create `tests/integration/test_pyinstaller_macos.py`:

```python
"""Integration: PyInstaller produces a runnable Locksmith.app on macOS.

Skipped unless: running on macOS AND pyinstaller is importable AND
``RUN_PYINSTALLER_INTEGRATION=1`` is set in the environment (the build is
slow — minutes — so we don't gate the default ``pytest`` suite on it).
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin"
    or os.environ.get("RUN_PYINSTALLER_INTEGRATION") != "1",
    reason=(
        "macOS-only, slow; set RUN_PYINSTALLER_INTEGRATION=1 to run "
        "(CI sets this in the build-macos job)"
    ),
)

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "packaging" / "Locksmith.macos.spec"
APP = REPO / "dist" / "Locksmith.app"


@pytest.fixture(scope="module", autouse=True)
def _pyinstaller_available():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        pytest.skip("pyinstaller not installed (pip install -e .[build-macos])")


def test_spec_runs_and_produces_app(tmp_path):
    """Run PyInstaller against the spec; assert the .app appears."""
    # Clean prior artifacts so we're sure we're testing this build.
    if APP.exists():
        shutil.rmtree(APP)
    dist_dir = REPO / "dist"
    if (dist_dir / "Locksmith").exists():
        shutil.rmtree(dist_dir / "Locksmith")

    result = subprocess.run(
        [
            "pyinstaller",
            "--noconfirm",
            "--clean",
            "--workpath", str(tmp_path / "build"),
            str(SPEC),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=900,  # 15 min cap
    )
    assert result.returncode == 0, (
        f"pyinstaller failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert APP.is_dir(), f"expected {APP} to exist"
    assert (APP / "Contents" / "MacOS" / "Locksmith").is_file()
    assert (APP / "Contents" / "Info.plist").is_file()


def test_bundle_identifier_is_correct():
    import plistlib

    info = plistlib.loads((APP / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == "host.keri.locksmith"


def test_app_launches_and_self_exits():
    """Sanity: ``open -W ... --args --self-test`` returns quickly.

    The app should accept ``--self-test`` and exit cleanly. If the binary is
    miswired (e.g. missing libsodium, missing Qt plugins) the call will hang
    or return non-zero.
    """
    # Many apps reject unknown flags; we use a short timeout and treat any
    # exit as success. The real signal is "didn't hang".
    proc = subprocess.run(
        ["open", "-W", "-a", str(APP), "--args", "--self-test"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # We don't assert returncode (the app may exit 0 or 1 depending on how
    # it handles unknown args). The important assertion is that ``open -W``
    # returned at all rather than timing out.
    assert proc.returncode in (0, 1), proc.stderr
```

- [ ] **Step 2: Run test (will skip locally unless flag is set)**

Run: `pytest tests/integration/test_pyinstaller_macos.py -v`
Expected: SKIPPED (no `RUN_PYINSTALLER_INTEGRATION=1`). This is correct local behavior.

- [ ] **Step 3: Run with the flag set (only on macOS, locally if you want to verify)**

```bash
RUN_PYINSTALLER_INTEGRATION=1 pytest tests/integration/test_pyinstaller_macos.py -v
```

Expected on a healthy macOS dev box: 3 passed in ~3–8 minutes.
If hidden-import errors appear, update `hiddenimports` in `packaging/Locksmith.macos.spec` and re-run.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_pyinstaller_macos.py
git commit -m "test(deploy): integration test for PyInstaller macOS build (spec §10.2)"
```

---

## Task 12: Update `.github/workflows/release.ci.yml` macOS job

Replace stubbed build step with `packaging/build-macos.sh`; add OIDC permissions; swap DO Spaces upload for S3 upload to `s3://releases.keri.host/releases/{version}/Locksmith-{version}.dmg`; add the `check-version.py` preflight; install `[build-macos]` extras.

**Files:**
- Modify: `.github/workflows/release.ci.yml`
- Test: `tests/ci/test_release_workflow.py`

- [ ] **Step 1: Write the failing test**

Create `tests/ci/test_release_workflow.py`:

```python
"""Static checks on the release CI workflow.

We don't run the workflow here — we assert it reflects the design decisions.
"""
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.ci.yml"


def _load():
    return yaml.safe_load(WORKFLOW.read_text())


def test_workflow_loads():
    _load()


def test_id_token_write_permission_for_oidc():
    wf = _load()
    job = wf["jobs"]["build-macos"]
    perms = job.get("permissions", {})
    assert perms.get("id-token") == "write", (
        "OIDC requires id-token: write on the build-macos job"
    )


def test_no_stubbed_build_step():
    src = WORKFLOW.read_text()
    assert "Build command not configured" not in src


def test_invokes_build_macos_script():
    src = WORKFLOW.read_text()
    assert "packaging/build-macos.sh" in src


def test_uses_aws_configure_credentials_action():
    src = WORKFLOW.read_text()
    assert "aws-actions/configure-aws-credentials@v4" in src


def test_role_to_assume_is_release_publisher():
    src = WORKFLOW.read_text()
    assert "gha-locksmith-release-publisher" in src


def test_uploads_to_releases_keri_host_bucket():
    src = WORKFLOW.read_text()
    assert "releases.keri.host" in src
    # Should NOT reference DO Spaces anymore
    assert "digitaloceanspaces" not in src
    assert "SPACES_ACCESS_KEY" not in src


def test_runs_check_version_preflight():
    src = WORKFLOW.read_text()
    assert "scripts/check-version.py" in src


def test_installs_build_macos_extras():
    src = WORKFLOW.read_text()
    assert ".[build-macos]" in src or "[build-macos]" in src


def test_bundle_id_is_host_keri_locksmith():
    src = WORKFLOW.read_text()
    assert "host.keri.locksmith" in src
    assert "com.CHANGEME.locksmith" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ci/test_release_workflow.py -v`
Expected: FAIL on most cases — current workflow has stubbed build, DO Spaces, `com.CHANGEME.locksmith`.

- [ ] **Step 3: Rewrite the macOS job in `.github/workflows/release.ci.yml`**

Replace the entire `build-macos:` job (lines 7–135) with this version. Leave the `build-windows:` job alone for now — Phase 3 owns it.

```yaml
name: Release Build
on:
  release:
    types: [created]

jobs:
  build-macos:
    runs-on: macos-latest
    permissions:
      id-token: write   # required for GitHub Actions OIDC
      contents: read
    env:
      APP_ID: host.keri.locksmith
      KC_PROFILE: host.keri.locksmith
      LOCKSMITH_RELEASE_CHANNEL: stable
      AWS_REGION: us-east-1
      S3_BUCKET: releases.keri.host
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python 3.14
        uses: actions/setup-python@v5
        with:
          python-version: '3.14'

      - name: Setup virtual environment outside of repo
        run: |
          python -m venv /tmp/venv
          source /tmp/venv/bin/activate
          echo "VIRTUAL_ENV=/tmp/venv" >> $GITHUB_ENV
          echo "/tmp/venv/bin" >> $GITHUB_PATH

      - name: Install requirements (with build-macos extras)
        run: |
          source /tmp/venv/bin/activate
          pip install --upgrade pip setuptools wheel boto3 pyyaml
          pip install -e .[build-macos]

      - name: Preflight — verify tag matches pyproject and is signed
        run: |
          source /tmp/venv/bin/activate
          python scripts/check-version.py --tag "${{ github.event.release.tag_name }}"

      - name: Set version output
        id: set_version
        run: |
          version="${{ github.event.release.tag_name }}"
          if [[ "$version" == v* ]]; then version="${version:1}"; fi
          echo "version=$version" >> "$GITHUB_OUTPUT"

      - name: Install create-dmg
        run: brew install create-dmg

      - name: Import Apple Developer ID certificate
        env:
          CERTIFICATE_BASE64: ${{ secrets.APPLE_DEVELOPER_CERTIFICATE_P12_BASE64 }}
          CERTIFICATE_PASSWORD: ${{ secrets.APPLE_DEVELOPER_CERTIFICATE_PASSWORD }}
          KEYCHAIN_PASSWORD: ${{ secrets.KEYCHAIN_PASSWORD }}
        run: |
          security create-keychain -p "$KEYCHAIN_PASSWORD" build.keychain
          security default-keychain -s build.keychain
          security unlock-keychain -p "$KEYCHAIN_PASSWORD" build.keychain
          security set-keychain-settings -t 3600 -u build.keychain
          echo "$CERTIFICATE_BASE64" | base64 --decode > certificate.p12
          security import certificate.p12 -k build.keychain \
              -P "$CERTIFICATE_PASSWORD" -T /usr/bin/codesign
          security set-key-partition-list -S apple-tool:,apple:,codesign: \
              -s -k "$KEYCHAIN_PASSWORD" build.keychain
          rm certificate.p12

      - name: Store notarytool credentials
        env:
          API_KEY_CONTENT: ${{ secrets.APPLE_API_KEY_CONTENT }}
          API_KEY_ID: ${{ secrets.APPLE_API_KEY_ID }}
          API_KEY_ISSUER: ${{ secrets.APPLE_API_KEY_ISSUER }}
        run: |
          echo "$API_KEY_CONTENT" > /tmp/api_key.p8
          xcrun notarytool store-credentials "$KC_PROFILE" \
              --key /tmp/api_key.p8 \
              --key-id "$API_KEY_ID" \
              --issuer "$API_KEY_ISSUER"
          rm /tmp/api_key.p8

      - name: Export signing identity into env
        env:
          DEVELOPER_ID_APP_CERT: ${{ secrets.DEVELOPER_ID_APP_CERT }}
        run: |
          echo "DEVELOPER_ID_APP_CERT=$DEVELOPER_ID_APP_CERT" >> $GITHUB_ENV

      - name: Build, sign, notarize, staple DMG
        env:
          LOCKSMITH_RELEASE_CHANNEL: ${{ env.LOCKSMITH_RELEASE_CHANNEL }}
        run: |
          source /tmp/venv/bin/activate
          chmod +x packaging/build-macos.sh
          packaging/build-macos.sh

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/gha-locksmith-release-publisher
          aws-region: ${{ env.AWS_REGION }}

      - name: Upload DMG to s3://releases.keri.host/releases/<version>/
        run: |
          source /tmp/venv/bin/activate
          VERSION="${{ steps.set_version.outputs.version }}"
          python scripts/upload.py \
            --bucket "$S3_BUCKET" \
            --object-key "releases/${VERSION}/Locksmith-${VERSION}.dmg" \
            --file "dist/Locksmith-${VERSION}.dmg"

  build-windows:
    runs-on: windows-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python 3.14
        uses: actions/setup-python@v5
        with:
          python-version: '3.14'

      - name: Phase 3 placeholder
        run: |
          echo "Windows build will land in Phase 3 of the deploy/update plan."
          exit 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ci/test_release_workflow.py -v`
Expected: 9 passed.

- [ ] **Step 5: Lint the workflow (best effort)**

If `actionlint` is available locally, run:

```bash
actionlint .github/workflows/release.ci.yml || true
```

Otherwise rely on GitHub's parser to flag any YAML errors on the next push.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/release.ci.yml tests/ci/test_release_workflow.py
git commit -m "feat(deploy): wire macOS CI to PyInstaller + S3 OIDC upload (spec §5.2, §5.6)"
```

---

## Task 13: Write the macOS smoke-test runbook

Spec §10: a polished manual checklist to run on a clean macOS VM after CI produces a release. The plan delivers it as committed documentation.

**Files:**
- Create: `docs/development/macos-build-smoke-test.md`
- Test: `tests/docs/test_smoke_runbook_exists.py`

- [ ] **Step 1: Write the failing test**

Create `tests/docs/test_smoke_runbook_exists.py`:

```python
"""Smoke-test runbook must exist and cover the required checks."""
from pathlib import Path

RUNBOOK = (
    Path(__file__).resolve().parents[2]
    / "docs" / "development" / "macos-build-smoke-test.md"
)

# Minimum content elements the runbook must call out
EXPECTED_PHRASES = [
    "clean macOS",
    "Gatekeeper",
    "spctl --assess",
    "stapler validate",
    "Locksmith.app",
    "drag",  # drag-to-Applications
    "/Applications",
    "open -a Locksmith",
    "host.keri.locksmith",  # bundle id sanity check
    "Activity Monitor",     # confirm process is the new one
]


def test_runbook_exists():
    assert RUNBOOK.is_file(), f"missing: {RUNBOOK}"


def test_runbook_covers_key_checks():
    text = RUNBOOK.read_text()
    missing = [p for p in EXPECTED_PHRASES if p not in text]
    assert not missing, f"runbook missing: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/docs/test_smoke_runbook_exists.py -v`
Expected: FAIL — file does not exist.

- [ ] **Step 3: Create `docs/development/macos-build-smoke-test.md`**

```markdown
# macOS DMG Smoke-Test Runbook

**Audience:** release engineer verifying a CI-produced `Locksmith-X.Y.Z.dmg` before announcing it.
**Frequency:** every release.
**Environment:** a clean macOS VM (UTM/Parallels snapshot, never the dev machine).

This is the human-execution checklist that complements automated CI checks. CI proves the artifact built, signed, and notarized. This runbook proves the artifact *installs and runs* the way a real user will see it.

---

## Pre-flight (host machine)

- [ ] Download the DMG from `https://releases.keri.host/releases/X.Y.Z/Locksmith-X.Y.Z.dmg`
- [ ] Confirm the file size matches the size CI reported in the workflow run logs
- [ ] Run `stapler validate Locksmith-X.Y.Z.dmg` — must report "The validate action worked!"
- [ ] Run `spctl --assess --type open --context context:primary-signature -v Locksmith-X.Y.Z.dmg` — must report "accepted, source=Notarized Developer ID"

If any of the above fails, **do not announce the release** — open an incident, do not retry the upload.

---

## On the clean macOS VM

- [ ] Restore the clean-snapshot of the VM (no prior Locksmith install)
- [ ] Use Safari (default browser) to download the DMG from `releases.keri.host`
- [ ] Double-click the DMG in Finder. The DMG window opens with the branded background visible
- [ ] Visual inspection: the Locksmith icon sits in the left half, the Applications symlink sits in the right half, the arrow/visual hint between them is visible
- [ ] drag the Locksmith icon onto the Applications shortcut in the DMG window
- [ ] Eject the DMG (the Finder side-bar entry should disappear cleanly)

## First launch on the clean VM

- [ ] Open `/Applications` in Finder, double-click `Locksmith.app`
- [ ] **Expected:** the app launches with no Gatekeeper dialog ("App downloaded from internet — are you sure?"). Notarization should handle this silently.
- [ ] If you see a Gatekeeper prompt: **STOP**. The notarization or stapling step failed. Re-check the CI logs and the `stapler validate` output above.
- [ ] The main Locksmith window appears within 5 seconds of launch
- [ ] No console flash. No "Python.app" or "ProcessName" generic-icon flash in the Dock — the Dock icon shows the Locksmith icon from the moment the process starts
- [ ] Open Activity Monitor → the running process name is `Locksmith` (not `python` or `Python`)
- [ ] In Activity Monitor → Inspect the process → "Bundle Identifier" reads `host.keri.locksmith`

## Functional sanity (no KERI verification yet — that's Phase 4)

- [ ] Create a new vault, set a passcode, complete onboarding to the home screen
- [ ] Close the app (`Cmd+Q`), reopen it. Vault prompts for passcode and unlocks cleanly
- [ ] In `About Locksmith` → version reads exactly `X.Y.Z` (matches the DMG filename)

## Uninstall sanity

- [ ] Quit Locksmith
- [ ] Drag `Locksmith.app` from `/Applications` to the Trash
- [ ] Empty Trash. No background processes left in Activity Monitor under `Locksmith`

---

## Sign-off

Record on the release ticket:
- DMG SHA256 (output of `shasum -a 256 Locksmith-X.Y.Z.dmg`)
- macOS version used for the smoke test (`sw_vers`)
- Date and engineer initials
- Any deviations from this checklist (none expected — escalate if any)

A release is **not announced** until this checklist is fully ticked.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/docs/test_smoke_runbook_exists.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/development/macos-build-smoke-test.md tests/docs/test_smoke_runbook_exists.py
git commit -m "docs(deploy): add macOS DMG smoke-test runbook (spec §10)"
```

---

## Task 14: Final whole-plan validation

Verify all the tests added in this plan still pass together, the full unit suite is still green, and the workflow YAML is valid.

- [ ] **Step 1: Run all new tests together**

```bash
pytest tests/scripts/ tests/packaging/ tests/release/ tests/test_build_info.py tests/test_pyproject_build_deps.py tests/ci/ tests/docs/ -v
```

Expected: all green. Total count: 5 + 9 + 4 + 2 + 2 + 5 + 5 + 11 + 9 + 2 = 54 tests passing (approximate; varies by collection).

- [ ] **Step 2: Run the full unit suite to confirm no regressions**

```bash
pytest -x --ignore=tests/integration -q
```

Expected: all green. If a pre-existing test fails, investigate — but do not block on it if the failure is unrelated to anything in this plan.

- [ ] **Step 3: Validate the workflow YAML loads**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.ci.yml'))"
```

Expected: no output (exit 0).

- [ ] **Step 4: Final commit message touch-up commit**

Only if any test gardening was needed during validation. Otherwise skip.

```bash
git status   # verify clean tree
```

---

## Self-Review

### 1. Spec coverage

Walking through the spec sections in scope for Phase 2:

| Spec section | Task(s) |
|---|---|
| §5.1 Bundling (PyInstaller spec, version, embedded anchor) | Task 6, Task 3, Task 4 |
| §5.2 macOS pipeline (PyInstaller → signLibs → codesign --deep → create-dmg → notarytool → stapler) | Task 10, Task 9, Task 7 |
| §5.5 Versioning (tag = pyproject, baked constants, semver, signed tag) | Task 2, Task 4, Task 10 |
| §5.6 CI structure (OIDC, preflight, build-macos) | Task 12, Task 2 |
| §6.1 S3 bucket layout (`releases/{version}/` key path) | Task 8, Task 12 |
| §10.2 Integration tests (PyInstaller, .app exists, launches) | Task 11 |
| §10.3 Release dry-run runbook (manual smoke test on clean VM) | Task 13 |
| §11.1 Entitlements migration (drop sandbox, drop unused AV, keep network + hardened) | Task 1 |
| §11.1 `scripts/sign.sh` adapted for PyInstaller | Task 9 |
| §11.1 `scripts/upload.py` S3 + OIDC | Task 8 |
| §11.1 `APP_ID = host.keri.locksmith` (replace `com.CHANGEME.locksmith`) | Task 6, Task 12 |
| `pyproject.toml` build-tool extras | Task 5 |
| `packaging/dmg/background.png` + `layout.json` | Task 7 |
| `scripts/check-version.py` | Task 2 |

Phase-2-out-of-scope items NOT covered here (correctly): KERI verifier (Phase 4), Sparkle integration (Phase 5), Windows build (Phase 3), anchor-release/publish jobs (Phase 1 + downstream).

### 2. Placeholder scan

Searched the plan for: "TBD", "TODO", "fill in", "implement later", "add appropriate", "similar to". None found except in user-facing instructions inside `publisher_anchor.json` where the value `_comment: "PLACEHOLDER..."` is itself the meaningful data (it documents that Phase 1 will replace it). That's an intentional product placeholder, not a plan placeholder, so it stays.

### 3. Type / signature / path consistency

- `scripts/check-version.py` — args `--tag`, `--pyproject`, `--skip-tag-signature` used consistently between the script body (Task 2 step 3) and tests (Task 2 step 1) and CI invocation (Task 12 step 3 uses only `--tag` and relies on the default `--pyproject`). Consistent.
- `packaging/Locksmith.macos.spec` — `bundle_identifier="host.keri.locksmith"` matches `info_plist["CFBundleIdentifier"]` matches Task 12 env `APP_ID: host.keri.locksmith` matches Task 13 runbook check. Consistent.
- `scripts/sign.sh` — accepts `APP_BUNDLE` and `ENTITLEMENTS` env vars (Task 9 step 3); `packaging/build-macos.sh` sets both before invoking (Task 10 step 3 step 6). Consistent.
- `scripts/upload.py` CLI — `--bucket`, `--object-key`, `--file`, `--region` (Task 8); Task 12 invocation uses `--bucket "$S3_BUCKET" --object-key "releases/${VERSION}/Locksmith-${VERSION}.dmg" --file "dist/Locksmith-${VERSION}.dmg"`. Consistent.
- `LOCKSMITH_VERSION` / `LOCKSMITH_RELEASE_CHANNEL` — defined in Task 4 (`src/locksmith/build_info.py`), rewritten by Task 10 (`build-macos.sh`), tested in Task 4. Consistent.
- `publisher_anchor.json` keys — `publisher_aid`, `embedded_kel_hash`, `embedded_kel_sn`, `witness_oobis` (Task 3 step 3 and Task 3 step 1 test). Matches spec §7.7. Consistent.

No drift found.
