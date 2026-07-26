"""The PyInstaller specs must satisfy every origin that declares it needs
build-time collection — derived from the origin registry, not hardcoded here.

Defect D2 (docs/superpowers/specs/2026-07-25-plugin-origin-strategy-design.md):
entry-point plugins are reached only via ``ep.load()``, which PyInstaller's
static analysis cannot see. Nothing in the code said so, and the omission shipped
twice — ``kerifoundation`` invisible in frozen builds (0.2.21), then the entire
HOA surface missing so Usurance fell back to the vault picker (0.3.1).

The requirement is now a declared property of the origin
(``requires_build_collection`` + ``collected_packages``). These tests read the
registry, so adding an origin or moving a plugin package cannot silently ship a
broken frozen build: the guard updates itself.

Replaces the earlier ``test_specs_bundle_kf_plugin.py``, which asserted the same
thing by re-hardcoding the group name and package in the test.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from locksmith.plugins.origins import (
    COMPOSED_ENTRY_POINT_GROUP,
    DEFAULT_ORIGINS,
    ENTRY_POINT_GROUP,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPECS = {
    "macos": _REPO_ROOT / "packaging" / "Locksmith.macos.spec",
    "windows": _REPO_ROOT / "packaging" / "Locksmith.windows.spec",
}

#: Origins whose code must be inside the frozen bundle.
_COLLECTED = tuple(o for o in DEFAULT_ORIGINS if o.requires_build_collection)


def _spec_text(name: str) -> str:
    return _SPECS[name].read_text()


def test_registry_declares_at_least_one_collected_origin():
    """Guard against the derivation going vacuous — if this ever emptied, the
    tests below would pass while bundling nothing."""
    assert _COLLECTED, (
        "no origin declares requires_build_collection; the packaging guards "
        "below would be vacuous"
    )


@pytest.mark.parametrize("name", sorted(_SPECS))
def test_spec_copies_entry_point_metadata(name):
    """Without the dist-info, ``entry_points(group=...)`` returns nothing in the
    frozen app and every in-tree plugin silently disappears."""
    assert 'copy_metadata("Locksmith")' in _spec_text(name), (
        f"{name} spec must copy_metadata('Locksmith') so entry-point plugins "
        f"are discoverable in the frozen app"
    )


@pytest.mark.parametrize("name", sorted(_SPECS))
def test_spec_collects_every_declared_package(name):
    """Each collected origin's packages must be collect_submodules()'d."""
    content = _spec_text(name)
    for origin in _COLLECTED:
        assert origin.collected_packages, (
            f"origin {origin.origin_id!r} requires build collection but declares "
            f"no collected_packages"
        )
        for package in origin.collected_packages:
            assert f'collect_submodules("{package}")' in content, (
                f"{name} spec must collect_submodules({package!r}) — origin "
                f"{origin.origin_id!r} declares it requires build collection, so "
                f"its plugins resolve via dynamic import that PyInstaller cannot see"
            )


def test_every_entry_point_plugin_lives_under_a_collected_package():
    """A broad ``collect_submodules(root)`` only covers plugins actually under
    that root. Assert every declared entry point — in EITHER group — does."""
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    eps = pyproject["project"]["entry-points"]
    groups = {g: eps.get(g, {}) for g in (ENTRY_POINT_GROUP,
                                          COMPOSED_ENTRY_POINT_GROUP)}
    assert any(groups.values()), "no locksmith.plugins entry-points declared"

    roots = tuple(p for o in _COLLECTED for p in o.collected_packages)
    for group, entries in groups.items():
        for pname, target in entries.items():
            module = target.split(":", 1)[0]
            assert any(module.startswith(f"{root}.") for root in roots), (
                f"entry-point {pname!r} in group {group!r} -> {target!r} is not "
                f"under any collected package {roots}; collect_submodules will "
                f"NOT bundle it — add an explicit collect_submodules to both specs"
            )


def test_guard_fails_for_an_uncollected_origin():
    """Prove the guard is live: a hypothetical origin whose package the specs do
    not collect must be detected."""
    class _Uncollected:
        origin_id = "fictional"
        requires_build_collection = True
        collected_packages = ("totally_not_bundled_pkg",)
        log_source = "fictional"

        def candidates(self):  # pragma: no cover - never invoked
            return ()

    content = _spec_text("macos")
    origin = _Uncollected()
    missing = [
        p for p in origin.collected_packages
        if f'collect_submodules("{p}")' not in content
    ]
    assert missing == list(origin.collected_packages), (
        "the derivation used by test_spec_collects_every_declared_package would "
        "not have flagged an uncollected origin"
    )


def test_composed_group_is_covered_by_the_same_collect():
    """The composed group was introduced to carry brand-opt-in policy. It must
    not have introduced a second packaging requirement: both groups live under
    the same package root, so the existing collect covers them."""
    assert COMPOSED_ENTRY_POINT_GROUP.startswith(ENTRY_POINT_GROUP), (
        "composed group is expected to be a sub-namespace of the default group"
    )
    roots = {p for o in _COLLECTED for p in o.collected_packages}
    assert "locksmith.plugins" in roots
