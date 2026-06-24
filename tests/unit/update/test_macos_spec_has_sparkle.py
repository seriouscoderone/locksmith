"""Static checks on packaging/Locksmith.macos.spec for Sparkle integration."""
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = _REPO_ROOT / "packaging" / "Locksmith.macos.spec"
_SIGN_SCRIPT = _REPO_ROOT / "signLibs.sh"
_PACKAGING = _REPO_ROOT / "packaging"
if str(_PACKAGING) not in sys.path:
    sys.path.insert(0, str(_PACKAGING))
import brandlib  # noqa: E402


def _locksmith_plist():
    return brandlib.macos_info_plist(brandlib.load_brand_manifest("locksmith"), "0.0.0")


def test_macos_spec_references_sparkle_framework():
    content = _SPEC.read_text()
    assert "Sparkle.framework" in content


def test_macos_spec_sets_sufeed_url():
    # SUFeedURL now flows from the brand manifest via brandlib.macos_info_plist;
    # the spec delegates to it. Assert the spec delegates AND the value emitted.
    assert "macos_info_plist" in _SPEC.read_text()
    assert _locksmith_plist()["SUFeedURL"] == "https://releases.keri.host/appcast/v1/macos.json"


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
    # We drive the scheduler; Sparkle's built-in cadence must be off.
    assert _locksmith_plist()["SUEnableAutomaticChecks"] is False


def test_macos_spec_sets_bundle_id():
    assert _locksmith_plist()["CFBundleIdentifier"] == "host.keri.locksmith"


def test_sign_libs_handles_sparkle_framework():
    sh = _SIGN_SCRIPT.read_text()
    assert "Sparkle.framework" in sh
    # Helper executables must be signed individually first
    assert "Autoupdate" in sh
    assert "Installer.xpc" in sh
