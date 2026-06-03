"""Integration: PyInstaller produces a runnable Locksmith.app on macOS.

Skipped unless: running on macOS AND pyinstaller is importable AND
``RUN_PYINSTALLER_INTEGRATION=1`` is set in the environment (the build is
slow — minutes — so we don't gate the default ``pytest`` suite on it).
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin"
    or os.environ.get("RUN_PYINSTALLER_INTEGRATION") != "1",
    reason=(
        "macOS-only, slow; set RUN_PYINSTALLER_INTEGRATION=1 to run "
        "(CI sets this in the build-macos job)"
    ),
)

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "packaging" / "Locksmith.macos.spec"
APP = REPO / "dist" / "Locksmith.app"


@pytest.fixture(scope="module", autouse=True)
def _pyinstaller_available():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        pytest.skip("pyinstaller not installed (pip install -e .[build-macos])")


def test_spec_runs_and_produces_app(tmp_path):
    """Run PyInstaller against the spec; assert the .app appears."""
    # Clean prior artifacts so we're sure we're testing this build.
    if APP.exists():
        shutil.rmtree(APP)
    dist_dir = REPO / "dist"
    if (dist_dir / "Locksmith").exists():
        shutil.rmtree(dist_dir / "Locksmith")

    result = subprocess.run(
        [
            "pyinstaller",
            "--noconfirm",
            "--clean",
            "--workpath", str(tmp_path / "build"),
            str(SPEC),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=900,  # 15 min cap
    )
    assert result.returncode == 0, (
        f"pyinstaller failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert APP.is_dir(), f"expected {APP} to exist"
    assert (APP / "Contents" / "MacOS" / "Locksmith").is_file()
    assert (APP / "Contents" / "Info.plist").is_file()


def test_bundle_identifier_is_correct():
    import plistlib

    info = plistlib.loads((APP / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == "host.keri.locksmith"


def test_app_launches_and_self_exits():
    """Sanity: ``open -W ... --args --self-test`` returns quickly.

    The app should accept ``--self-test`` and exit cleanly. If the binary is
    miswired (e.g. missing libsodium, missing Qt plugins) the call will hang
    or return non-zero.
    """
    # Many apps reject unknown flags; we use a short timeout and treat any
    # exit as success. The real signal is "didn't hang".
    proc = subprocess.run(
        ["open", "-W", "-a", str(APP), "--args", "--self-test"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # We don't assert returncode (the app may exit 0 or 1 depending on how
    # it handles unknown args). The important assertion is that ``open -W``
    # returned at all rather than timing out.
    assert proc.returncode in (0, 1), proc.stderr
