"""End-to-end: install a local fixture, simulate a restart, verify it loads + hooks fire.

This test does NOT use the wallet's full GUI startup path — it
constructs PluginManager directly to keep the test hermetic. The
in-core dev-control harness (still present in this branch under
src/locksmith/dev_control.py) is what would drive an actual GUI test;
see Task 16's manual checklist for that exercise.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import logging as stdlib_logging
import pytest

from locksmith.plugins import storage
from locksmith.plugins.installer import PluginInstaller, SourceDescriptor
from locksmith.plugins.manager import PluginManager


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"

# Logger names whose output we want pytest's caplog to see.
# keri.help.ogler loggers are non-propagating; we temporarily flip propagation
# inside the test windows where we assert on log content.
_CAPLOG_TARGETS = ("locksmith.plugins.manager", "echo_app.plugin")


class _CaplogPropagate:
    """Temporarily set propagate=True + level=DEBUG on named loggers.

    keri.help.ogler.getLogger() resets level=CRITICAL and propagate=False on
    every call, including at plugin-module import time.  We work around this by
    monkey-patching ogler.getLogger so that for loggers we own it skips the
    reset and returns the already-configured logger unchanged.
    """
    def __init__(self, names):
        self._names = set(names)
        self._saved: dict[str, tuple[bool, int]] = {}
        self._orig_ogler_get = None

    def _apply(self):
        """(Re-)apply propagation settings."""
        for n in self._names:
            lg = stdlib_logging.getLogger(n)
            lg.propagate = True
            lg.setLevel(stdlib_logging.DEBUG)

    def __enter__(self):
        # Save and apply
        for n in self._names:
            lg = stdlib_logging.getLogger(n)
            self._saved[n] = (lg.propagate, lg.level)
        self._apply()

        # Patch help.ogler.getLogger so plugin-module import doesn't clobber us
        from keri import help as _keri_help
        orig = _keri_help.ogler.getLogger

        def _patched_get_logger(name):
            result = orig(name)
            # If this is one of ours, re-apply our settings immediately.
            if name in self._names:
                result.propagate = True
                result.setLevel(stdlib_logging.DEBUG)
            return result

        self._orig_ogler_get = orig
        _keri_help.ogler.getLogger = _patched_get_logger
        return self

    def __exit__(self, exc_type, exc, tb):
        # Restore ogler.getLogger
        from keri import help as _keri_help
        if self._orig_ogler_get is not None:
            _keri_help.ogler.getLogger = self._orig_ogler_get
        # Restore logger settings
        for n, (prop, lvl) in self._saved.items():
            lg = stdlib_logging.getLogger(n)
            lg.propagate = prop
            lg.setLevel(lvl)


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]
    yield tmp_path
    if "echo_app" in sys.modules:
        del sys.modules["echo_app"]


@pytest.fixture
def fake_app():
    app = MagicMock()
    app.config = SimpleNamespace(base="")
    return app


def test_install_restart_load_lifecycle(isolated_root, fake_app, caplog):
    # 1. Install.
    PluginInstaller().install(
        SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app")),
    )

    # 2. Simulate restart: fresh PluginManager.
    mgr = PluginManager(fake_app, keri_base=isolated_root / "keri")

    # 3. Discover + initialize.
    with _CaplogPropagate(_CAPLOG_TARGETS):
        with caplog.at_level("INFO"):
            mgr.discover()
    assert "echo_app" in mgr.loaded_ids()
    state = mgr.get_state("echo_app")
    assert state.status == "loaded"
    assert any(
        "plugin.initialize plugin_id=echo_app" in rec.getMessage()
        for rec in caplog.records
    )

    # 4. on_app_started fires the AppPlugin hook + service.start.
    caplog.clear()
    with _CaplogPropagate(_CAPLOG_TARGETS):
        with caplog.at_level("INFO"):
            mgr.on_app_started(window=MagicMock())
    msgs = [rec.getMessage() for rec in caplog.records]
    assert any("on_app_started plugin_id=echo_app" in m for m in msgs)
    assert any("service.started plugin_id=echo_app" in m for m in msgs)

    # 5. on_app_stopping reverses in expected order.
    caplog.clear()
    with _CaplogPropagate(_CAPLOG_TARGETS):
        with caplog.at_level("INFO"):
            mgr.on_app_stopping()
    msgs = [rec.getMessage() for rec in caplog.records]
    stop_idx = next(i for i, m in enumerate(msgs) if "service.stopped plugin_id=echo_app" in m)
    hook_idx = next(i for i, m in enumerate(msgs) if "on_app_stopping plugin_id=echo_app" in m)
    assert stop_idx < hook_idx


def test_uninstall_then_restart_omits_plugin(isolated_root, fake_app):
    inst = PluginInstaller()
    inst.install(SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app")))
    inst.uninstall("echo_app")
    mgr = PluginManager(fake_app, keri_base=isolated_root / "keri")
    mgr.discover()
    assert "echo_app" not in mgr.loaded_ids()


def test_exclude_then_restart_skips_plugin(isolated_root, fake_app):
    keri_base = isolated_root / "keri"
    PluginInstaller().install(
        SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app")),
    )
    storage.write_enable_list(keri_base, {"format": 1, "excluded": ["echo_app"]})
    mgr = PluginManager(fake_app, keri_base=keri_base)
    mgr.discover()
    assert "echo_app" not in mgr.loaded_ids()
    assert "echo_app" in mgr.excluded_ids()
