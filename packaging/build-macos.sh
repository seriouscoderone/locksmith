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

# ---- 0. Resolve brand identity (build-time white-label). Default = locksmith.
export LOCKSMITH_BRAND="${LOCKSMITH_BRAND:-locksmith}"
export LOCKSMITH_RELEASE="$(cd packaging && python -c "import brandlib; print(brandlib.brand_release_dir('$LOCKSMITH_BRAND'))")"
APP_NAME="$(cd packaging && python -m brandlib id display_name)"
ARTIFACT_PREFIX="$(cd packaging && python -m brandlib id artifact_prefix)"
echo "build-macos: brand=$LOCKSMITH_BRAND app=$APP_NAME.app prefix=$ARTIFACT_PREFIX release=$LOCKSMITH_RELEASE"

# Build (or refresh) the brand's self-contained release bundle — assets.rcc,
# brand.json, Locksmith.wxs, dmg-layout.json, staged icons, trust material —
# before PyInstaller/create-dmg read it. Idempotent (brand_apply always
# rewrites its output dir); CI's release workflow already runs this as its
# own step, but calling it here too keeps this script correct standalone
# (e.g. local dev builds run directly, without the CI step preceding it).
python scripts/brand_apply.py --brand "$LOCKSMITH_BRAND"

# ---- 1. Read version from pyproject.toml ---------------------------------
VERSION="$(python3 -c '
import tomllib, sys
with open("pyproject.toml", "rb") as f:
    print(tomllib.load(f)["project"]["version"])
')"
echo "build-macos: building $APP_NAME $VERSION (channel=$CHANNEL)"

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

if [[ ! -d "dist/${APP_NAME}.app" ]]; then
    echo "build-macos: PyInstaller did not produce dist/${APP_NAME}.app" >&2
    exit 1
fi

# ---- 4b. Embed Sparkle.framework -----------------------------------------
# Done post-PyInstaller because PyInstaller's BUNDLE step nests data paths
# under Contents/Frameworks/, producing Contents/Frameworks/Frameworks/...,
# and its internal ad-hoc codesign chokes on the nested .framework. Copying
# here puts it at the canonical Contents/Frameworks/Sparkle.framework path;
# scripts/sign.sh below does a recursive Developer ID sign that catches it.
SPARKLE_SRC="packaging/macos/Sparkle.framework"
if [[ -d "$SPARKLE_SRC" ]]; then
    echo "build-macos: embedding Sparkle.framework into Contents/Frameworks/"
    mkdir -p "dist/${APP_NAME}.app/Contents/Frameworks"
    rm -rf "dist/${APP_NAME}.app/Contents/Frameworks/Sparkle.framework"
    # -R preserves symlinks (Frameworks rely on Versions/Current/* symlink chain).
    cp -R "$SPARKLE_SRC" "dist/${APP_NAME}.app/Contents/Frameworks/Sparkle.framework"
else
    echo "build-macos: WARNING — $SPARKLE_SRC not present; in-app updates will be a no-op"
fi

# ---- 5. Sign nested libsodium dylibs ------------------------------------
echo "build-macos: signing libsodium dylibs"
./signLibs.sh

# ---- 6. Sign the .app (entitlements applied, hardened runtime) ----------
echo "build-macos: signing dist/${APP_NAME}.app"
APP_BUNDLE="dist/${APP_NAME}.app" ENTITLEMENTS="entitlements.plist" \
    ./scripts/sign.sh

# ---- 7. Build the DMG ---------------------------------------------------
DMG_NAME="${ARTIFACT_PREFIX}-${VERSION}.dmg"
DMG_PATH="dist/${DMG_NAME}"
rm -f "$DMG_PATH"

# Pull window + icon coords from the brand's generated dmg-layout.json
read APP_X APP_Y APPS_X APPS_Y WIN_W WIN_H ICON_SIZE < <(APP_NAME="$APP_NAME" LOCKSMITH_RELEASE="$LOCKSMITH_RELEASE" python3 - <<'PY'
import json, os
name = os.environ["APP_NAME"]
d = json.load(open(os.path.join(os.environ["LOCKSMITH_RELEASE"], "dmg-layout.json")))
icons = {i["name"]: i for i in d["icons"]} if isinstance(d["icons"], list) else d["icons"]
print(
    icons[f"{name}.app"]["pos"][0],
    icons[f"{name}.app"]["pos"][1],
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
    --volname "${APP_NAME}" \
    --volicon "$LOCKSMITH_RELEASE/AppIcon.icns" \
    --background "packaging/dmg/background.png" \
    --window-pos 200 200 \
    --window-size "$WIN_W" "$WIN_H" \
    --icon-size "$ICON_SIZE" \
    --icon "${APP_NAME}.app" "$APP_X" "$APP_Y" \
    --app-drop-link "$APPS_X" "$APPS_Y" \
    --hide-extension "${APP_NAME}.app" \
    --format UDZO \
    "$DMG_PATH" \
    "dist/${APP_NAME}.app"

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
