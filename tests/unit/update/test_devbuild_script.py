"""Static shape-checks for scripts/devbuild-macos.sh.

These tests run headlessly in CI (Linux/macOS) and on any developer machine
WITHOUT invoking PyInstaller or launching the app. They guard:

  * the script exists and has its executable bit set
  * the safety boilerplate is present (set -euo pipefail)
  * the correct PyInstaller spec is referenced
  * Sparkle.framework is staged into Contents/Frameworks/ after the build
    (mirroring what build-macos.sh does, per the spec comment block)

Step 5 (live smoke-run: build + launch + check native=yes) is intentionally
OUT OF SCOPE for automated CI — it requires PyInstaller + a real macOS
display and is run by the human operator.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "devbuild-macos.sh"


def test_script_exists() -> None:
    """scripts/devbuild-macos.sh must exist in the repo."""
    assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


def test_script_is_executable() -> None:
    """scripts/devbuild-macos.sh must have its executable bit set (all users)."""
    mode = SCRIPT.stat().st_mode
    # At least owner-execute
    assert mode & stat.S_IXUSR, (
        f"Script is not executable (mode={oct(mode)}): {SCRIPT}"
    )


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_set_euo_pipefail() -> None:
    """The script must start with 'set -euo pipefail' for safety."""
    text = _script_text()
    assert "set -euo pipefail" in text, (
        "Missing 'set -euo pipefail' in devbuild-macos.sh"
    )


def test_references_macos_spec() -> None:
    """The script must invoke PyInstaller against packaging/Locksmith.macos.spec."""
    text = _script_text()
    assert "Locksmith.macos.spec" in text, (
        "devbuild-macos.sh does not reference packaging/Locksmith.macos.spec"
    )


def test_stages_sparkle_into_contents_frameworks() -> None:
    """Sparkle.framework must be copied into Contents/Frameworks/ post-build.

    This mirrors build-macos.sh's post-PyInstaller cp -R step.  The framework
    must land at Contents/Frameworks/Sparkle.framework (NOT the nested
    Contents/Frameworks/Frameworks/... path that PyInstaller's BUNDLE would
    produce if the framework were added to datas).
    """
    text = _script_text()
    # The cp -R destination must be the concatenated path — proves the framework
    # lands at Contents/Frameworks/Sparkle.framework, not a wrong nesting.
    assert "Contents/Frameworks/Sparkle.framework" in text, (
        "devbuild-macos.sh does not stage Sparkle.framework into "
        "Contents/Frameworks/ (expected 'Contents/Frameworks/Sparkle.framework')"
    )


def test_patches_info_plist_version() -> None:
    """The script must patch Info.plist via PlistBuddy so Sparkle sees $VERSION.

    FIX 1 guard: after the PyInstaller build, both CFBundleShortVersionString
    and CFBundleVersion must be set to the VERSION arg so that the Sparkle-
    visible version matches what was passed to the script.
    """
    text = _script_text()
    assert "PlistBuddy" in text, (
        "devbuild-macos.sh does not use PlistBuddy to patch Info.plist"
    )
    assert "CFBundleShortVersionString" in text, (
        "devbuild-macos.sh does not set CFBundleShortVersionString via PlistBuddy"
    )
    assert "CFBundleVersion" in text, (
        "devbuild-macos.sh does not set CFBundleVersion via PlistBuddy"
    )


def test_prints_launch_path() -> None:
    """The script must print the path to the Locksmith binary."""
    text = _script_text()
    assert "Contents/MacOS/Locksmith" in text, (
        "devbuild-macos.sh does not print the launch path (Contents/MacOS/Locksmith)"
    )


def test_checks_publisher_anchor() -> None:
    """The script must verify the publisher anchor is present before building."""
    text = _script_text()
    assert "publisher_anchor.json" in text, (
        "devbuild-macos.sh does not check for publisher_anchor.json"
    )
    assert "LOCKSMITH_PUBLISHER_ANCHOR" in text, (
        "devbuild-macos.sh does not honour $LOCKSMITH_PUBLISHER_ANCHOR override"
    )


def test_checks_deploy_config() -> None:
    """The script must verify the deploy_config is present before building."""
    text = _script_text()
    assert "deploy_config.json" in text, (
        "devbuild-macos.sh does not check for deploy_config.json"
    )
    assert "LOCKSMITH_DEPLOY_CONFIG" in text, (
        "devbuild-macos.sh does not honour $LOCKSMITH_DEPLOY_CONFIG override"
    )
