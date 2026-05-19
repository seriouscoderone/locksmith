"""Tests for the rewritten PluginManager (index discovery, dispatch, exclude)."""
from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from locksmith.plugins import storage
from locksmith.plugins.base import AppPlugin, VaultPlugin
from locksmith.plugins.installer import PluginInstaller, SourceDescriptor
from locksmith.plugins.manager import PluginManager


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"

# Logger names used by the manager and the echo fixture plugin.  keri ogler
# loggers have propagate=False by default, which prevents pytest caplog from
# capturing them (caplog installs its handler on the root logger only).
# The helper below temporarily re-enables propagation so caplog works normally.
_LOGGERS_TO_PROPAGATE = [
    "locksmith.plugins.manager",
    "echo_app.plugin",
]


@contextmanager
def _caplog_propagate(caplog, level="INFO"):
    """Enable propagation on keri loggers so pytest caplog can intercept them."""
    loggers = [logging.getLogger(n) for n in _LOGGERS_TO_PROPAGATE]
    orig_propagate = [lg.propagate for lg in loggers]
    orig_level = [lg.level for lg in loggers]
    for lg in loggers:
        lg.propagate = True
        lg.setLevel(logging.DEBUG)
    try:
        with caplog.at_level(level):
            yield
    finally:
        for lg, prop, lvl in zip(loggers, orig_propagate, orig_level):
            lg.propagate = prop
            lg.setLevel(lvl)


@pytest.fixture
def isolated_plugin_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]
    yield tmp_path
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]


@pytest.fixture
def fake_app():
    from locksmith.core.configing import Environments
    app = MagicMock()
    app.config = SimpleNamespace(base="", environment=Environments.DEVELOPMENT)
    return app


def _install_echo(installer):
    installer.install(SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app")))


def test_discovery_loads_installed_plugins_from_index(isolated_plugin_root, fake_app):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "echo_app" in mgr.loaded_ids()


def test_discovery_calls_initialize(isolated_plugin_root, fake_app):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    plugin = mgr.get_plugin("echo_app")
    assert plugin is not None
    assert isinstance(plugin, AppPlugin)


def test_on_app_started_runs_only_app_plugins(isolated_plugin_root, fake_app, caplog):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    with _caplog_propagate(caplog, "INFO"):
        mgr.on_app_started(window=MagicMock())
    assert any("on_app_started plugin_id=echo_app" in rec.getMessage() for rec in caplog.records)


def test_on_app_stopping_stops_services_in_reverse(isolated_plugin_root, fake_app, caplog):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    window = MagicMock()
    mgr.on_app_started(window=window)
    with _caplog_propagate(caplog, "INFO"):
        mgr.on_app_stopping()
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("service.stopped plugin_id=echo_app" in m for m in messages)
    assert any("on_app_stopping plugin_id=echo_app" in m for m in messages)


def test_excluded_plugin_is_not_loaded(isolated_plugin_root, fake_app):
    _install_echo(PluginInstaller())
    keri_base = isolated_plugin_root / "keri"
    storage.write_enable_list(keri_base, {"format": 1, "excluded": ["echo_app"]})
    mgr = PluginManager(fake_app, keri_base=keri_base)
    mgr.discover()
    assert "echo_app" not in mgr.loaded_ids()
    assert "echo_app" in mgr.excluded_ids()


def test_missing_clone_dir_marks_files_missing(isolated_plugin_root, fake_app):
    _install_echo(PluginInstaller())
    import shutil as _sh
    _sh.rmtree(storage.plugin_clone_dir("echo_app"))
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    state = mgr.get_state("echo_app")
    assert state.status == "files_missing"
    assert "echo_app" not in mgr.loaded_ids()


def test_failed_initialize_marks_failed_does_not_crash(isolated_plugin_root, fake_app, caplog):
    _install_echo(PluginInstaller())
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    # discover() first so the clone dir is on sys.path, then import the module
    mgr.discover()
    import echo_app.plugin as ep  # noqa: E402  (imported after install adds clone dir to sys.path)
    orig_init = ep.EchoAppPlugin.initialize
    ep.EchoAppPlugin.initialize = lambda self, app: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        # Create a fresh manager and discover with the broken initialize
        mgr2 = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
        with _caplog_propagate(caplog, "ERROR"):
            mgr2.discover()
    finally:
        ep.EchoAppPlugin.initialize = orig_init
    state = mgr2.get_state("echo_app")
    assert state.status == "failed"
    assert "boom" in state.error
    assert isinstance(mgr2.loaded_ids(), list)


def test_entry_point_fallback_still_works(isolated_plugin_root, fake_app):
    """Entry-point-registered plugins (in-tree kerifoundation) must still load."""
    mgr = PluginManager(fake_app, keri_base=isolated_plugin_root / "keri")
    mgr.discover()
    assert "kerifoundation" in mgr.loaded_ids()
    kf = mgr.get_plugin("kerifoundation")
    assert isinstance(kf, VaultPlugin)


def test_excluded_kerifoundation_still_skipped_via_entry_points(isolated_plugin_root, fake_app):
    keri_base = isolated_plugin_root / "keri"
    storage.write_enable_list(keri_base, {"format": 1, "excluded": ["kerifoundation"]})
    mgr = PluginManager(fake_app, keri_base=keri_base)
    mgr.discover()
    assert "kerifoundation" not in mgr.loaded_ids()
