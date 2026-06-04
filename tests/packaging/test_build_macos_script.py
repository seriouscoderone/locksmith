"""Static checks on packaging/build-macos.sh."""
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "packaging" / "build-macos.sh"


def test_script_exists():
    assert SCRIPT.is_file()


def test_script_is_executable():
    assert SCRIPT.stat().st_mode & 0o111


def test_script_runs_pyinstaller_with_spec():
    s = SCRIPT.read_text()
    assert "pyinstaller" in s
    assert "packaging/Locksmith.macos.spec" in s


def test_script_calls_signLibs():
    s = SCRIPT.read_text()
    assert "signLibs.sh" in s


def test_script_calls_sign_sh():
    s = SCRIPT.read_text()
    assert "scripts/sign.sh" in s


def test_script_calls_create_dmg():
    s = SCRIPT.read_text()
    assert "create-dmg" in s


def test_script_calls_notarytool():
    s = SCRIPT.read_text()
    assert "notarytool" in s
    assert "--wait" in s


def test_script_calls_stapler():
    s = SCRIPT.read_text()
    assert "stapler" in s
    assert "staple" in s


def test_script_writes_build_info():
    s = SCRIPT.read_text()
    assert "build_info.py" in s
    assert "LOCKSMITH_VERSION" in s


def test_script_reads_version_from_pyproject():
    s = SCRIPT.read_text()
    assert "pyproject.toml" in s


def test_script_uses_dmg_layout():
    s = SCRIPT.read_text()
    assert "packaging/dmg/layout.json" in s
    assert "packaging/dmg/background.png" in s
