#!/usr/bin/env bash
#
# scripts/devbuild-macos.sh — LOCAL unsigned .app for Sparkle update-dialog iteration
#
# Usage:
#   ./scripts/devbuild-macos.sh [VERSION]
#
#   VERSION defaults to "0.0.0-dev" when omitted.
#
# Produces: dist/Locksmith.app (unsigned, no DMG, no notarization)
# Launch:   dist/Locksmith.app/Contents/MacOS/Locksmith
#
# -----------------------------------------------------------------------
# VERSION-OVERRIDE NOTE
# -----------------------------------------------------------------------
# build-macos.sh's mechanism:
#   1. Reads the version from pyproject.toml.
#   2. Rewrites src/locksmith/build_info.py (LOCKSMITH_VERSION) — this is
#      what the RUNNING APP reports at runtime (Help › About, update log).
#   3. The PyInstaller spec ALSO reads pyproject.toml independently and
#      bakes that value into Info.plist CFBundleVersion — which is what
#      Sparkle reads when it decides whether a feed item is "newer".
#
# This script follows the SAME mechanism (rewrite build_info.py) so the
# running app reports the right version. HOWEVER it does NOT patch
# pyproject.toml, because the brief explicitly forbids a fragile sed hack
# that the real build doesn't use.
#
# CONSEQUENCE FOR SMOKE-RUNS:
#   Sparkle compares the feed's <sparkle:version> against Info.plist
#   CFBundleVersion, which equals the pyproject.toml version (e.g. 0.2.4).
#   For "Check for Updates" to offer an update the feed must advertise a
#   version HIGHER than what pyproject.toml currently contains — regardless
#   of the VERSION argument passed to this script.
#
#   Typical smoke-run workflow:
#     1. Leave pyproject.toml at its current version (e.g. 0.2.4).
#     2. Publish a test appcast advertising a HIGHER version (e.g. 0.2.5).
#     3. Run: ./scripts/devbuild-macos.sh 0.2.4
#        The built app's About box will show 0.2.4 and Sparkle will see
#        0.2.5 in the feed → offers the update.
# -----------------------------------------------------------------------
#
# Required (one of):
#   src/locksmith/release/publisher_anchor.json    — gitignored real anchor
#   $LOCKSMITH_PUBLISHER_ANCHOR                    — path override
#
# Required (one of):
#   src/locksmith/release/deploy_config.json       — gitignored real config
#   $LOCKSMITH_DEPLOY_CONFIG                       — path override
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VERSION="${1:-0.0.0-dev}"
CHANNEL="${LOCKSMITH_RELEASE_CHANNEL:-stable}"

echo "devbuild-macos: building Locksmith $VERSION (channel=$CHANNEL, UNSIGNED)"

# ---- 1. Check publisher anchor -------------------------------------------
ANCHOR_PATH="${LOCKSMITH_PUBLISHER_ANCHOR:-src/locksmith/release/publisher_anchor.json}"
if [[ ! -f "$ANCHOR_PATH" ]]; then
    echo "devbuild-macos: ERROR — publisher anchor not found at $ANCHOR_PATH" >&2
    echo "  Set LOCKSMITH_PUBLISHER_ANCHOR to the real anchor path, or place" >&2
    echo "  the anchor at src/locksmith/release/publisher_anchor.json" >&2
    exit 1
fi
echo "devbuild-macos: anchor present at $ANCHOR_PATH"

# ---- 2. Check deploy_config ----------------------------------------------
DEPLOY_CONFIG_PATH="${LOCKSMITH_DEPLOY_CONFIG:-src/locksmith/release/deploy_config.json}"
if [[ ! -f "$DEPLOY_CONFIG_PATH" ]]; then
    echo "devbuild-macos: ERROR — deploy_config not found at $DEPLOY_CONFIG_PATH" >&2
    echo "  Set LOCKSMITH_DEPLOY_CONFIG to the real config path, or place" >&2
    echo "  the config at src/locksmith/release/deploy_config.json" >&2
    exit 1
fi
echo "devbuild-macos: deploy_config present at $DEPLOY_CONFIG_PATH"

# ---- 3. Bake version + channel into build_info.py -----------------------
# Same mechanism as build-macos.sh (§ version-override note at top of file).
cat > src/locksmith/build_info.py <<EOF
"""Build-time constants — REWRITTEN by scripts/devbuild-macos.sh at build time."""
from __future__ import annotations

LOCKSMITH_VERSION: str = "$VERSION"
LOCKSMITH_RELEASE_CHANNEL: str = "$CHANNEL"
EOF
echo "devbuild-macos: wrote build_info.py (LOCKSMITH_VERSION=$VERSION)"

# ---- 4. Clean prior outputs ---------------------------------------------
rm -rf build dist

# ---- 5. PyInstaller ------------------------------------------------------
echo "devbuild-macos: running pyinstaller (no signing, no notarization)"
.venv/bin/pyinstaller --noconfirm --clean packaging/Locksmith.macos.spec

if [[ ! -d "dist/Locksmith.app" ]]; then
    echo "devbuild-macos: ERROR — PyInstaller did not produce dist/Locksmith.app" >&2
    exit 1
fi

# ---- 6. Embed Sparkle.framework ------------------------------------------
# Mirrors build-macos.sh exactly: copy post-PyInstaller so the framework
# lands at Contents/Frameworks/Sparkle.framework (NOT the nested
# Contents/Frameworks/Frameworks/... path that PyInstaller's BUNDLE produces).
# See the comment block in packaging/Locksmith.macos.spec for why this is
# done outside the spec.
SPARKLE_SRC="packaging/macos/Sparkle.framework"
if [[ -d "$SPARKLE_SRC" ]]; then
    echo "devbuild-macos: embedding Sparkle.framework into Contents/Frameworks/"
    mkdir -p "dist/Locksmith.app/Contents/Frameworks"
    rm -rf "dist/Locksmith.app/Contents/Frameworks/Sparkle.framework"
    # -R preserves symlinks (Frameworks rely on Versions/Current/* symlink chain).
    cp -R "$SPARKLE_SRC" "dist/Locksmith.app/Contents/Frameworks/Sparkle.framework"
    echo "devbuild-macos: Sparkle.framework embedded"
else
    echo "devbuild-macos: WARNING — $SPARKLE_SRC not present; in-app updates will be a no-op"
    echo "  Download from https://github.com/sparkle-project/Sparkle/releases (2.x line)"
    echo "  and extract to packaging/macos/Sparkle.framework"
fi

# ---- 7. Done -------------------------------------------------------------
LAUNCH_PATH="dist/Locksmith.app/Contents/MacOS/Locksmith"
echo ""
echo "devbuild-macos: OK — unsigned .app ready"
echo "  Launch: $REPO_ROOT/$LAUNCH_PATH"
echo "  open dist/Locksmith.app"
