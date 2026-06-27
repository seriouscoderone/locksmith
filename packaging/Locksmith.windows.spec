# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Windows — produces dist/Locksmith/Locksmith.exe.

Phase 3 of the deploy/update design. Bundles libsodium.dll, the assets
directory, qtawesome icon fonts, and the embedded publisher_anchor.json.

Version is read from pyproject.toml so we maintain a single source of truth
(spec §5.1, §5.5).

Layout:
    dist/Locksmith/Locksmith.exe       (entry exe; no console)
    dist/Locksmith/_internal/          (PySide6/Qt/qtawesome/keri deps)
    dist/Locksmith/_internal/libsodium.dll
    dist/Locksmith/_internal/assets/
"""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

import qtawesome  # noqa: F401 — bundling its data only

# ---- Resolve paths -------------------------------------------------------
# Use SPECPATH-relative absolute paths: PyInstaller resolves Analysis script
# paths relative to SPECPATH (not CWD), so any "src/..." relative would look
# inside packaging/ and fail.
REPO_ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 — SPECPATH injected
SRC_ROOT = REPO_ROOT / "src"
ASSETS = REPO_ROOT / "assets"
WIN_ICON = ASSETS / "custom" / "AppIcon.ico"

import sys as _sys
_sys.path.insert(0, str(REPO_ROOT / "packaging"))
import brandlib as _brandlib
_BRAND = _brandlib.load_brand_manifest()
_BRAND_NAME = _BRAND["brand"]["display_name"]

# ---- Read version --------------------------------------------------------

with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
    _pyproject = tomllib.load(fh)
LOCKSMITH_VERSION = _pyproject["project"]["version"]
LOCKSMITH_RELEASE_CHANNEL = os.environ.get("LOCKSMITH_RELEASE_CHANNEL", "stable")

# ---- Discover qtawesome fonts directory ----------------------------------

import qtawesome as _qta_mod
_QTA_DIR = Path(_qta_mod.__file__).resolve().parent
_QTA_FONTS = _QTA_DIR / "fonts"

# ---- Datas: non-code resources bundled into the dist tree ----------------

datas = [
    # Application asset tree (icons, fonts, mock data, etc.)
    (str(ASSETS), "assets"),
    # Embedded KERI publisher trust anchor (Phase 1 placeholder/real)
    (
        str(SRC_ROOT / "locksmith" / "release" / "publisher_anchor.json"),
        "locksmith/release",
    ),
    # Deploy config (federation/CDN domains). Build-injected + gitignored like
    # the anchor; REQUIRED at runtime so the in-app verify gate can fetch the
    # real appcast/KEL — without it the gate falls back to example.com and the
    # KERI verify cannot run.
    (
        str(SRC_ROOT / "locksmith" / "release" / "deploy_config.json"),
        "locksmith/release",
    ),
    # qtawesome icon fonts (needed at runtime; not auto-collected reliably)
    (str(_QTA_FONTS), "qtawesome/fonts"),
]

# ---- Binaries: native libs ----------------------------------------------
# libsodium.dll is installed via choco in CI and copied into packaging/windows/
# before pyinstaller runs (see build-windows.ps1 / release.ci.yml). The
# bootstrap loader in src/locksmith/main.py points pysodium at this DLL via
# ctypes.util.find_library monkey-patch.
binaries = []
_SODIUM_DLL = REPO_ROOT / "packaging" / "windows" / "libsodium.dll"
if _SODIUM_DLL.is_file():
    # Place at root of bundle so the loader's first candidate path resolves.
    binaries.append((str(_SODIUM_DLL), "."))
else:
    print(f"[spec] WARNING: {_SODIUM_DLL} not present; build will fail at runtime "
          "without a bundled libsodium.dll. CI's 'Stage libsodium for PyInstaller' "
          "step copies it into place before pyinstaller runs.")

# WinSparkle.dll — bundled next to Locksmith.exe so the ctypes loader in
# locksmith.update.winsparkle_bridge finds it as `WinSparkle.dll`. The
# release CI step "Fetch WinSparkle" downloads it from
# https://github.com/vslavik/winsparkle/releases (0.8+ line) into
# packaging/windows/winsparkle/ before invoking PyInstaller.
#
# Runtime appcast URL: https://releases.keri.host/appcast/v1/windows.xml
# (brand-derived by winsparkle_init._appcast_url via win_sparkle_set_appcast_url).
# WinSparkle's native DSA verification is DISABLED at runtime
# (win_sparkle_set_dsa_pub_pem(NULL)) — KERI is sole trust (spec §3).
_WINSPARKLE_DLL = REPO_ROOT / "packaging" / "windows" / "winsparkle" / "WinSparkle.dll"
if _WINSPARKLE_DLL.is_file():
    binaries.append((str(_WINSPARKLE_DLL), "."))
else:
    print(f"[spec] WARNING: {_WINSPARKLE_DLL} not present; bundle will ship "
          "without in-app updates. CI's 'Fetch WinSparkle' step copies "
          "WinSparkle.dll into place before pyinstaller runs.")

# ---- Hidden imports ------------------------------------------------------
#
# Mirror the macOS spec's pinned list. Add to this list with a one-line
# comment ONLY when a runtime ImportError proves the dependency is needed.
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
    [str(SRC_ROOT / "locksmith" / "main.py")],
    pathex=[str(SRC_ROOT)],
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

# NOTE: no PyInstaller Splash() here. Its Tcl/Tk splash can't run inside a macOS
# .app (so the splash was absent there) and DPI-rescales on Windows (the splash
# "moves and shrinks"). The app now shows a Qt QSplashScreen from main.py
# (_make_splash) on every platform — DPI-correct and consistent. SplashScreen.png
# ships in the bundled assets/ tree, which main.py loads at runtime.

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=_BRAND_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX-compressed binaries fail Authenticode signing
    console=False,       # GUI app — no terminal window flash
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(WIN_ICON) if WIN_ICON.is_file() else None,
    version_file=None,   # MSI carries the version metadata
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=_BRAND_NAME,
)
