"""Both PyInstaller specs must bundle entry-point plugin metadata + the KERI
Foundation plugin module.

The KF plugin is a purely bundled ``[project.entry-points."locksmith.plugins"]``
entry, discovered ONLY via ``importlib.metadata.entry_points(group=...)``. In a
frozen app that needs (1) the Locksmith dist-info bundled (``copy_metadata``) so
the lookup returns the entry, and (2) the plugin package bundled
(``collect_submodules``) so ``ep.load()`` resolves. Without both, the plugin is
invisible in frozen builds while working fine from source — a silent gap this
guard prevents from regressing.
See backlog/2026-07-09-kerifoundation-plugin-missing-in-frozen-builds.md.
"""
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPECS = {
    "macos": _REPO_ROOT / "packaging" / "Locksmith.macos.spec",
    "windows": _REPO_ROOT / "packaging" / "Locksmith.windows.spec",
}


@pytest.mark.parametrize("name", sorted(_SPECS))
def test_spec_bundles_entry_point_metadata(name):
    content = _SPECS[name].read_text()
    assert 'copy_metadata("Locksmith")' in content, (
        f"{name} spec must copy_metadata('Locksmith') so entry-point plugins "
        f"(KERI Foundation) are discoverable in the frozen app"
    )


@pytest.mark.parametrize("name", sorted(_SPECS))
def test_spec_bundles_kerifoundation_module(name):
    content = _SPECS[name].read_text()
    assert 'collect_submodules("locksmith.plugins.kerifoundation")' in content, (
        f"{name} spec must collect the kerifoundation plugin submodules so "
        f"ep.load() resolves in the frozen app"
    )
