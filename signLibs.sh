#!/bin/bash
#
# Re-sign embedded native libraries / frameworks inside the staged .app
# bundle with the Developer ID Application certificate. Run after
# pyinstaller has produced dist/Locksmith.app and before notarization.
#
# Required env: DEVELOPER_ID_APP_CERT  — codesign identity (cert name or
#                                        SHA-1 thumbprint). CI exports this
#                                        from the macOS keychain step.

set -euo pipefail

if [ -z "${DEVELOPER_ID_APP_CERT:-}" ]; then
    echo "DEVELOPER_ID_APP_CERT environment variable not set"
    exit 1
fi

# Sign libsodium dylibs in the source tree (used by local builds where
# the bundle hasn't been assembled yet).
find "libsodium" -name "*.dylib" -exec \
    codesign --force --verify --verbose \
             --sign "$DEVELOPER_ID_APP_CERT" {} \;

# Sparkle.framework — Sparkle ships multiple helper executables (XPC
# services + the Autoupdate / Updater.app stub) that each need to be
# signed individually before the outer framework is signed. Without
# this, Gatekeeper rejects the bundle at notarization.
APP_BUNDLE="${APP_BUNDLE:-dist/Locksmith.app}"
SPARKLE_FRAMEWORK="$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"

if [ -d "$SPARKLE_FRAMEWORK" ]; then
    echo "[signLibs] codesigning Sparkle.framework helpers"

    # Helper paths inside Sparkle 2.x. The 'B' version directory is the
    # current bundle version Sparkle ships; if Sparkle changes its
    # version-letter convention this list needs to be updated.
    HELPERS=(
        "$SPARKLE_FRAMEWORK/Versions/B/XPCServices/Downloader.xpc"
        "$SPARKLE_FRAMEWORK/Versions/B/XPCServices/Installer.xpc"
        "$SPARKLE_FRAMEWORK/Versions/B/Autoupdate"
        "$SPARKLE_FRAMEWORK/Versions/B/Updater.app"
    )

    for helper in "${HELPERS[@]}"; do
        if [ -e "$helper" ]; then
            codesign --force --options runtime \
                     --sign "$DEVELOPER_ID_APP_CERT" \
                     --timestamp "$helper"
        fi
    done

    # Sign the outer framework last so it picks up the sealed helper sigs.
    codesign --force --options runtime \
             --sign "$DEVELOPER_ID_APP_CERT" \
             --timestamp "$SPARKLE_FRAMEWORK"
fi
