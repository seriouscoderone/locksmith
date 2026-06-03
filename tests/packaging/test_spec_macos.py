"""Static checks on packaging/Locksmith.macos.spec.

We don't execute the spec here (that's the integration test). We verify it
mentions every required input the build is supposed to bundle.
"""
from pathlib import Path

SPEC = Path(__file__).resolve().parents[2] / "packaging" / "Locksmith.macos.spec"


def test_spec_exists():
    assert SPEC.is_file(), f"missing: {SPEC}"


def test_spec_references_entry_point():
    s = SPEC.read_text()
    assert "src/locksmith/main.py" in s


def test_spec_includes_libsodium():
    s = SPEC.read_text()
    assert "libsodium" in s


def test_spec_includes_assets():
    s = SPEC.read_text()
    assert "'assets'" in s or '"assets"' in s


def test_spec_includes_publisher_anchor():
    s = SPEC.read_text()
    assert "publisher_anchor.json" in s


def test_spec_includes_qtawesome():
    s = SPEC.read_text()
    assert "qtawesome" in s


def test_spec_bundle_id_is_host_keri_locksmith():
    s = SPEC.read_text()
    assert "host.keri.locksmith" in s


def test_spec_reads_version_from_pyproject():
    s = SPEC.read_text()
    assert "pyproject.toml" in s


def test_spec_app_name_is_Locksmith():
    s = SPEC.read_text()
    assert "name='Locksmith'" in s or 'name="Locksmith"' in s
