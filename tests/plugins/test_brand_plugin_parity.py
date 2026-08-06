# -*- encoding: utf-8 -*-
"""Per-brand plugin composition, driven by the REAL brand manifests.

Behavior-preservation oracle for the origin/policy refactor: whatever the
internals look like, each shipped brand must end up with exactly the plugin set
it had before. Reads ``brands/<id>/brand.toml`` through the same
``brandlib.runtime_brand_json`` -> ``branding._from_dict`` path the packaged app
uses, so a brand-config or policy change that silently drops a surface fails here.

Scope, stated precisely: these tests run **from source**, so they would NOT have
caught the 0.3.1 bug — there, discovery was correct and only the *frozen build*
was missing the plugin modules. That class is guarded by
``tests/unit/test_specs_bundle_plugin_origins.py``. What this file catches is the
other half: a brand-config or activation-policy change that drops a surface
before packaging ever enters the picture.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from locksmith.core import branding
from locksmith.plugins import manager as manager_module
from locksmith.plugins import storage

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: What each shipped brand must load from in-tree origins.
#: locksmith: default-on kerifoundation, no composed plugins (no [plugins] table).
#: usurance:  peeled (no kerifoundation) + the three composed surfaces it lists.
EXPECTED: dict[str, set[str]] = {
    "locksmith": {"kerifoundation"},
    "usurance": {"hoa_shell", "actuary", "product_designer", "cuo"},
}


def _real_brand(brand_id: str) -> branding.Brand:
    sys.path.insert(0, str(_REPO_ROOT / "packaging"))
    import brandlib  # noqa: PLC0415 — repo-local build helper

    manifest = tomllib.loads(
        (_REPO_ROOT / "brands" / brand_id / "brand.toml").read_text(encoding="utf-8"))
    return branding._from_dict(brandlib.runtime_brand_json(manifest))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """No ~/.locksmith or ~/.keri access: clone root + keri base are temp."""
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def fake_app():
    from locksmith.core.configing import Environments

    app = MagicMock()
    app.config = SimpleNamespace(base="", environment=Environments.DEVELOPMENT)
    return app


@pytest.mark.parametrize("brand_id", sorted(EXPECTED))
def test_brand_loads_exactly_its_declared_surfaces(
    brand_id, isolated, fake_app, monkeypatch, qtbot,
):
    """qtbot: some plugins build real QWidgets in initialize()."""
    b = _real_brand(brand_id)
    monkeypatch.setattr(manager_module, "brand", lambda: b)

    mgr = manager_module.PluginManager(
        fake_app, keri_base=isolated / f"keri-{brand_id}")
    mgr.discover()

    assert set(mgr.loaded_ids()) == EXPECTED[brand_id], (
        f"brand {brand_id!r} loaded {sorted(mgr.loaded_ids())}, expected "
        f"{sorted(EXPECTED[brand_id])} (peel={b.peel_core_pages}, "
        f"bundled={list(b.bundled_plugins)})"
    )


def test_usurance_gets_the_hoa_shell_that_0_3_1_was_missing(
    isolated, fake_app, monkeypatch, qtbot,
):
    """Named regression: the shipped 0.3.1 Usurance had no hoa_shell, so the
    brand fell back to the vanilla vault picker."""
    b = _real_brand("usurance")
    monkeypatch.setattr(manager_module, "brand", lambda: b)

    mgr = manager_module.PluginManager(fake_app, keri_base=isolated / "keri-u")
    mgr.discover()

    assert "hoa_shell" in mgr.loaded_ids()
    assert "kerifoundation" not in mgr.loaded_ids(), "peel must remove the wallet provider"


def test_locksmith_is_unaffected_by_the_composed_group(
    isolated, fake_app, monkeypatch, qtbot,
):
    """The composed group must not leak into the default brand: Locksmith
    declares no [plugins] table, so none of the composed plugins may load."""
    b = _real_brand("locksmith")
    monkeypatch.setattr(manager_module, "brand", lambda: b)

    mgr = manager_module.PluginManager(fake_app, keri_base=isolated / "keri-l")
    mgr.discover()

    loaded = set(mgr.loaded_ids())
    assert "kerifoundation" in loaded
    assert not (loaded & {"carrier", "hoa_shell", "actuary", "product_designer", "cuo"})
