"""Verify entitlements.plist matches spec §11.1.

Sparkle 2.x requires non-sandboxed app. Hardened runtime + network must stay.
Camera/microphone removed because the codebase doesn't use them.
"""
from pathlib import Path
import plistlib

ENTITLEMENTS = Path(__file__).resolve().parents[2] / "entitlements.plist"

REQUIRED_TRUE = [
    "com.apple.security.cs.allow-jit",
    "com.apple.security.cs.allow-unsigned-executable-memory",
    "com.apple.security.cs.allow-dyld-environment-variables",
    "com.apple.security.network.client",
    "com.apple.security.network.server",
]

MUST_BE_ABSENT = [
    "com.apple.security.app-sandbox",
    "com.apple.security.device.audio-input",
    "com.apple.security.device.camera",
    "com.apple.security.device.microphone",
]


def test_entitlements_has_required_keys():
    data = plistlib.loads(ENTITLEMENTS.read_bytes())
    for key in REQUIRED_TRUE:
        assert data.get(key) is True, f"missing or false: {key}"


def test_entitlements_no_sandbox_or_av():
    data = plistlib.loads(ENTITLEMENTS.read_bytes())
    for key in MUST_BE_ABSENT:
        assert key not in data, f"must be removed: {key}"
