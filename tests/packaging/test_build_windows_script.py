"""Static checks on packaging/build-windows.ps1."""
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "packaging" / "build-windows.ps1"


def test_script_exists():
    assert SCRIPT.is_file()


def test_script_runs_pyinstaller_with_spec():
    s = SCRIPT.read_text()
    assert "pyinstaller" in s.lower()
    assert "Locksmith.windows.spec" in s


def test_script_runs_wix_harvest():
    s = SCRIPT.read_text()
    assert "wix harvest" in s


def test_script_runs_wix_build():
    s = SCRIPT.read_text()
    assert "wix build" in s


def test_script_writes_build_info():
    s = SCRIPT.read_text()
    assert "build_info.py" in s
    assert "LOCKSMITH_VERSION" in s


def test_script_reads_version_from_pyproject():
    s = SCRIPT.read_text()
    assert "pyproject.toml" in s


def test_script_produces_versioned_msi():
    s = SCRIPT.read_text()
    assert "Locksmith-$Version.msi" in s or 'Locksmith-' in s and '.msi' in s


def test_script_emits_structured_log_lines():
    s = SCRIPT.read_text()
    assert "[build]" in s
