"""Static checks on packaging/Locksmith.macos.spec for Sparkle integration."""
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = _REPO_ROOT / "packaging" / "Locksmith.macos.spec"
_SIGN_SCRIPT = _REPO_ROOT / "signLibs.sh"


def test_macos_spec_references_sparkle_framework():
    content = _SPEC.read_text()
    assert "Sparkle.framework" in content


def test_macos_spec_sets_sufeed_url():
    content = _SPEC.read_text()
    assert "SUFeedURL" in content
    assert "releases.keri.host/appcast/v1/macos.json" in content


def test_macos_spec_does_not_set_public_ed_key():
    """Spec §3 — KERI is sole trust; Sparkle's signature verification stays OFF.

    We only care that no dict entry assigns the key; documentary mentions
    in comments explaining the omission are allowed.
    """
    content = _SPEC.read_text()
    # The dict-form line would look like:  "SUPublicEDKey": "..."
    assert "\"SUPublicEDKey\":" not in content
    assert "'SUPublicEDKey':" not in content


def test_macos_spec_disables_sparkle_automatic_checks():
    """We drive the scheduler; Sparkle's built-in cadence must be off."""
    content = _SPEC.read_text()
    assert "SUEnableAutomaticChecks" in content
    # The line must explicitly set False (string form because info_plist
    # is a Python dict literal):
    assert "\"SUEnableAutomaticChecks\": False" in content


def test_macos_spec_sets_bundle_id():
    content = _SPEC.read_text()
    assert "host.keri.locksmith" in content


def test_sign_libs_handles_sparkle_framework():
    sh = _SIGN_SCRIPT.read_text()
    assert "Sparkle.framework" in sh
    # Helper executables must be signed individually first
    assert "Autoupdate" in sh
    assert "Installer.xpc" in sh
