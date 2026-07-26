# -*- encoding: utf-8 -*-
"""Activation policy must be decided BEFORE a plugin's module is imported.

Defect D1 (see docs/superpowers/specs/2026-07-25-plugin-origin-strategy-design.md):
``_discover_from_entry_points`` called ``ep.load()`` and instantiated the class,
and only *then* consulted the user exclude list and the "an installed clone
already claimed this id" precedence rule. So a plugin the user explicitly
excluded — or one overridden by a clone — still had its module imported and its
constructor executed, running any import-time or ``__init__`` side effect.

The peel and brand-composition checks were already pre-import (they match on
``ep.name``), so the old behavior was internally inconsistent as well as wrong.

These tests observe the defect through a spy entry point: if the loader touches
``.load()`` for a candidate that policy rejects, the spy records it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from locksmith.plugins import manager as manager_module
from locksmith.plugins import storage
from locksmith.plugins.base import PluginCore

SPY_ID = "spy_plugin"


class _SpyPlugin(PluginCore):
    """Minimal loadable plugin; construction is what we assert never happens.

    Subclasses ``PluginCore`` (not ``VaultPlugin``) so it only has to satisfy
    ``plugin_id`` + ``initialize`` — this test is about the import boundary, not
    about vault hooks.
    """

    @property
    def plugin_id(self) -> str:
        return SPY_ID

    def initialize(self, app):
        pass


class _SpyEntryPoint:
    """Stands in for an importlib.metadata EntryPoint.

    ``load()`` is the import boundary: every call is recorded so a test can
    assert the loader never crossed it for a policy-rejected candidate.
    """

    def __init__(self, name: str, calls: list[str]):
        self.name = name
        self.group = manager_module.ENTRY_POINT_GROUP
        self._calls = calls

    def load(self):
        self._calls.append(self.name)
        return _SpyPlugin


@pytest.fixture
def isolated_plugin_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def fake_app():
    from locksmith.core.configing import Environments

    app = MagicMock()
    app.config = SimpleNamespace(base="", environment=Environments.DEVELOPMENT)
    return app


@pytest.fixture
def spy_entry_points(monkeypatch):
    """Replace entry-point discovery with a single spy EP; return the call log."""
    calls: list[str] = []
    ep = _SpyEntryPoint(SPY_ID, calls)

    def _fake_entry_points(*, group=None):
        return [ep] if group == manager_module.ENTRY_POINT_GROUP else []

    monkeypatch.setattr(
        manager_module.importlib.metadata, "entry_points", _fake_entry_points,
    )
    # Neutral brand: neither peel nor composition should interfere.
    monkeypatch.setattr(
        manager_module, "brand",
        lambda: SimpleNamespace(peel_core_pages=False, bundled_plugins=()),
    )
    return calls


def test_excluded_plugin_module_is_never_imported(
    isolated_plugin_root, fake_app, spy_entry_points,
):
    """The user excluded this plugin, so the loader must not import it at all."""
    keri_base = isolated_plugin_root / "keri"
    storage.write_enable_list(keri_base, {"excluded": [SPY_ID]})

    mgr = manager_module.PluginManager(fake_app, keri_base=keri_base)
    mgr.discover()

    assert SPY_ID not in mgr.loaded_ids()
    assert spy_entry_points == [], (
        "loader imported an EXCLUDED plugin's module — policy must be decided "
        "from the candidate's identity before crossing the import boundary"
    )


def test_non_excluded_plugin_is_still_imported(
    isolated_plugin_root, fake_app, spy_entry_points,
):
    """Guard against 'fixing' D1 by never importing anything."""
    keri_base = isolated_plugin_root / "keri"

    mgr = manager_module.PluginManager(fake_app, keri_base=keri_base)
    mgr.discover()

    assert spy_entry_points == [SPY_ID]
    assert SPY_ID in mgr.loaded_ids()


def test_clone_claimed_id_short_circuits_before_import(
    isolated_plugin_root, fake_app, spy_entry_points, monkeypatch,
):
    """An installed clone wins over the in-tree entry point (existing
    precedence). The losing in-tree module must not be imported to discover
    that it lost."""
    keri_base = isolated_plugin_root / "keri"

    # A clone record claiming the same plugin_id, whose files are present.
    clone = storage.plugin_clone_dir(SPY_ID)
    clone.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        storage, "read_index",
        lambda: {"plugins": [{
            "plugin_id": SPY_ID,
            "source": {"type": "local", "path": str(clone)},
            "manifest_snapshot": {"entry_point": "nonexistent_mod:Cls"},
        }]},
    )

    mgr = manager_module.PluginManager(fake_app, keri_base=keri_base)
    mgr.discover()

    # The clone load fails (module does not exist) -> status failed, which is
    # the pre-existing behavior; the point is the in-tree EP was not imported.
    assert spy_entry_points == [], (
        "in-tree entry point was imported even though an installed clone had "
        "already claimed the plugin_id"
    )
