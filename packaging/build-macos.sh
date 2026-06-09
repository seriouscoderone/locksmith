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

# ---- 4b. Embed Sparkle.framework -----------------------------------------
# Done post-PyInstaller because PyInstaller's BUNDLE step nests data paths
# under Contents/Frameworks/, producing Contents/Frameworks/Frameworks/...,
# and its internal ad-hoc codesign chokes on the nested .framework. Copying
# here puts it at the canonical Contents/Frameworks/Sparkle.framework path;
# scripts/sign.sh below does a recursive Developer ID sign that catches it.
SPARKLE_SRC="packaging/macos/Sparkle.framework"
if [[ -d "$SPARKLE_SRC" ]]; then
    echo "build-macos: embedding Sparkle.framework into Contents/Frameworks/"
    mkdir -p "dist/Locksmith.app/Contents/Frameworks"
    rm -rf "dist/Locksmith.app/Contents/Frameworks/Sparkle.framework"
    # -R preserves symlinks (Frameworks rely on Versions/Current/* symlink chain).
    cp -R "$SPARKLE_SRC" "dist/Locksmith.app/Contents/Frameworks/Sparkle.framework"
else
    echo "build-macos: WARNING — $SPARKLE_SRC not present; in-app updates will be a no-op"
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
    --volicon "assets/custom/AppIcon.icns" \
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
