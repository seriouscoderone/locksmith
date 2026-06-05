"""Static checks on packaging/Locksmith.windows.spec.

We don't execute the spec here (a PyInstaller build only runs on a
Windows host in CI). We verify it mentions every required input the
Windows build is supposed to bundle.
"""
from pathlib import Path

SPEC = Path(__file__).resolve().parents[2] / "packaging" / "Locksmith.windows.spec"


def test_spec_exists():
    assert SPEC.is_file(), f"missing: {SPEC}"


def test_spec_references_entry_point():
    s = SPEC.read_text()
    assert "locksmith" in s and "main.py" in s


def test_spec_includes_libsodium_dll():
    s = SPEC.read_text()
    assert "libsodium.dll" in s


def test_spec_includes_assets():
    s = SPEC.read_text()
    assert "'assets'" in s or '"assets"' in s


def test_spec_includes_publisher_anchor():
    s = SPEC.read_text()
    assert "publisher_anchor.json" in s


def test_spec_includes_qtawesome():
    s = SPEC.read_text()
    assert "qtawesome" in s


def test_spec_reads_version_from_pyproject():
    s = SPEC.read_text()
    assert "pyproject.toml" in s


def test_spec_app_name_is_Locksmith():
    s = SPEC.read_text()
    assert "name='Locksmith'" in s or 'name="Locksmith"' in s


def test_spec_uses_windows_ico_icon():
    s = SPEC.read_text()
    assert "AppIcon.ico" in s


def test_spec_disables_console():
    s = SPEC.read_text()
    assert "console=False" in s


def test_spec_disables_upx():
    """UPX-compressed binaries fail Authenticode signing on Windows."""
    s = SPEC.read_text()
    # `upx=False` appears in EXE() and COLLECT().
    assert s.count("upx=False") >= 2
