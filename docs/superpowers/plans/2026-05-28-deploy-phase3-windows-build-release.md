# Deploy Phase 3: Windows Build + Signing + Manual Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user can download `Locksmith-X.Y.Z.msi` from `releases.keri.host`, double-click, and install per-user on Windows 10/11 with no UAC, no SmartScreen scariness, no console flash — and uninstall cleanly via Add/Remove Programs. **No KERI verification yet** (Phase 4); **no auto-updater yet** (Phase 5). This phase only builds, signs, and ships the MSI.

**Architecture:** Three independent concerns, wired sequentially:
1. **Bundle.** A committed `packaging/Locksmith.windows.spec` drives PyInstaller to produce `dist/Locksmith/Locksmith.exe` plus a `_internal/` tree of PySide6/Qt/libsodium/qtawesome deps. Version, channel, and embedded publisher anchor are baked in at build time.
2. **Author + Sign.** A committed `packaging/wix/Locksmith.wxs` (WiX Toolset v4) authors a per-user MSI with a polished WixUI flow. `packaging/build-windows.ps1` orchestrates: PyInstaller → sign `Locksmith.exe` via Azure Trusted Signing → `heat` harvest → `wix build` → sign the MSI → verify.
3. **Publish.** The Windows job in `.github/workflows/release.ci.yml` is rewritten: PyInstaller → AzTS sign → WiX → AzTS sign → upload to `s3://releases.keri.host/releases/{version}/Locksmith-{version}.msi` via OIDC. The old `Compress-Archive` + DigitalOcean Spaces path is deleted.

The PyInstaller spec is hidden-import-clean and the WiX wxs is upgrade-safe (immutable `UpgradeCode`, fresh `ProductCode` per release). Installs land in `%LOCALAPPDATA%\Programs\Locksmith\` so Phase 5 WinSparkle can update them in place without admin rights.

**Tech Stack:**
- Python 3.14, PyInstaller 6.x
- WiX Toolset v4 (Cake-free, modern `wix` CLI)
- PowerShell 7 (orchestration)
- `Azure/trusted-signing-action@v0.4.0` (Authenticode signing)
- `aws-actions/configure-aws-credentials@v4` (OIDC → IAM role from Phase 1)
- pytest (test runner); Pester only if a PowerShell helper grows non-trivial logic (currently none planned)

**Phase dependencies:**
- Depends on **Phase 1** for: the `s3://releases.keri.host` bucket, the OIDC IAM role `gha-locksmith-release-publisher`, the placeholder `src/locksmith/release/publisher_anchor.json`.
- Independent of **Phase 2** (macOS). Both can run in parallel jobs.
- Feeds **Phase 4** (KERI verifier) — the embedded `publisher_anchor.json` is loaded by Phase 4's verifier at runtime.
- Feeds **Phase 5** (WinSparkle) — the install layout (`%LOCALAPPDATA%\Programs\Locksmith\`) is the surface WinSparkle will overwrite.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `packaging/Locksmith.windows.spec` | **new** | PyInstaller spec for Windows: entry point, hidden imports, data files (assets, fonts, publisher_anchor.json), libsodium DLL, Qt plugin discovery, version + channel constants, `console=False`, `.ico`. |
| `packaging/wix/Locksmith.wxs` | **new** | WiX v4 product authoring: per-user scope, immutable `UpgradeCode`, fresh `ProductCode` per build, components, shortcuts, WixUI flow, license, branding. |
| `packaging/wix/heat-exclusions.txt` | **new** | Glob list of files heat should skip during harvest (`__pycache__/`, `*.pyc`, `*.pdb`). |
| `packaging/wix/banner.png` | **new** | 493×58 PNG banner (top of installer dialogs). Generated from `assets/custom/SymbolLogo.svg`. |
| `packaging/wix/dialog.png` | **new** | 493×312 PNG (welcome/exit dialog background). Generated from `assets/custom/FullLogo.svg`. |
| `assets/icon.ico` | **new** | Multi-resolution `.ico` (16, 32, 48, 64, 128, 256) generated from `assets/custom/SymbolLogo.svg`. |
| `packaging/build-windows.ps1` | **new** | Local + CI orchestration: PyInstaller → sign Locksmith.exe → heat → wix build → sign MSI → signtool verify. Accepts `-Version`, `-SkipSign` (local dev). |
| `packaging/sign-windows.ps1` | **new** | Thin wrapper around `azuresigntool` / AzTS SDK so the same signing call works in CI and locally; emits `[sign]` structured log lines. |
| `packaging/version-from-pyproject.py` | **new** | Extracts `project.version` from `pyproject.toml` and prints it to stdout. Both the macOS spec (Phase 2) and Windows spec consume it. |
| `scripts/generate-windows-assets.py` | **new** | Generates `assets/icon.ico`, `packaging/wix/banner.png`, `packaging/wix/dialog.png` from existing SVGs via Pillow. Committed outputs are checked into the repo; the script is for regeneration. |
| `.github/workflows/release.ci.yml` | modify (replace `build-windows` job) | New Windows job: setup-python, OIDC auth, install WiX + AzTS, run `build-windows.ps1`, upload MSI to S3. |
| `docs/development/windows-signing-setup.md` | **new** | One-time-ops runbook: AzTS account creation, identity validation, certificate profile, federated credentials for GitHub OIDC, required secrets. |
| `docs/development/windows-build-smoke-test.md` | **new** | Manual smoke-test runbook for a clean Windows 11 VM. |
| `tests/integration/test_pyinstaller_windows.py` | **new** | Integration test: invoke PyInstaller against the spec, assert `Locksmith.exe` exists, launch with `--self-test`, assert exit code 0. Skipped if not on Windows. |
| `tests/integration/test_wix_authoring.py` | **new** | Integration test: lint `Locksmith.wxs` with `wix build` (no link), validate component GUIDs are present and the upgrade code is immutable. |
| `tests/unit/test_version_from_pyproject.py` | **new** | Unit test for the version extractor. |
| `src/locksmith/main.py` | modify | Add `--self-test` flag that prints version + embedded anchor summary and exits 0; gate the GUI startup behind "no flag passed". |

---

## Conventions

- **Commit messages:** Conventional commits (`feat(packaging):`, `fix(ci):`, `test(packaging):`, `docs(packaging):`).
- **Branch:** `feat/deploy-phase3-windows` (off `development`).
- **Versions everywhere:** read from `pyproject.toml`. Never hardcode.
- **WiX v4 chosen over v3.** Rationale: v4 has a single `wix` CLI (no `candle`/`light` two-step), built-in `wix.exe build` linting, and modern XML namespace. Spec says "v4 unless v3 ergonomics are needed" — v3 ergonomics are not needed.
- **Install location:** `%LOCALAPPDATA%\Programs\Locksmith\` (per-user, no UAC, WinSparkle-friendly).
- **Logging:** All build-script output uses `[build]`, `[sign]`, `[wix]`, `[upload]` tags per project's `[[feedback-testing-automated]]` memory.

---

## Task 1: Version extractor (`packaging/version-from-pyproject.py`)

A tiny script we'll reuse in PyInstaller, WiX, and CI. Centralizing it means we get **one** failure mode for version-skew.

**Files:**
- Create: `packaging/version-from-pyproject.py`
- Create: `tests/unit/test_version_from_pyproject.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_version_from_pyproject.py`:

```python
"""Tests for packaging/version-from-pyproject.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "packaging" / "version-from-pyproject.py"


def test_prints_version_from_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(pyproject)],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "1.2.3"


def test_exits_nonzero_when_version_missing(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\n', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(pyproject)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "version" in result.stderr.lower()


def test_default_pyproject_is_repo_root_when_no_arg():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    )
    # Should match whatever the real pyproject says — non-empty semver-ish.
    out = result.stdout.strip()
    assert out and out.count(".") >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_version_from_pyproject.py -v`
Expected: FAIL — `packaging/version-from-pyproject.py` does not exist (FileNotFoundError or non-zero exit).

- [ ] **Step 3: Implement the script**

Create `packaging/version-from-pyproject.py`:

```python
#!/usr/bin/env python3
"""Print the [project].version from a pyproject.toml file.

Used by PyInstaller specs, WiX authoring, and CI to derive a single source
of truth for the application version.

Usage:
    python packaging/version-from-pyproject.py            # uses ./pyproject.toml
    python packaging/version-from-pyproject.py path/to/pyproject.toml
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def read_version(pyproject_path: Path) -> str:
    with pyproject_path.open("rb") as fh:
        data = tomllib.load(fh)
    try:
        return str(data["project"]["version"])
    except KeyError as exc:
        raise KeyError(f"[project].version not found in {pyproject_path}") from exc


def main(argv: list[str]) -> int:
    pyproject = Path(argv[1]) if len(argv) > 1 else Path("pyproject.toml")
    if not pyproject.is_file():
        print(f"error: pyproject.toml not found at {pyproject}", file=sys.stderr)
        return 2
    try:
        version = read_version(pyproject)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_version_from_pyproject.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add packaging/version-from-pyproject.py tests/unit/test_version_from_pyproject.py
git commit -m "feat(packaging): version-from-pyproject helper for build pipeline"
```

---

## Task 2: `--self-test` flag in `src/locksmith/main.py`

This is the entry point we'll use in `tests/integration/test_pyinstaller_windows.py` to launch the bundled exe non-interactively. We can't launch the full GUI from a CI runner — we need a deterministic dry-run path.

**Files:**
- Modify: `src/locksmith/main.py`
- Test: `tests/unit/test_main_self_test_flag.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_main_self_test_flag.py`:

```python
"""Tests for the --self-test entry-point flag."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_self_test_exits_zero_and_prints_version():
    """Running `python -m locksmith.main --self-test` prints version and exits 0."""
    result = subprocess.run(
        [sys.executable, "-m", "locksmith.main", "--self-test"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "locksmith self-test ok" in result.stdout.lower()
    # Version from version.py should be in the output
    assert "0.0.1" in result.stdout or "version=" in result.stdout.lower()


def test_self_test_does_not_start_gui(monkeypatch):
    """Self-test must not import QApplication or open a window."""
    # Subprocess-level check is the safest: just confirm exit-zero is fast.
    import time
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "locksmith.main", "--self-test"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=15,
    )
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    # GUI startup typically takes >2s; self-test should be much faster.
    assert elapsed < 10, f"self-test took {elapsed}s — should be <10s"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_main_self_test_flag.py -v`
Expected: FAIL — `--self-test` flag not recognized; exits non-zero or starts the GUI.

- [ ] **Step 3: Add the flag handling**

Modify `src/locksmith/main.py`. Find the existing `if __name__ == "__main__":` block (near end of file, after `set_load_env_vars`). Replace the existing block so `--self-test` is checked **before** any QApplication import or libsodium load:

```python
if __name__ == "__main__":
    # Self-test entry: prints version + embedded anchor summary and exits.
    # Used by CI integration tests against the PyInstaller-bundled binary,
    # and by smoke-test runbooks on clean VMs. Must NOT start the GUI.
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        from locksmith.version import __version__
        print(f"Locksmith self-test ok version={__version__}")

        # Try to load the embedded publisher anchor (created in Phase 1).
        # If it's not present yet, that's fine — Phase 1 may not have landed.
        try:
            import json
            from importlib import resources
            with resources.files("locksmith.release").joinpath("publisher_anchor.json").open("r") as fh:
                anchor = json.load(fh)
            print(f"anchor publisher_aid={anchor.get('publisher_aid', 'unset')}")
            print(f"anchor embedded_kel_sn={anchor.get('embedded_kel_sn', 'unset')}")
        except (ModuleNotFoundError, FileNotFoundError, AttributeError):
            print("anchor not_embedded")

        sys.exit(0)

    # Check if running in MCP server mode (for PyInstaller bundle subprocess)
    if len(sys.argv) > 1 and sys.argv[1] == "--mcp-server":
        logger.info("MCP server mode detected")
        logger.info(f"sys.argv: {sys.argv}")
        logger.info(f"sys.executable: {sys.executable}")
        logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")

    if platform.system() == 'Darwin':
        load_custom_libsodium()

    from locksmith.ui.styles import set_global_styles
    from locksmith.core.configing import LocksmithConfig
    from locksmith.ui.window import LocksmithWindow

    app = QApplication(sys.argv)
    set_global_styles(app)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    config = LocksmithConfig.get_instance()
    window = LocksmithWindow(config)
    window.show()

    with loop:
        sys.exit(loop.run_forever())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_main_self_test_flag.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/main.py tests/unit/test_main_self_test_flag.py
git commit -m "feat(main): add --self-test CLI flag for CI bundle smoke tests"
```

---

## Task 3: Windows asset generation (icon, banner, dialog images)

Generate the `.ico` and the two WiX UI PNGs **once**, commit the outputs, and ship a script so we can regenerate when the brand changes. We're not building this in CI — Pillow + cairosvg in a Python script is enough.

**Files:**
- Create: `scripts/generate-windows-assets.py`
- Create: `assets/icon.ico` (output, committed)
- Create: `packaging/wix/banner.png` (output, committed, 493×58)
- Create: `packaging/wix/dialog.png` (output, committed, 493×312)
- Test: `tests/unit/test_generate_windows_assets.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_generate_windows_assets.py`:

```python
"""Tests for the Windows asset generation script."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_icon_exists_and_is_ico():
    icon = REPO_ROOT / "assets" / "icon.ico"
    assert icon.is_file(), f"expected committed icon at {icon}"
    # ICO files start with 0x00 0x00 0x01 0x00
    head = icon.read_bytes()[:4]
    assert head == b"\x00\x00\x01\x00", f"not an ICO file: {head!r}"


def test_banner_exists_and_correct_dimensions():
    banner = REPO_ROOT / "packaging" / "wix" / "banner.png"
    assert banner.is_file()
    from PIL import Image
    with Image.open(banner) as img:
        assert img.size == (493, 58), f"banner size {img.size} != (493, 58)"


def test_dialog_exists_and_correct_dimensions():
    dialog = REPO_ROOT / "packaging" / "wix" / "dialog.png"
    assert dialog.is_file()
    from PIL import Image
    with Image.open(dialog) as img:
        assert img.size == (493, 312), f"dialog size {img.size} != (493, 312)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_generate_windows_assets.py -v`
Expected: FAIL — files don't exist.

- [ ] **Step 3: Write the generator script**

Create `scripts/generate-windows-assets.py`:

```python
#!/usr/bin/env python3
"""Regenerate Windows-specific image assets from the canonical SVG sources.

Outputs (all committed to git):
  - assets/icon.ico               multi-resolution Windows icon
  - packaging/wix/banner.png      493x58 banner (top of WiX dialogs)
  - packaging/wix/dialog.png      493x312 background (welcome/exit dialogs)

Inputs:
  - assets/custom/SymbolLogo.svg  -> icon, banner mark
  - assets/custom/FullLogo.svg    -> dialog background

Usage:
    python scripts/generate-windows-assets.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

try:
    import cairosvg
    from PIL import Image, ImageDraw
except ImportError as exc:
    print(f"error: missing dependency {exc.name!r}; run: pip install cairosvg pillow", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[1]
SYMBOL_SVG = REPO_ROOT / "assets" / "custom" / "SymbolLogo.svg"
FULL_SVG = REPO_ROOT / "assets" / "custom" / "FullLogo.svg"

OUT_ICON = REPO_ROOT / "assets" / "icon.ico"
OUT_BANNER = REPO_ROOT / "packaging" / "wix" / "banner.png"
OUT_DIALOG = REPO_ROOT / "packaging" / "wix" / "dialog.png"

ICON_SIZES = [16, 32, 48, 64, 128, 256]


def render_svg_to_png(svg_path: Path, width: int, height: int) -> Image.Image:
    """Render an SVG to a PNG-bytes-backed PIL Image at the requested pixel size."""
    png_bytes = cairosvg.svg2png(
        url=str(svg_path),
        output_width=width,
        output_height=height,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def make_icon() -> None:
    OUT_ICON.parent.mkdir(parents=True, exist_ok=True)
    images = [render_svg_to_png(SYMBOL_SVG, s, s) for s in ICON_SIZES]
    # Pillow handles multi-size ICO via the `sizes` kwarg.
    images[0].save(OUT_ICON, format="ICO", sizes=[(s, s) for s in ICON_SIZES], append_images=images[1:])
    print(f"[assets] wrote {OUT_ICON} ({len(ICON_SIZES)} resolutions)")


def make_banner() -> None:
    """493x58 banner: white background, symbol mark on the right."""
    OUT_BANNER.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGBA", (493, 58), (255, 255, 255, 255))
    mark = render_svg_to_png(SYMBOL_SVG, 44, 44)
    # Right-align mark with 8px padding.
    canvas.paste(mark, (493 - 44 - 8, (58 - 44) // 2), mark)
    canvas.convert("RGB").save(OUT_BANNER, format="PNG")
    print(f"[assets] wrote {OUT_BANNER}")


def make_dialog() -> None:
    """493x312 background: white, centered full logo."""
    OUT_DIALOG.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGBA", (493, 312), (255, 255, 255, 255))
    logo = render_svg_to_png(FULL_SVG, 260, 130)
    x = (493 - 260) // 2
    y = (312 - 130) // 2 - 20  # nudge up for visual balance
    canvas.paste(logo, (x, y), logo)
    canvas.convert("RGB").save(OUT_DIALOG, format="PNG")
    print(f"[assets] wrote {OUT_DIALOG}")


def main() -> int:
    if not SYMBOL_SVG.is_file() or not FULL_SVG.is_file():
        print(f"error: missing input SVG ({SYMBOL_SVG} or {FULL_SVG})", file=sys.stderr)
        return 1
    make_icon()
    make_banner()
    make_dialog()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Generate the assets**

Run:
```bash
python -m pip install cairosvg pillow
python scripts/generate-windows-assets.py
```
Expected: three new files under `assets/icon.ico`, `packaging/wix/banner.png`, `packaging/wix/dialog.png`.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_generate_windows_assets.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/generate-windows-assets.py \
        assets/icon.ico \
        packaging/wix/banner.png \
        packaging/wix/dialog.png \
        tests/unit/test_generate_windows_assets.py
git commit -m "feat(packaging): generate committed Windows installer assets (icon, banner, dialog)"
```

---

## Task 4: PyInstaller spec for Windows

The spec is mostly declarative; the only real engineering decision is which Qt plugins and hidden imports to include. We pin the conservative superset (more plugins is wasted disk; missing plugins is a runtime crash) and add a hidden-imports list driven by what `locksmith.ui` and `keri` actually load.

**Files:**
- Create: `packaging/Locksmith.windows.spec`
- Test: deferred to Task 9 (integration test runs the spec on a Windows runner)

- [ ] **Step 1: Write the spec**

Create `packaging/Locksmith.windows.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Locksmith Windows build.

Inputs:
  - src/locksmith/main.py             (entry point)
  - assets/                           (icons, fonts, custom images)
  - src/locksmith/release/publisher_anchor.json (created in Phase 1)
  - assets/icon.ico                   (committed in Task 3)

Outputs:
  - dist/Locksmith/Locksmith.exe      (entry binary)
  - dist/Locksmith/_internal/         (PyInstaller dep tree)

Build-time constants:
  - LOCKSMITH_VERSION         derived from pyproject.toml
  - LOCKSMITH_RELEASE_CHANNEL "stable" for v1

Run:
    pyinstaller --noconfirm --clean packaging/Locksmith.windows.spec
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# -- Repo paths ---------------------------------------------------------------

SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parent
SRC_ROOT = REPO_ROOT / "src"
ASSETS = REPO_ROOT / "assets"
ICON = ASSETS / "icon.ico"

# -- Version + channel (build-time constants) ---------------------------------

VERSION_SCRIPT = SPEC_DIR / "version-from-pyproject.py"
LOCKSMITH_VERSION = subprocess.run(
    [sys.executable, str(VERSION_SCRIPT)],
    cwd=str(REPO_ROOT), capture_output=True, text=True, check=True,
).stdout.strip()
LOCKSMITH_RELEASE_CHANNEL = "stable"

print(f"[spec] LOCKSMITH_VERSION={LOCKSMITH_VERSION}")
print(f"[spec] LOCKSMITH_RELEASE_CHANNEL={LOCKSMITH_RELEASE_CHANNEL}")

# Expose as env vars the runtime can read at boot (frozen runtime sees these).
os.environ["LOCKSMITH_VERSION"] = LOCKSMITH_VERSION
os.environ["LOCKSMITH_RELEASE_CHANNEL"] = LOCKSMITH_RELEASE_CHANNEL

# -- Data files ---------------------------------------------------------------

datas = []

# Bundle the assets/ tree wholesale; resources_rc.py also references them.
datas += [(str(ASSETS), "assets")]

# Embed the publisher trust anchor (Phase 1 produces this file).
anchor_src = SRC_ROOT / "locksmith" / "release" / "publisher_anchor.json"
if anchor_src.is_file():
    datas += [(str(anchor_src), "locksmith/release")]
else:
    print(f"[spec] WARNING: {anchor_src} not present; building without embedded anchor "
          f"(Phase 1 may not yet have landed)")

# qtawesome's icon-font files (Material, FontAwesome, etc).
datas += collect_data_files("qtawesome")

# keri's data files (configs, schemas).
datas += collect_data_files("keri")

# -- Hidden imports -----------------------------------------------------------
#
# Pinned list: things imported via string lookups, plugin entry points,
# or by C extensions. Add new entries here if a runtime ModuleNotFoundError
# appears during smoke testing.
#
hiddenimports = []
hiddenimports += collect_submodules("locksmith.plugins")
hiddenimports += collect_submodules("locksmith.ui")
hiddenimports += [
    "qasync",
    "pysodium",
    "qtawesome._iconic_font",
    "keri.app",
    "keri.core",
    "keri.db",
    "keri.help",
    "keri.peer",
    "keri.vdr",
    "cbor",
    "falcon",
    "mnemonic",
    "multicommand",
    "pyotp",
    "schedule",
    "kerkle",
    "qrcode",
    "PIL",
    "PIL.Image",
    "PIL.ImageQt",
]

# -- Binaries -----------------------------------------------------------------
#
# libsodium is needed by pysodium; on Windows we expect it as a DLL
# discoverable on PATH. PyInstaller's binary collection will follow it via
# pysodium's ctypes call, but pin it explicitly as a belt-and-braces measure.
#
binaries = []
import importlib.util  # noqa: E402
_sodium_spec = importlib.util.find_spec("pysodium")
if _sodium_spec is not None:
    # pysodium ships nothing — the DLL must already be on the runner.
    # vcpkg / chocolatey libsodium installs libsodium.dll into a known path.
    # CI installs via choco; see release.ci.yml.
    pass

# -- Analysis -----------------------------------------------------------------

block_cipher = None

a = Analysis(
    [str(SRC_ROOT / "locksmith" / "main.py")],
    pathex=[str(SRC_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Big optional deps we don't ship.
        "tkinter",
        "matplotlib",
        "scipy",
        "test",
        "tests",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# -- Executable ---------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Locksmith",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX breaks signtool; never enable.
    console=False,              # Windowed Qt app — no console flash.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,     # Signing is done in build-windows.ps1.
    entitlements_file=None,
    icon=str(ICON) if ICON.is_file() else None,
    version_file=None,          # We rely on the MSI for version metadata.
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Locksmith",
)
```

- [ ] **Step 2: Smoke-check the spec parses on the dev host**

This step only verifies the spec is syntactically valid Python and PyInstaller can load it. We do NOT actually build on a non-Windows host (Qt plugin collection differs per platform).

Run (works on macOS/Linux dev hosts):
```bash
python -c "import ast; ast.parse(open('packaging/Locksmith.windows.spec').read()); print('spec parses')"
```
Expected: prints `spec parses`.

- [ ] **Step 3: Commit**

```bash
git add packaging/Locksmith.windows.spec
git commit -m "feat(packaging): PyInstaller spec for Windows Locksmith.exe"
```

---

## Task 5: `heat-exclusions.txt` for WiX harvest

`heat` (the wxs harvester) is unforgiving about cruft files. We exclude debug symbols, `__pycache__`, etc. so the MSI payload is clean.

**Files:**
- Create: `packaging/wix/heat-exclusions.txt`

- [ ] **Step 1: Write the file**

Create `packaging/wix/heat-exclusions.txt`:

```
# Files to omit from the WiX heat harvest of dist/Locksmith.
# Lines are matched as filename globs (case-insensitive on Windows).
# Used by packaging/build-windows.ps1 to filter the heat-generated fragment
# before passing it to `wix build`.

__pycache__
*.pyc
*.pyo
*.pdb
*.lib
*.exp
*.map
*.log
*.tmp
.DS_Store
Thumbs.db
```

- [ ] **Step 2: Commit**

```bash
git add packaging/wix/heat-exclusions.txt
git commit -m "feat(packaging): heat exclusion list for WiX harvest"
```

---

## Task 6: WiX v4 product authoring (`packaging/wix/Locksmith.wxs`)

This is the meatiest file. We're authoring a **per-user**, no-UAC MSI with a polished WixUI dialog flow. Key design points:

- `InstallScope="perUser"` + `InstallPrivileges="limited"` ⇒ no UAC.
- Install to `LocalAppDataFolder\Programs\Locksmith\` ⇒ WinSparkle (Phase 5) can overwrite without admin.
- **Immutable** `UpgradeCode` (committed GUID) ⇒ MSI knows what previous versions to remove on upgrade.
- **Per-build** `ProductCode` (`*` in WiX v4 ⇒ auto-generated each build) ⇒ each MSI is a distinct product instance.
- WixUI standard dialog set with custom banner/dialog images.
- `MajorUpgrade` element ⇒ smart in-place upgrade behavior.

**Files:**
- Create: `packaging/wix/Locksmith.wxs`
- Create: `packaging/wix/license.rtf` (Wix needs RTF for the license dialog)
- Test: `tests/integration/test_wix_authoring.py` (new — covered in Task 8)

- [ ] **Step 1: Generate the license RTF from LICENSE**

WiX's WixUI_InstallDir license dialog reads RTF only. We convert the repo's existing `LICENSE` to RTF.

Create `packaging/wix/license.rtf`:

```rtf
{\rtf1\ansi\deffs0\fs20
{\fonttbl{\f0\fnil\fcharset0 Segoe UI;}}
\f0
\b Locksmith \b0\par
\par
Copyright (c) KERI.host\par
\par
Licensed under the MIT License. You may obtain a copy of the License at\par
https://opensource.org/licenses/MIT \par
\par
This software is provided "as is", without warranty of any kind, express or\par
implied, including but not limited to the warranties of merchantability,\par
fitness for a particular purpose, and noninfringement. In no event shall the\par
authors or copyright holders be liable for any claim, damages, or other\par
liability arising from the use of this software.\par
\par
Full license text:\par
https://github.com/seriouscoderone/locksmith/blob/main/LICENSE\par
}
```

- [ ] **Step 2: Mint an UpgradeCode GUID**

This GUID **MUST NEVER CHANGE** across releases. Generate once and bake into the wxs.

Run on a Unix-y host:
```bash
python -c "import uuid; print(str(uuid.uuid4()).upper())"
```
Note the GUID output (e.g. `7C9F4B8A-3D2E-4A1B-9F8C-1234567890AB`).

> **Plan-time GUID lock:** The implementing engineer MUST commit a specific generated UpgradeCode the first time this plan is executed and use the same value forever. The example below is illustrative only.

Pick the generated GUID — let's call it `<UPGRADE_GUID>` — and use it in Step 3 below. Once committed, this is permanent for `host.keri.locksmith`.

- [ ] **Step 3: Write the wxs**

Create `packaging/wix/Locksmith.wxs`. **Replace `<UPGRADE_GUID>` with the GUID from Step 2 before committing.**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  Locksmith MSI authoring (WiX v4).

  Compile + link:
    wix build Locksmith.wxs HarvestedComponents.wxs `
        -ext WixToolset.UI.wixext `
        -arch x64 `
        -define Version=$env:LOCKSMITH_VERSION `
        -out Locksmith-$env:LOCKSMITH_VERSION.msi

  Notes:
    - UpgradeCode is immutable across releases. NEVER regenerate it.
    - ProductCode is auto-generated per build (`Id="*"`).
    - Per-user install scope: no UAC prompt on install.
    - Install path: %LOCALAPPDATA%\Programs\Locksmith\
-->
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"
     xmlns:ui="http://wixtoolset.org/schemas/v4/wxs/ui">

  <Package
      Name="Locksmith"
      Manufacturer="KERI.host"
      Version="$(var.Version)"
      UpgradeCode="<UPGRADE_GUID>"
      Scope="perUser"
      InstallerVersion="500"
      Compressed="yes"
      Codepage="1252">

    <!-- Per-user install: no UAC, no admin required. -->
    <Property Id="ALLUSERS" Value="" />
    <Property Id="MSIINSTALLPERUSER" Value="1" />

    <!-- Smart upgrade: same UpgradeCode, larger version => replace; smaller => block. -->
    <MajorUpgrade
        DowngradeErrorMessage="A newer version of Locksmith is already installed."
        Schedule="afterInstallInitialize"
        AllowSameVersionUpgrades="yes" />

    <!-- Single cab embedded in the MSI. -->
    <MediaTemplate EmbedCab="yes" />

    <!-- Branding & metadata visible in Add/Remove Programs. -->
    <Property Id="ARPPRODUCTICON" Value="LocksmithIcon" />
    <Property Id="ARPURLINFOABOUT" Value="https://locksmith.app" />
    <Property Id="ARPHELPLINK" Value="https://locksmith.app/support" />
    <Property Id="ARPNOREPAIR" Value="1" />
    <Property Id="ARPNOMODIFY" Value="1" />
    <Icon Id="LocksmithIcon" SourceFile="..\..\assets\icon.ico" />

    <!-- Install location: %LOCALAPPDATA%\Programs\Locksmith\ -->
    <StandardDirectory Id="LocalAppDataFolder">
      <Directory Id="ProgramsFolder" Name="Programs">
        <Directory Id="INSTALLFOLDER" Name="Locksmith" />
      </Directory>
    </StandardDirectory>

    <!-- Start menu folder for the shortcut. -->
    <StandardDirectory Id="ProgramMenuFolder">
      <Directory Id="ApplicationProgramsFolder" Name="Locksmith" />
    </StandardDirectory>

    <!-- Desktop folder is referenced by the optional desktop-shortcut component. -->
    <StandardDirectory Id="DesktopFolder" />

    <!-- Start menu shortcut (always installed). -->
    <DirectoryRef Id="ApplicationProgramsFolder">
      <Component Id="StartMenuShortcut" Guid="*">
        <Shortcut Id="StartMenuShortcut"
                  Name="Locksmith"
                  Description="Locksmith — KERI identity vault"
                  Target="[INSTALLFOLDER]Locksmith.exe"
                  WorkingDirectory="INSTALLFOLDER"
                  Icon="LocksmithIcon" />
        <RemoveFolder Id="RemoveApplicationProgramsFolder"
                      Directory="ApplicationProgramsFolder"
                      On="uninstall" />
        <RegistryValue Root="HKCU"
                       Key="Software\KERI.host\Locksmith"
                       Name="StartMenuShortcut"
                       Type="integer"
                       Value="1"
                       KeyPath="yes" />
      </Component>
    </DirectoryRef>

    <!-- Desktop shortcut (optional; user can uncheck during install). -->
    <DirectoryRef Id="DesktopFolder">
      <Component Id="DesktopShortcut" Guid="*">
        <Condition>INSTALLDESKTOPSHORTCUT = 1</Condition>
        <Shortcut Id="DesktopShortcut"
                  Name="Locksmith"
                  Description="Locksmith — KERI identity vault"
                  Target="[INSTALLFOLDER]Locksmith.exe"
                  WorkingDirectory="INSTALLFOLDER"
                  Icon="LocksmithIcon" />
        <RegistryValue Root="HKCU"
                       Key="Software\KERI.host\Locksmith"
                       Name="DesktopShortcut"
                       Type="integer"
                       Value="1"
                       KeyPath="yes" />
      </Component>
    </DirectoryRef>

    <Property Id="INSTALLDESKTOPSHORTCUT" Value="1" />

    <!--
      Feature ties harvested components, shortcuts, and the desktop-shortcut
      together. HarvestedComponents.wxs is generated by `heat` from the
      PyInstaller dist/Locksmith directory at build time.
    -->
    <Feature Id="MainFeature"
             Title="Locksmith"
             Level="1"
             ConfigurableDirectory="INSTALLFOLDER"
             AllowAdvertise="no"
             Absent="disallow">
      <ComponentGroupRef Id="HarvestedComponents" />
      <ComponentRef Id="StartMenuShortcut" />
      <ComponentRef Id="DesktopShortcut" />
    </Feature>

    <!-- WixUI dialog flow: minimal but polished. -->
    <ui:WixUI Id="WixUI_InstallDir" InstallDirectory="INSTALLFOLDER" />
    <WixVariable Id="WixUILicenseRtf" Value="license.rtf" />
    <WixVariable Id="WixUIBannerBmp" Value="banner.png" />
    <WixVariable Id="WixUIDialogBmp" Value="dialog.png" />

    <!-- Default INSTALLFOLDER if user accepts default (relative redirect). -->
    <SetProperty Id="INSTALLFOLDER"
                 Value="[LocalAppDataFolder]Programs\Locksmith"
                 Before="CostFinalize"
                 Sequence="execute">
      INSTALLFOLDER=""
    </SetProperty>

  </Package>
</Wix>
```

- [ ] **Step 4: Commit**

```bash
git add packaging/wix/Locksmith.wxs packaging/wix/license.rtf
git commit -m "feat(packaging): WiX v4 per-user MSI authoring for Locksmith"
```

---

## Task 7: PowerShell signing wrapper (`packaging/sign-windows.ps1`)

A thin wrapper around the Azure Trusted Signing tool so the same call works in CI and locally. We use the official `azuresigntool` (a.k.a. AST CLI) which the `Azure/trusted-signing-action` GitHub Action also drives internally; running it directly locally lets us reproduce signing failures off-CI.

**Files:**
- Create: `packaging/sign-windows.ps1`

- [ ] **Step 1: Write the script**

Create `packaging/sign-windows.ps1`:

```powershell
<#
.SYNOPSIS
    Sign a file (EXE or MSI) with Azure Trusted Signing.

.DESCRIPTION
    Wraps the AzureSignTool CLI. Reads Azure credentials from environment
    variables (set by the GitHub Action via OIDC, or by the developer
    locally via `az login` + service principal).

    Required env vars:
      AZURE_TENANT_ID
      AZURE_CLIENT_ID
      AZURE_SUBSCRIPTION_ID
      AZURE_TRUSTED_SIGNING_ACCOUNT_NAME
      AZURE_TRUSTED_SIGNING_CERTIFICATE_PROFILE_NAME
      AZURE_TRUSTED_SIGNING_ENDPOINT
        (e.g. https://eus.codesigning.azure.net/ - region of the AzTS account)

.PARAMETER Path
    Absolute path to the file to sign (Locksmith.exe or Locksmith-X.Y.Z.msi).

.PARAMETER Description
    Human-readable description embedded in the signature (visible in
    Properties > Digital Signatures).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $false)]
    [string]$Description = "Locksmith"
)

$ErrorActionPreference = "Stop"

function Require-Env {
    param([string]$Name)
    $value = [System.Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "[sign] required environment variable not set: $Name"
    }
    return $value
}

if (-not (Test-Path -LiteralPath $Path)) {
    throw "[sign] file not found: $Path"
}

$tenantId       = Require-Env "AZURE_TENANT_ID"
$clientId       = Require-Env "AZURE_CLIENT_ID"
$endpoint       = Require-Env "AZURE_TRUSTED_SIGNING_ENDPOINT"
$accountName    = Require-Env "AZURE_TRUSTED_SIGNING_ACCOUNT_NAME"
$profileName    = Require-Env "AZURE_TRUSTED_SIGNING_CERTIFICATE_PROFILE_NAME"

Write-Host "[sign] signing $Path"
Write-Host "[sign]   endpoint=$endpoint account=$accountName profile=$profileName"

# Locate AzureSignTool. CI installs it via `dotnet tool install`.
# Locally, developers must `dotnet tool install -g AzureSignTool`.
$astCmd = Get-Command AzureSignTool -ErrorAction SilentlyContinue
if (-not $astCmd) {
    throw "[sign] AzureSignTool not on PATH; install with: dotnet tool install -g AzureSignTool"
}

& AzureSignTool sign `
    --azure-key-vault-url $endpoint `
    --azure-key-vault-tenant-id $tenantId `
    --azure-key-vault-client-id $clientId `
    --azure-key-vault-managed-identity `
    --description $Description `
    --description-url "https://locksmith.app" `
    --timestamp-rfc3161 "http://timestamp.acs.microsoft.com" `
    --timestamp-digest sha256 `
    --file-digest sha256 `
    --trusted-signing-account-name $accountName `
    --certificate-profile-name $profileName `
    --verbose `
    -- $Path

if ($LASTEXITCODE -ne 0) {
    throw "[sign] AzureSignTool exited with code $LASTEXITCODE"
}

Write-Host "[sign] verifying signature with signtool /pa /v $Path"
& signtool verify /pa /v $Path
if ($LASTEXITCODE -ne 0) {
    throw "[sign] signtool verify failed (exit $LASTEXITCODE) — signature did not stick"
}

Write-Host "[sign] ok $Path"
```

- [ ] **Step 2: Commit**

```bash
git add packaging/sign-windows.ps1
git commit -m "feat(packaging): Azure Trusted Signing wrapper for Windows signing"
```

---

## Task 8: Orchestrator script (`packaging/build-windows.ps1`)

The end-to-end pipeline: PyInstaller → sign exe → harvest → wix build → sign msi → verify.

**Files:**
- Create: `packaging/build-windows.ps1`

- [ ] **Step 1: Write the script**

Create `packaging/build-windows.ps1`:

```powershell
<#
.SYNOPSIS
    Build, sign, and package Locksmith for Windows.

.DESCRIPTION
    Drives the full Windows release pipeline:
      1. PyInstaller     -> dist/Locksmith/Locksmith.exe
      2. AzureSignTool   -> signs Locksmith.exe (embedded in MSI)
      3. heat            -> harvests dist/Locksmith -> HarvestedComponents.wxs
      4. wix build       -> Locksmith-X.Y.Z.msi
      5. AzureSignTool   -> signs the MSI itself
      6. signtool verify -> sanity check

.PARAMETER Version
    Override the version derived from pyproject.toml. Optional.

.PARAMETER SkipSign
    Skip signing steps (useful for local dev iteration; produces an
    unsigned MSI that Windows will SmartScreen-warn on).

.EXAMPLE
    pwsh packaging/build-windows.ps1
    pwsh packaging/build-windows.ps1 -SkipSign
    pwsh packaging/build-windows.ps1 -Version 1.2.3
#>
[CmdletBinding()]
param(
    [string]$Version,
    [switch]$SkipSign
)

$ErrorActionPreference = "Stop"

# --- Repo + workspace ---------------------------------------------------------

$repoRoot     = (Resolve-Path "$PSScriptRoot\..").Path
$packagingDir = "$repoRoot\packaging"
$wixDir       = "$packagingDir\wix"
$distDir      = "$repoRoot\dist\Locksmith"
$buildDir     = "$repoRoot\build\windows"

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

# --- Resolve version ----------------------------------------------------------

if (-not $Version) {
    $Version = (& python "$packagingDir\version-from-pyproject.py" "$repoRoot\pyproject.toml").Trim()
}
if (-not $Version) {
    throw "[build] could not derive version"
}
$env:LOCKSMITH_VERSION = $Version
$env:LOCKSMITH_RELEASE_CHANNEL = "stable"
Write-Host "[build] LOCKSMITH_VERSION=$Version"

# --- Step 1: PyInstaller ------------------------------------------------------

Write-Host "[build] running PyInstaller"
Push-Location $repoRoot
try {
    & pyinstaller --noconfirm --clean "$packagingDir\Locksmith.windows.spec"
} finally {
    Pop-Location
}

$exePath = Join-Path $distDir "Locksmith.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "[build] PyInstaller did not produce $exePath"
}
Write-Host "[build] PyInstaller ok exe=$exePath"

# --- Step 2: Sign Locksmith.exe ----------------------------------------------

if (-not $SkipSign) {
    Write-Host "[build] signing $exePath"
    & pwsh "$packagingDir\sign-windows.ps1" -Path $exePath -Description "Locksmith"
} else {
    Write-Host "[build] -SkipSign set; leaving $exePath unsigned"
}

# --- Step 3: Harvest with heat (wix v4) ---------------------------------------

Write-Host "[build] harvesting $distDir with heat"
$harvestedWxs = Join-Path $buildDir "HarvestedComponents.wxs"

# wix v4 ships heat as `wix harvest` (still XML-only output).
& wix harvest dir $distDir `
    -componentgroup HarvestedComponents `
    -directoryref INSTALLFOLDER `
    -srd `
    -gg `
    -sfrag `
    -var var.HarvestSource `
    -out $harvestedWxs

if (-not (Test-Path -LiteralPath $harvestedWxs)) {
    throw "[build] wix harvest did not produce $harvestedWxs"
}

# Filter exclusions out of the heat output by deleting any <File>/<Component>
# nodes whose Source attribute matches an exclusion glob. Use PowerShell XML.
$exclusions = Get-Content "$wixDir\heat-exclusions.txt" | Where-Object {
    $_ -and -not $_.StartsWith("#")
}
[xml]$harvestXml = Get-Content -LiteralPath $harvestedWxs
$ns = New-Object Xml.XmlNamespaceManager($harvestXml.NameTable)
$ns.AddNamespace("w", "http://wixtoolset.org/schemas/v4/wxs")
$nodesToRemove = @()
foreach ($fileNode in $harvestXml.SelectNodes("//w:File", $ns)) {
    foreach ($pattern in $exclusions) {
        if ($fileNode.Source -like "*$pattern*") {
            $nodesToRemove += $fileNode.ParentNode  # remove the enclosing Component
            break
        }
    }
}
foreach ($node in ($nodesToRemove | Select-Object -Unique)) {
    $node.ParentNode.RemoveChild($node) | Out-Null
}
$harvestXml.Save($harvestedWxs)
Write-Host "[build] heat ok ($($nodesToRemove.Count) components excluded)"

# --- Step 4: wix build -> MSI -------------------------------------------------

$msiName = "Locksmith-$Version.msi"
$msiPath = Join-Path $buildDir $msiName
Write-Host "[build] linking $msiPath"

Push-Location $wixDir
try {
    & wix build "Locksmith.wxs" $harvestedWxs `
        -ext WixToolset.UI.wixext `
        -arch x64 `
        -define "Version=$Version" `
        -define "HarvestSource=$distDir" `
        -out $msiPath
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $msiPath)) {
    throw "[build] wix build did not produce $msiPath"
}
Write-Host "[build] wix ok msi=$msiPath"

# --- Step 5: Sign the MSI -----------------------------------------------------

if (-not $SkipSign) {
    Write-Host "[build] signing $msiPath"
    & pwsh "$packagingDir\sign-windows.ps1" -Path $msiPath -Description "Locksmith Installer"
} else {
    Write-Host "[build] -SkipSign set; leaving $msiPath unsigned"
}

# --- Step 6: Final verify -----------------------------------------------------

if (-not $SkipSign) {
    Write-Host "[build] running signtool verify /pa /v $msiPath"
    & signtool verify /pa /v $msiPath
    if ($LASTEXITCODE -ne 0) {
        throw "[build] final signtool verify failed (exit $LASTEXITCODE)"
    }
}

Write-Host "[build] done"
Write-Host "[build] artifact=$msiPath version=$Version"
```

- [ ] **Step 2: Commit**

```bash
git add packaging/build-windows.ps1
git commit -m "feat(packaging): build-windows.ps1 orchestrates PyInstaller + WiX + signing"
```

---

## Task 9: Integration test — PyInstaller smoke (Windows-only)

We want a test that, on a Windows runner, actually runs PyInstaller end-to-end and exercises the bundled `Locksmith.exe --self-test`. This is the only way to catch hidden-import regressions.

**Files:**
- Create: `tests/integration/test_pyinstaller_windows.py`

- [ ] **Step 1: Write the test**

Create `tests/integration/test_pyinstaller_windows.py`:

```python
"""End-to-end integration test for the Windows PyInstaller bundle.

Runs PyInstaller against packaging/Locksmith.windows.spec, then launches
the resulting Locksmith.exe with --self-test and asserts a clean exit.

Skipped on non-Windows. Skipped if SKIP_HEAVY_INTEGRATION=1.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "packaging" / "Locksmith.windows.spec"
EXPECTED_EXE = REPO_ROOT / "dist" / "Locksmith" / "Locksmith.exe"

pytestmark = [
    pytest.mark.skipif(platform.system() != "Windows",
                       reason="Windows-only PyInstaller integration"),
    pytest.mark.skipif(os.environ.get("SKIP_HEAVY_INTEGRATION") == "1",
                       reason="SKIP_HEAVY_INTEGRATION=1 set"),
]


@pytest.fixture(scope="module")
def pyinstaller_bundle():
    """Run PyInstaller once; share the resulting dist tree across tests."""
    # Clean any stale build
    if (REPO_ROOT / "dist" / "Locksmith").exists():
        shutil.rmtree(REPO_ROOT / "dist" / "Locksmith")
    if (REPO_ROOT / "build" / "Locksmith").exists():
        shutil.rmtree(REPO_ROOT / "build" / "Locksmith")

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)]
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"PyInstaller failed:\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    assert EXPECTED_EXE.is_file(), f"expected {EXPECTED_EXE}, got missing"
    return EXPECTED_EXE


def test_bundled_exe_runs_self_test(pyinstaller_bundle):
    """Locksmith.exe --self-test exits 0 and prints a version line."""
    result = subprocess.run(
        [str(pyinstaller_bundle), "--self-test"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"self-test failed:\n--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    assert "locksmith self-test ok" in result.stdout.lower()


def test_bundled_exe_contains_internal_dir(pyinstaller_bundle):
    """PyInstaller's onedir layout puts deps under _internal/."""
    internal = pyinstaller_bundle.parent / "_internal"
    assert internal.is_dir(), f"missing {internal}"
    # PySide6 must be present.
    assert any(internal.rglob("PySide6")), "PySide6 not found in bundle"


def test_bundled_exe_has_no_pycache(pyinstaller_bundle):
    """No __pycache__ should leak into the dist directory."""
    pycache_hits = list(pyinstaller_bundle.parent.rglob("__pycache__"))
    assert not pycache_hits, f"found stray __pycache__: {pycache_hits[:3]}"
```

- [ ] **Step 2: Run on a non-Windows dev host to confirm it skips**

Run: `pytest tests/integration/test_pyinstaller_windows.py -v`
Expected: 3 tests SKIPPED on macOS/Linux (skipif applies).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_pyinstaller_windows.py
git commit -m "test(packaging): Windows PyInstaller bundle integration test"
```

---

## Task 10: Integration test — WiX authoring lint

We want a static check that the wxs is well-formed XML and references the upgrade-code GUID consistently. We **don't** invoke `wix build` here (that requires the dotnet toolchain and is exercised in CI).

**Files:**
- Create: `tests/integration/test_wix_authoring.py`

- [ ] **Step 1: Write the test**

Create `tests/integration/test_wix_authoring.py`:

```python
"""Lint checks for packaging/wix/Locksmith.wxs.

Static-only — does not invoke the wix CLI. The end-to-end MSI build is
exercised in CI on a Windows runner.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WXS = REPO_ROOT / "packaging" / "wix" / "Locksmith.wxs"
LICENSE_RTF = REPO_ROOT / "packaging" / "wix" / "license.rtf"
BANNER = REPO_ROOT / "packaging" / "wix" / "banner.png"
DIALOG = REPO_ROOT / "packaging" / "wix" / "dialog.png"
HEAT_EXCLUSIONS = REPO_ROOT / "packaging" / "wix" / "heat-exclusions.txt"

NS = {
    "w": "http://wixtoolset.org/schemas/v4/wxs",
    "ui": "http://wixtoolset.org/schemas/v4/wxs/ui",
}


@pytest.fixture(scope="module")
def wxs_tree():
    return ET.parse(WXS)


def test_wxs_is_well_formed(wxs_tree):
    root = wxs_tree.getroot()
    assert root.tag.endswith("}Wix"), f"unexpected root: {root.tag}"


def test_package_has_perUser_scope(wxs_tree):
    pkg = wxs_tree.find("w:Package", NS)
    assert pkg is not None, "no Package element"
    assert pkg.attrib.get("Scope") == "perUser", f"Scope={pkg.attrib.get('Scope')}"


def test_upgrade_code_is_immutable_guid(wxs_tree):
    pkg = wxs_tree.find("w:Package", NS)
    upgrade_code = pkg.attrib.get("UpgradeCode", "")
    # Must be a real GUID — not the placeholder.
    assert upgrade_code != "<UPGRADE_GUID>", (
        "UpgradeCode is still the placeholder — generate a real GUID and commit it"
    )
    # uuid.UUID raises on malformed.
    parsed = uuid.UUID(upgrade_code)
    assert str(parsed).upper() == upgrade_code.upper(), "UpgradeCode case-canonical mismatch"


def test_version_uses_variable(wxs_tree):
    pkg = wxs_tree.find("w:Package", NS)
    assert pkg.attrib.get("Version") == "$(var.Version)", (
        "Version should be the WiX variable, not hardcoded"
    )


def test_install_path_is_localappdata(wxs_tree):
    set_prop = wxs_tree.find(".//w:SetProperty[@Id='INSTALLFOLDER']", NS)
    assert set_prop is not None, "INSTALLFOLDER SetProperty missing"
    value = set_prop.attrib.get("Value", "")
    assert "LocalAppDataFolder" in value, f"install path does not use LocalAppDataFolder: {value}"


def test_major_upgrade_block_present(wxs_tree):
    major = wxs_tree.find(".//w:MajorUpgrade", NS)
    assert major is not None, "MajorUpgrade element missing"
    assert major.attrib.get("AllowSameVersionUpgrades") == "yes"


def test_referenced_files_exist():
    assert LICENSE_RTF.is_file(), f"missing {LICENSE_RTF}"
    assert BANNER.is_file(), f"missing {BANNER}"
    assert DIALOG.is_file(), f"missing {DIALOG}"


def test_heat_exclusions_present_and_nontrivial():
    assert HEAT_EXCLUSIONS.is_file()
    lines = [
        ln.strip() for ln in HEAT_EXCLUSIONS.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert "__pycache__" in lines
    assert "*.pyc" in lines


def test_no_hardcoded_changeme_strings():
    text = WXS.read_text(encoding="utf-8")
    assert "CHANGEME" not in text.upper()
    assert "com.CHANGEME" not in text
```

- [ ] **Step 2: Run test — should PASS once Task 6 is committed**

Run: `pytest tests/integration/test_wix_authoring.py -v`
Expected: 9 tests PASS (will fail if the placeholder GUID was not replaced).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_wix_authoring.py
git commit -m "test(packaging): static lint for Locksmith.wxs"
```

---

## Task 11: Rewrite `.github/workflows/release.ci.yml` Windows job

Replace the stubbed `build-windows` job at the bottom of the workflow with a real PyInstaller + WiX + AzTS + S3 pipeline. We do **not** touch the macOS job here — Phase 2 owns that.

**Files:**
- Modify: `.github/workflows/release.ci.yml` (replace lines 137–207, the entire `build-windows` job)

- [ ] **Step 1: Replace the Windows job**

In `.github/workflows/release.ci.yml`, delete the existing `build-windows:` job (lines 137 to end) and replace it with:

```yaml
  build-windows:
    runs-on: windows-latest
    # OIDC permissions for AWS auth (no long-lived keys).
    permissions:
      id-token: write
      contents: read

    env:
      LOCKSMITH_RELEASE_CHANNEL: stable

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python 3.14
        uses: actions/setup-python@v5
        with:
          python-version: '3.14'

      - name: Set version variable
        id: set_version
        shell: pwsh
        run: |
          $version = "${{ github.event.release.tag_name }}"
          if ($version.StartsWith("v")) { $version = $version.Substring(1) }
          echo "version=$version" >> $env:GITHUB_OUTPUT
          echo "LOCKSMITH_VERSION=$version" >> $env:GITHUB_ENV

      - name: Verify pyproject version matches release tag
        shell: pwsh
        run: |
          $pyprojectVersion = (& python packaging/version-from-pyproject.py).Trim()
          $tagVersion = "${{ steps.set_version.outputs.version }}"
          if ($pyprojectVersion -ne $tagVersion) {
              throw "version skew: pyproject=$pyprojectVersion tag=$tagVersion"
          }

      - name: Install Python build dependencies
        shell: pwsh
        run: |
          python -m pip install --upgrade pip
          python -m pip install setuptools wheel
          python -m pip install pyinstaller==6.11.1
          python -m pip install -e .

      - name: Install libsodium DLL
        shell: pwsh
        run: |
          choco install libsodium --version=1.0.20 --no-progress -y
          # libsodium.dll is dropped into C:\ProgramData\chocolatey\lib\libsodium\tools
          # add to PATH so PyInstaller's binary collection sees it.
          $sodiumDir = "C:\ProgramData\chocolatey\lib\libsodium\tools"
          echo $sodiumDir >> $env:GITHUB_PATH

      - name: Install WiX Toolset v4
        shell: pwsh
        run: |
          dotnet tool install --global wix --version 4.0.5
          # Verify on PATH
          & wix --version

      - name: Install WiX UI extension
        shell: pwsh
        run: |
          & wix extension add -g WixToolset.UI.wixext

      - name: Install AzureSignTool
        shell: pwsh
        run: |
          dotnet tool install --global AzureSignTool --version 6.0.0
          & AzureSignTool --version

      - name: Azure login (OIDC, federated credential for Trusted Signing)
        uses: azure/login@v2
        with:
          tenant-id:       ${{ secrets.AZURE_TENANT_ID }}
          client-id:       ${{ secrets.AZURE_CLIENT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Set Trusted Signing env vars
        shell: pwsh
        run: |
          echo "AZURE_TENANT_ID=${{ secrets.AZURE_TENANT_ID }}"                           >> $env:GITHUB_ENV
          echo "AZURE_CLIENT_ID=${{ secrets.AZURE_CLIENT_ID }}"                           >> $env:GITHUB_ENV
          echo "AZURE_SUBSCRIPTION_ID=${{ secrets.AZURE_SUBSCRIPTION_ID }}"               >> $env:GITHUB_ENV
          echo "AZURE_TRUSTED_SIGNING_ENDPOINT=${{ secrets.AZURE_TRUSTED_SIGNING_ENDPOINT }}" >> $env:GITHUB_ENV
          echo "AZURE_TRUSTED_SIGNING_ACCOUNT_NAME=${{ secrets.AZURE_TRUSTED_SIGNING_ACCOUNT_NAME }}" >> $env:GITHUB_ENV
          echo "AZURE_TRUSTED_SIGNING_CERTIFICATE_PROFILE_NAME=${{ secrets.AZURE_TRUSTED_SIGNING_CERTIFICATE_PROFILE_NAME }}" >> $env:GITHUB_ENV

      - name: Build, sign, and link MSI
        shell: pwsh
        run: |
          pwsh packaging/build-windows.ps1 -Version "${{ steps.set_version.outputs.version }}"

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_RELEASE_PUBLISHER_ROLE_ARN }}
          aws-region: us-east-1

      - name: Upload MSI to releases.keri.host
        shell: pwsh
        env:
          VERSION: ${{ steps.set_version.outputs.version }}
        run: |
          $msi = "build/windows/Locksmith-$env:VERSION.msi"
          if (-not (Test-Path -LiteralPath $msi)) {
              throw "MSI not found at $msi"
          }
          $key = "releases/$env:VERSION/Locksmith-$env:VERSION.msi"
          aws s3 cp $msi "s3://releases.keri.host/$key" `
              --content-type "application/x-msi" `
              --cache-control "public, max-age=31536000, immutable"
          Write-Host "[upload] ok s3://releases.keri.host/$key"

      - name: Capture MSI artifact (for downstream anchor-release job)
        uses: actions/upload-artifact@v4
        with:
          name: Locksmith-${{ steps.set_version.outputs.version }}-msi
          path: build/windows/Locksmith-${{ steps.set_version.outputs.version }}.msi
          retention-days: 7
```

- [ ] **Step 2: Verify YAML parses**

Run on any host:
```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.ci.yml'))" && echo OK
```
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.ci.yml
git commit -m "ci(release): rewrite Windows job to use PyInstaller + WiX + AzTS + S3"
```

---

## Task 12: Drop the macOS job's DigitalOcean upload references that the Phase-1 spec replaces

The macOS job currently still uploads to DigitalOcean Spaces using `SPACES_*` secrets. Phase 2 owns the macOS rewrite, but the **Windows job** above no longer touches `scripts/upload.py`, so we should make sure leftover references don't break the lint we just added.

This is a no-op check task — we leave the macOS job's DigitalOcean upload alone (Phase 2 will rewrite it). We only verify the file still parses.

- [ ] **Step 1: Lint the full workflow**

Run:
```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.ci.yml'))" && echo OK
```
Expected: `OK`.

- [ ] **Step 2: No commit needed**

If parse succeeds, no commit is needed for this task. If it fails, fix the YAML before continuing.

---

## Task 13: Signing setup runbook (`docs/development/windows-signing-setup.md`)

One-time-ops doc. The implementer ran this once already (or will, before the first release). It belongs in the repo so the second engineer can reproduce it.

**Files:**
- Create: `docs/development/windows-signing-setup.md`

- [ ] **Step 1: Write the runbook**

Create `docs/development/windows-signing-setup.md`:

```markdown
# Windows Code Signing — One-Time Setup

This runbook captures the one-time operations needed to enable Azure Trusted
Signing for the Locksmith Windows release pipeline. After you've completed
this once for the KERI.host publishing entity, you should never need to
touch it again except during annual identity revalidation.

## Background

We sign `Locksmith.exe` and `Locksmith-X.Y.Z.msi` via **Azure Trusted Signing**
(AzTS). AzTS is Microsoft's managed code-signing service: certificates are
short-lived (72h), issued by a Microsoft-operated CA, and never exposed to
the signing client. SmartScreen reputation accrues to the *publisher identity*
(KERI.host) and persists across cert reissuance.

Pricing: ~$10/month base + $0.005/signature. At our release cadence this is
under $15/month.

## Prerequisites

1. An Azure subscription owned by the KERI.host entity (or by the user
   pending non-profit incorporation — switch the subscription owner over
   when KERI.host incorporates).
2. Microsoft Entra ID (Azure AD) tenant.
3. Access to set GitHub Actions secrets on `seriouscoderone/locksmith`.

## Step 1 — Create the Trusted Signing account

1. In the Azure Portal: **Create resource → Trusted Signing Account**.
2. Resource group: `keri-host-signing-rg` (create new).
3. Region: `East US` (the AzTS endpoint we'll use is `https://eus.codesigning.azure.net/`).
4. Account name: `keri-host-signing`.
5. Pricing tier: **Basic** (sufficient for our volume; can upgrade later).
6. Click **Review + Create**, then **Create**.

## Step 2 — Identity validation

This is the slowest step (24–72h for Microsoft to verify).

1. In the new Trusted Signing account → **Identity Validation** → **New identity**.
2. Validation type: **Public** (this is what populates the "Verified Publisher"
   field SmartScreen reads).
3. Identity type: **Organization** (or **Individual** until KERI.host incorporates,
   then re-validate as Organization).
4. Provide:
   - Legal name: **KERI.host** (or your legal name pending incorporation)
   - Address, phone, contact email
   - Website: `https://locksmith.app` and/or `https://keri.host`
   - Business registration documents (or government ID for Individual)
5. Submit. You'll receive an email when validation completes.

While you wait, you can continue to Step 3 (the certificate profile can be
created before validation completes, but cannot **issue** until validation
is approved).

## Step 3 — Certificate profile

1. In the Trusted Signing account → **Certificate Profiles** → **New profile**.
2. Profile name: `locksmith-release`.
3. Identity validation: select the one created in Step 2.
4. Certificate type: **Public Trust** (Code Signing).
5. Include code-signing EKU: **Yes**.
6. Save.

## Step 4 — Microsoft Entra ID app registration for GitHub OIDC

We do NOT use a long-lived service principal secret. We use federated
credentials so GitHub Actions can OIDC-exchange a token from
`token.actions.githubusercontent.com` for an Azure access token.

1. Entra ID → **App registrations** → **New registration**.
2. Name: `locksmith-release-signing-gha`.
3. Supported account types: single tenant.
4. Redirect URI: leave blank.
5. Register.
6. Note the **Application (client) ID** and **Directory (tenant) ID**.

### Federated credential

1. In the app registration → **Certificates & secrets** → **Federated credentials**
   → **Add credential**.
2. Scenario: **GitHub Actions deploying Azure resources**.
3. Organization: `seriouscoderone` (or the GitHub org once we move).
4. Repository: `locksmith`.
5. Entity type: **Environment** → `release` (we'll gate signing on this
   environment) **or** **Branch** → `main` if we don't use environments yet.
   Recommend **Environment** for production gating.
6. Name: `gha-release`.
7. Audience: `api://AzureADTokenExchange` (default).
8. Save.

### Grant signing permissions

1. In the Trusted Signing account → **Access control (IAM)** → **Add role assignment**.
2. Role: **Trusted Signing Certificate Profile Signer**.
3. Scope: the certificate profile created in Step 3.
4. Assign to: the app registration from Step 4 (`locksmith-release-signing-gha`).
5. Save.

## Step 5 — Configure GitHub Actions secrets

Set the following repository secrets (Repo → Settings → Secrets and variables
→ Actions → New repository secret):

| Secret | Value |
|---|---|
| `AZURE_TENANT_ID` | Directory (tenant) ID from Step 4 |
| `AZURE_CLIENT_ID` | Application (client) ID from Step 4 |
| `AZURE_SUBSCRIPTION_ID` | The Azure subscription ID owning the Trusted Signing account |
| `AZURE_TRUSTED_SIGNING_ENDPOINT` | `https://eus.codesigning.azure.net/` (or your region) |
| `AZURE_TRUSTED_SIGNING_ACCOUNT_NAME` | `keri-host-signing` |
| `AZURE_TRUSTED_SIGNING_CERTIFICATE_PROFILE_NAME` | `locksmith-release` |

If you used an environment gate (Step 4, recommended), set these on the
**`release` environment**, not the repository. Then the build-windows job
must declare `environment: release`.

### AWS OIDC secret (Phase 1 provisions this)

| Secret | Value |
|---|---|
| `AWS_RELEASE_PUBLISHER_ROLE_ARN` | ARN of the IAM role created by Phase 1 |

## Step 6 — First successful signing run

1. Cut a test release tag (e.g., `v0.0.1-rc1`).
2. Trigger the workflow.
3. Watch the `build-windows` job log; look for `[sign] ok` lines.
4. Download the produced MSI from S3 and right-click → **Properties** →
   **Digital Signatures**. You should see one signature from
   "KERI.host" (or your identity), countersigned with a Microsoft RFC3161
   timestamp.

## Step 7 — Annual revalidation

Microsoft requires identity revalidation every ~12 months. AzTS emails you
60 days before expiry. Repeat Step 2 with the same identity.

## Troubleshooting

**`AzureSignTool: 401 Unauthorized`** — federated credential mismatch.
Confirm the GitHub repo, branch/environment, and audience match the
federated credential exactly. The subject claim in the GitHub OIDC token
must match the federated credential's subject pattern.

**`The specified certificate profile is not authorized for signing`** —
the app registration is missing the **Trusted Signing Certificate Profile
Signer** role on the profile. Re-check Step 4 → "Grant signing permissions".

**`Identity validation status: Pending`** — the certificate profile cannot
sign until Step 2's validation is **Completed**.
```

- [ ] **Step 2: Commit**

```bash
git add docs/development/windows-signing-setup.md
git commit -m "docs(packaging): Azure Trusted Signing one-time setup runbook"
```

---

## Task 14: Smoke-test runbook (`docs/development/windows-build-smoke-test.md`)

A short manual checklist a human runs on a clean Windows 11 VM before each release. The integration test catches "does it bundle"; the smoke test catches "does it feel right".

**Files:**
- Create: `docs/development/windows-build-smoke-test.md`

- [ ] **Step 1: Write the runbook**

Create `docs/development/windows-build-smoke-test.md`:

```markdown
# Windows Build Smoke Test

Run this checklist on a clean Windows 11 VM **before every public release**.
This catches UX issues the integration tests can't catch (console flashes,
SmartScreen wording, Add/Remove Programs entry quality).

## Setup

1. Provision a clean Windows 11 VM. Hyper-V, Parallels, VMware Fusion, or
   UTM all work. Allocate at least 4GB RAM and 40GB disk.
2. **Do not** install any developer tools on the VM. We want this to look
   like a real user's machine.
3. Take a snapshot before installing Locksmith so you can revert.

## Acquiring the MSI

- Production release: download from
  `https://releases.keri.host/releases/X.Y.Z/Locksmith-X.Y.Z.msi`.
- Local build: copy `build\windows\Locksmith-X.Y.Z.msi` from the dev
  machine to the VM via a shared folder.

## Checklist

### Signature

- [ ] Right-click the MSI → **Properties** → **Digital Signatures** tab is
      present.
- [ ] Signature is from **KERI.host** (or the validated identity).
- [ ] **Countersignature** lists a Microsoft RFC3161 timestamp authority.
- [ ] **Details** → **View Certificate** shows a valid, non-expired cert
      issued by the Microsoft ID Verified CS Authority.

### Install UX

- [ ] Double-click the MSI. **No UAC prompt** appears (per-user install).
- [ ] The Welcome dialog shows the Locksmith banner image at the top.
- [ ] The License dialog renders the license text correctly (no garbled
      characters).
- [ ] The Install Location dialog defaults to
      `%LOCALAPPDATA%\Programs\Locksmith\` (the dialog displays the expanded
      path).
- [ ] Optional Desktop shortcut checkbox is present and checked by default.
- [ ] Clicking Install completes in under 30 seconds with a smooth
      progress bar (no console window flashes).
- [ ] **Finish dialog** offers a "Launch Locksmith" checkbox; ticking it
      launches the app cleanly.

### First launch

- [ ] Locksmith window opens. **No console window flashes** before or after.
- [ ] Window title is "Locksmith" and the icon in the taskbar is the
      multi-resolution icon (sharp at all sizes — not blurry).
- [ ] No error dialogs about missing DLLs, Qt plugins, or libsodium.
- [ ] Open Task Manager → Details. `Locksmith.exe` is running. No child
      `cmd.exe` or `python.exe` processes are visible.

### Shortcuts

- [ ] Start Menu → "Locksmith" entry is present under its own folder.
- [ ] Start Menu → typing "Locksmith" finds it in search.
- [ ] Desktop shortcut is present (if installed).
- [ ] Both shortcuts launch the same `Locksmith.exe`.
- [ ] Shortcut icon is the multi-resolution app icon (not the generic MSI
      icon).

### Add/Remove Programs

- [ ] Settings → Apps → Installed apps. Find "Locksmith".
- [ ] The entry shows:
      - Publisher: **KERI.host**
      - Size: a real number (not "0 bytes")
      - Version: **X.Y.Z** (matches the release)
- [ ] Clicking the "..." menu shows only **Uninstall** (no Modify, no Repair
      — we set ARPNOREPAIR/ARPNOMODIFY).
- [ ] **Uninstall** prompts no UAC. Completes cleanly in under 15 seconds.

### Post-uninstall

- [ ] `%LOCALAPPDATA%\Programs\Locksmith\` is gone.
- [ ] Start Menu "Locksmith" folder is gone.
- [ ] Desktop shortcut is gone.
- [ ] HKCU\Software\KERI.host\Locksmith is gone (use regedit).
- [ ] Locksmith no longer appears in Add/Remove Programs.

### Reinstall idempotency

- [ ] Reinstall the same MSI immediately. Install succeeds (no "already
      installed" error).
- [ ] Open the MSI when Locksmith is already running. Either the installer
      prompts to close Locksmith or it queues for next reboot — **never**
      silently overwrites a running EXE.

## If something fails

File an issue at https://github.com/seriouscoderone/locksmith/issues with:

- The release version (X.Y.Z)
- Which checklist item failed
- A screenshot or screen recording
- The contents of `%LOCALAPPDATA%\Locksmith\logs\` if any logs exist
- The Windows event log entries from "Application" around the time of failure
```

- [ ] **Step 2: Commit**

```bash
git add docs/development/windows-build-smoke-test.md
git commit -m "docs(packaging): Windows clean-VM smoke-test runbook"
```

---

## Task 15: Final cross-cutting wire-up — verify spec-level acceptance

We've shipped all the deliverables. This task is a fresh-eyes review against Phase 3's deliverables list in the task brief.

- [ ] **Step 1: Re-read the spec section §5.3 (Windows pipeline)**

Open `docs/superpowers/specs/2026-05-28-locksmith-deploy-update-design.md` and re-read §5.3. Confirm each numbered step has a corresponding task:

| Spec step | Implemented in |
|---|---|
| 1. PyInstaller → `dist/Locksmith/` | Task 4 (spec) + Task 8 (build orchestrator step 1) |
| 2. WiX `heat`/`candle`/`light` | Task 5 (exclusions) + Task 6 (wxs) + Task 8 (orchestrator steps 3–4) |
| 3. `Locksmith.exe` signed before MSI authoring | Task 8 step 2 (signs exe BEFORE heat harvest) |
| 4. MSI signed via `Azure/trusted-signing-action` | Task 7 (wrapper) + Task 8 step 5 + Task 11 (CI uses same wrapper) |
| 5. Output: signed MSI | Task 8 final artifact + Task 11 S3 upload |

- [ ] **Step 2: Re-read Phase 3 brief deliverables**

Walk down the 7 deliverable groups from the task brief and confirm coverage:

1. PyInstaller spec ✓ Task 4
2. WiX authoring ✓ Tasks 5, 6
3. heat exclusions ✓ Task 5
4. build orchestration ✓ Tasks 7, 8
5. CI updates ✓ Task 11
6. Signing setup doc ✓ Task 13
7. Testing (unit + integration + smoke runbook) ✓ Tasks 1, 2, 3, 9, 10, 14

- [ ] **Step 3: Final sanity run of all unit + lint-level tests**

Run (on macOS dev host — Windows-only tests will skip):
```bash
pytest tests/unit/test_version_from_pyproject.py \
       tests/unit/test_main_self_test_flag.py \
       tests/unit/test_generate_windows_assets.py \
       tests/integration/test_wix_authoring.py \
       tests/integration/test_pyinstaller_windows.py \
       -v
```
Expected: 8+ tests PASS, 3 SKIPPED (the Windows-only PyInstaller integration), 0 failures.

- [ ] **Step 4: Confirm clean working tree**

Run:
```bash
git status
```
Expected: `nothing to commit, working tree clean`.

- [ ] **Step 5: Push the feature branch**

```bash
git push -u origin feat/deploy-phase3-windows
```

The branch is now ready for review. Open a draft PR titled
`feat(deploy): phase 3 — Windows build + signing + manual release` linking
this plan and the parent spec.

---

## Self-Review Notes

Self-review was performed against the spec (`docs/superpowers/specs/2026-05-28-locksmith-deploy-update-design.md` §5.3, §11.1) and the Phase 3 task brief. Key checks:

1. **Spec coverage:**
   - §5.3 (Windows pipeline): all five sub-steps mapped (Task 15 step 1).
   - §11.1 migration table: `Compress-Archive` and DigitalOcean Spaces upload are deleted in Task 11; `com.CHANGEME.locksmith` is replaced with `host.keri.locksmith` in Task 6 (no hardcoded ID strings remain in any new file).
   - §6.1 S3 path `releases/{version}/Locksmith-{version}.msi`: matches Task 11's upload step.
   - §2 non-goals: no MDM, no per-machine install — confirmed in Task 6 (`Scope="perUser"`).

2. **Placeholder scan:** No `TBD`, `TODO`, or "implement later" markers. The `<UPGRADE_GUID>` placeholder in Task 6 step 3 is **explicitly called out** in Task 6 step 2 with instructions to generate a real GUID before commit, and the WiX lint test (Task 10) **fails** if the placeholder is still present — so the placeholder cannot leak past commit.

3. **Type consistency:** Variable names matched across tasks (`LOCKSMITH_VERSION`, `LOCKSMITH_RELEASE_CHANNEL`, `INSTALLFOLDER`, `HarvestedComponents`, `LocksmithIcon`).

4. **Cross-phase dependencies:**
   - Task 2's `--self-test` flag tries to load `locksmith.release.publisher_anchor.json` (a Phase 1 artifact) but **gracefully falls back** to `anchor not_embedded` if absent — so Phase 3 can ship before Phase 1 lands without breaking the integration test.
   - Task 11 references `secrets.AWS_RELEASE_PUBLISHER_ROLE_ARN` from Phase 1 — if Phase 1 isn't merged yet, the CI job will fail at the AWS-auth step, but PyInstaller + WiX + signing will succeed; the build artifact will still exist as a workflow artifact (`actions/upload-artifact`).
   - Phase 5 (WinSparkle) install layout is documented in Task 6 (`%LOCALAPPDATA%\Programs\Locksmith\`).

5. **Test design:** Each task has a real failing-first test where one is meaningful (Tasks 1, 2, 3, 9, 10). Tasks 4–8, 11, 13, 14 produce config/script/docs where the verification step is "lints / parses / has expected structure" rather than "passes a behavioral test"; this matches the spec's testing-strategy doctrine for build infrastructure (§10.2 covers integration; smoke runbook covers UX-only checks). The Windows-only PyInstaller test (Task 9) is the load-bearing E2E check and runs on `windows-latest` in CI.
