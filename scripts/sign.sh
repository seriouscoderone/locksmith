#!/bin/bash

#
# Author: Kevin Griffin
#
# Disclaimer: This script is provided "as is" without warranty of any kind, either express or implied,
# including but not limited to the implied warranties of merchantability and fitness for a particular purpose.
# Use this script at your own risk. The author shall not be held responsible for any damages arising from
# the use of this script.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Requires the following environment variables to be set:
# DEVELOPER_ID_APP_CERT: The Developer ID Application certificate to sign the app with


if [ -z "$DEVELOPER_ID_APP_CERT" ]; then
    echo "DEVELOPER_ID_APP_CERT environment variable not set"
    exit 1
fi

if [ -z "$LOCKSMITH_ENVIRONMENT" ]; then
    echo "LOCKSMITH_ENVIRONMENT environment variable not set"
    echo "Using PRODUCTION"
    echo "Press Enter to continue..."
    LOCKSMITH_ENVIRONMENT=production
    read -r
else
    echo "Using $LOCKSMITH_ENVIRONMENT environment"
fi

APP_NAME="Locksmith"
APP_IDENTIFIER="com.CHANGEME.locksmith"
APP_VERSION="0.0.1"
APP_DISPLAY_NAME="Locksmith"
BUILD_DIR="build/macos"
MACHINE_OS=$(sw_vers -buildVersion)
APP_ICON="AppIcon"
DMG_NAME="$APP_NAME.dmg"
KC_PROFILE="com.CHANGEME.locksmith"
WORKING_DIR=$(pwd)

# Get the build machine OS build version
# BUILD_MACHINE_OS_BUILD=$(sw_vers -buildVersion)

# Create Info.plist
cat <<EOF > "$BUILD_DIR/$APP_NAME.app/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
	<key>CFBundleExecutable</key>
	<string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_DISPLAY_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>$APP_IDENTIFIER</string>
    <key>CFBundleVersion</key>
    <string>$APP_VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$APP_VERSION</string>
	<key>BuildMachineOSBuild</key>
	<string>$MACHINE_OS</string>
	<key>CFBundleIconFile</key>
	<string>$APP_ICON</string>
	<key>CFBundleIconName</key>
	<string>$APP_ICON</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
	<key>CFBundleDevelopmentRegion</key>
	<string>en</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleSupportedPlatforms</key>
	<array>
		<string>MacOSX</string>
	</array>
  <key>LSEnvironment</key>
   <dict>
     <key>LOCKSMITH_ENVIRONMENT</key>
     <string>$LOCKSMITH_ENVIRONMENT</string>
   </dict>
</dict>
</plist>
EOF

cat <<EOF > "entitlements.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.app-sandbox</key>
    <true/>
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
    <key>com.apple.security.device.audio-input</key>
    <true/>
    <key>com.apple.security.device.camera</key>
    <true/>
    <key>com.apple.security.device.microphone</key>
    <true/>
</dict>
</plist>
EOF

# Unpack, sign, and repack the zip file within the framework
cd "$BUILD_DIR/$APP_NAME.app/Contents/Frameworks/App.framework/Versions/A/Resources/flutter_assets/app/" || fail
unzip -q app.zip -d tmp
find "tmp" -type f -name "*.so" -exec codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" {} \;
find "tmp" -type f -name "*.dylib" -exec codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" {} \;
cd tmp || fail
zip -q -r ../app.zip .
rm -rf .venv
cd ..
rm -rf tmp

cd "$WORKING_DIR" || fail

# Sign all .so files
find "$BUILD_DIR/$APP_NAME.app" -name "*.so" -exec codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" {} \;
find "$BUILD_DIR/$APP_NAME.app" -name "*.dylib" -exec codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" {} \;

# Sign all .dylib dynamic library files
find "libsodium" -name "*.dylib" -exec codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" {} \;

# Sign the main executable
codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" --entitlements entitlements.plist "$BUILD_DIR/$APP_NAME.app/Contents/MacOS/$APP_NAME"

# Sign any frameworks
find "$BUILD_DIR/$APP_NAME.app/Contents/Frameworks" -name "*.framework" -exec codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" {} \;

# Sign the entire .app bundle
codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" --options runtime "$BUILD_DIR/$APP_NAME.app"

# Create the DMG
cd "${BUILD_DIR}" || fail
rm -f "Locksmith.dmg"
create-dmg --volname Locksmith --volicon "${WORKING_DIR}/assets/custom/SymbolLogo.svg" \
           --background "${WORKING_DIR}/assets/dmgBackground.jpeg" \
           --window-pos 200 800 --window-size 600 400 --icon-size 100 \
           --hide-extension Locksmith --icon Locksmith 150 190 --app-drop-link 450 185 "Locksmith.dmg" "Locksmith.app/"

cd "$WORKING_DIR" || fail

# Sign the DMG
codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" "$BUILD_DIR/$DMG_NAME"

# Notarize the DMG
xcrun notarytool submit "$BUILD_DIR/$DMG_NAME" --keychain-profile "$KC_PROFILE" --wait

# Staple the notarization ticket to the DMG
xcrun stapler staple "$BUILD_DIR/$DMG_NAME"

# Verify the notarization
xcrun stapler validate "$BUILD_DIR/$DMG_NAME"