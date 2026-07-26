"""Library package DATA read off disk at runtime must be collected by both specs.

Regression: `keri_serviceaid` ships its EGF meta-schema as package data and reads
it from disk (`keri_serviceaid/egf/documents.py:_load_meta_schema`). PyInstaller
bundles the `.py` modules because they are imported, but NOT the `.json` beside
them — so every frozen build died with

    FileNotFoundError: .../keri_serviceaid/egf/schemas/egf-doc-0.1.json

the moment `core/egf_seeding.make_hoa_resolver()` resolved the brand's EGF,
taking the HOA persona/roles surface with it. Confirmed absent from the shipped
0.3.4 artifact (zero `keri_serviceaid` entries in the bundle).

The requirement is *derived*, not restated: for each package below we assert the
data file genuinely exists on disk (so the test tracks the dependency rather
than a remembered filename) and that both specs collect that package.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS = ("Locksmith.macos.spec", "Locksmith.windows.spec")

#: Installed packages whose on-disk data files the app reads at runtime.
#: Extend this when a dependency starts reading its own package data.
RUNTIME_DATA_PACKAGES = ("keri_serviceaid",)


def _package_dir(name: str) -> Path | None:
    spec = importlib.util.find_spec(name)
    if spec is None or not spec.submodule_search_locations:
        return None
    return Path(list(spec.submodule_search_locations)[0])


@pytest.mark.parametrize("package", RUNTIME_DATA_PACKAGES)
def test_package_actually_ships_data_files(package):
    """Guard against the guard going stale: if the dependency stops shipping
    data files, this test should be revisited rather than silently passing."""
    pkg_dir = _package_dir(package)
    if pkg_dir is None:
        pytest.skip(f"{package} not installed in this environment")
    data_files = [p for p in pkg_dir.rglob("*.json")]
    assert data_files, (
        f"{package} ships no .json data files any more — re-check whether it "
        f"still belongs in RUNTIME_DATA_PACKAGES")


@pytest.mark.parametrize("spec_name", SPECS)
@pytest.mark.parametrize("package", RUNTIME_DATA_PACKAGES)
def test_both_specs_collect_runtime_data_files(spec_name, package):
    src = (REPO_ROOT / "packaging" / spec_name).read_text(encoding="utf-8")
    assert "collect_data_files" in src, (
        f"{spec_name} must import/use collect_data_files")
    assert f'collect_data_files("{package}")' in src, (
        f"{spec_name} must collect {package}'s package data — it is read off "
        f"disk at runtime and PyInstaller does not infer it from imports")


@pytest.mark.parametrize("spec_name", SPECS)
def test_both_specs_bundle_brand_egf_conditionally(spec_name):
    """The brand's own EGF bundle is staged next to brand.json by brand_apply,
    and `branding.egf_local_dir()` looks for `egf/` as a SIBLING of the brand.json
    that was read — so it must land at locksmith/release/egf. It stays
    conditional because only brands that pin an EGF have the dir (the reference
    Locksmith brand does not, and an unconditional entry breaks its build)."""
    src = (REPO_ROOT / "packaging" / spec_name).read_text(encoding="utf-8")
    assert '(_RELEASE / "egf").is_dir()' in src, (
        f"{spec_name} must bundle the brand EGF conditionally")
    assert '"locksmith/release/egf"' in src, (
        f"{spec_name} must bundle the brand EGF as a sibling of brand.json")
