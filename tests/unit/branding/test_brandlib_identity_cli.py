import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PKG = REPO / "packaging"


def _run(field, brand):
    return subprocess.run(
        [sys.executable, "-m", "brandlib", "id", field],
        cwd=PKG, env={"LOCKSMITH_BRAND": brand, "PATH": ""},
        capture_output=True, text=True,
    )


def test_locksmith_identity_fields():
    assert _run("display_name", "locksmith").stdout.strip() == "Locksmith"
    assert _run("artifact_prefix", "locksmith").stdout.strip() == "Locksmith"
    assert _run("bundle_id", "locksmith").stdout.strip() == "host.keri.locksmith"


def test_usurance_identity_fields():
    assert _run("display_name", "usurance").stdout.strip() == "Usurance"
    assert _run("artifact_prefix", "usurance").stdout.strip() == "Usurance"
    assert _run("bundle_id", "usurance").stdout.strip() == "com.usurance.wallet"


def test_unknown_field_exits_nonzero():
    assert _run("nope", "locksmith").returncode == 2


def test_release_prefix():
    assert _run("release_prefix", "locksmith").stdout.strip() == "releases"
    assert _run("release_prefix", "usurance").stdout.strip() == "usurance/releases"


def test_website():
    assert _run("website", "locksmith").stdout.strip() == "https://locksmith.app"
    assert _run("website", "usurance").stdout.strip() == "https://usurance.com"
