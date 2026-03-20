#!/bin/bash

if [ -z "$DEVELOPER_ID_APP_CERT" ]; then
    echo "DEVELOPER_ID_APP_CERT environment variable not set"
    exit 1
fi

# Sign all .dylib dynamic library files - only libsodium for now
find "libsodium" -name "*.dylib" -exec codesign --force --verify --verbose --sign "$DEVELOPER_ID_APP_CERT" {} \;