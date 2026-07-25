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
    # Spec composes the entry path via Path("src") / "locksmith" / "main.py"
    # to keep it OS-portable, so we look for the tokens not the joined string.
    assert '"src"' in s and '"locksmith"' in s and '"main.py"' in s


def test_spec_includes_libsodium():
    s = SPEC.read_text()
    assert "libsodium" in s


def test_spec_includes_assets():
    # The loose assets/ tree was dropped in favor of the compiled brand
    # bundle (assets.rcc) staged into the brand release dir by brand_apply;
    # see tests/packaging/test_spec_bundles_rcc.py for the guard that the
    # loose datas entry stays gone.
    s = SPEC.read_text()
    assert "assets.rcc" in s


def test_spec_includes_publisher_anchor():
    s = SPEC.read_text()
    assert "publisher_anchor.json" in s


def test_spec_includes_qtawesome():
    s = SPEC.read_text()
    assert "qtawesome" in s


def test_spec_bundle_id_from_brand():
    # Bundle id is brand-driven; the resolved value ("host.keri.locksmith") is
    # asserted in tests/unit/branding/test_spec_brand_values.py.
    s = SPEC.read_text()
    assert '_BRAND["identity"]["bundle_id"]' in s


def test_spec_reads_version_from_pyproject():
    s = SPEC.read_text()
    assert "pyproject.toml" in s


def test_spec_app_name_from_brand():
    # App name is brand-driven (_BRAND_NAME = brand display_name). The resolved
    # value ("Locksmith" for the default brand) is asserted in
    # tests/unit/branding/test_spec_brand_values.py.
    s = SPEC.read_text()
    assert "name=_BRAND_NAME" in s
