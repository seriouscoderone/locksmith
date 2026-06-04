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
