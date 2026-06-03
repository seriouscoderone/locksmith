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
    ["src/locksmith/main.py"],
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
