"""Both PyInstaller specs must bundle entry-point plugin metadata + ALL bundled
plugin modules.

Bundled plugins are ``[project.entry-points."locksmith.plugins"]`` entries,
discovered ONLY via ``importlib.metadata.entry_points(group=...)``. In a frozen
app that needs (1) the Locksmith dist-info bundled (``copy_metadata``) so the
lookup returns the entries, and (2) each plugin package bundled
(``collect_submodules``) so ``ep.load()`` resolves. Without both, a plugin is
invisible in frozen builds while working fine from source.

Originally the specs collected ONLY ``locksmith.plugins.kerifoundation``, so the
HOA plugins (hoa_shell/actuary/product_designer) never made it into the frozen
Usurance build and the brand fell back to the vanilla vault picker. The specs
now collect the whole ``locksmith.plugins`` tree; this guard asserts that, and
that every entry-point plugin lives under that tree so the broad collect covers
it (current AND future).
See backlog/2026-07-09-kerifoundation-plugin-missing-in-frozen-builds.md.
"""
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPECS = {
    "macos": _REPO_ROOT / "packaging" / "Locksmith.macos.spec",
    "windows": _REPO_ROOT / "packaging" / "Locksmith.windows.spec",
}


def _entry_point_targets() -> dict[str, str]:
    """{plugin_name: 'locksmith.plugins.<pkg>.plugin:Class'} from pyproject."""
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    eps = pyproject["project"]["entry-points"]["locksmith.plugins"]
    assert eps, "no locksmith.plugins entry-points declared"
    return eps


@pytest.mark.parametrize("name", sorted(_SPECS))
def test_spec_bundles_entry_point_metadata(name):
    content = _SPECS[name].read_text()
    assert 'copy_metadata("Locksmith")' in content, (
        f"{name} spec must copy_metadata('Locksmith') so entry-point plugins "
        f"are discoverable in the frozen app"
    )


@pytest.mark.parametrize("name", sorted(_SPECS))
def test_spec_collects_whole_plugins_tree(name):
    content = _SPECS[name].read_text()
    assert 'collect_submodules("locksmith.plugins")' in content, (
        f"{name} spec must collect the whole locksmith.plugins tree so every "
        f"bundled entry-point plugin's submodules resolve via ep.load() in the "
        f"frozen app (kerifoundation-only left the HOA plugins out)"
    )


def test_every_entry_point_plugin_is_under_the_collected_tree():
    """collect_submodules('locksmith.plugins') only covers plugins that actually
    live under that package. Guard that every declared entry-point does."""
    for pname, target in _entry_point_targets().items():
        module = target.split(":", 1)[0]
        assert module.startswith("locksmith.plugins."), (
            f"entry-point {pname!r} -> {target!r} is not under locksmith.plugins; "
            f"collect_submodules('locksmith.plugins') will NOT bundle it — add an "
            f"explicit collect_submodules for its package to both specs"
        )
