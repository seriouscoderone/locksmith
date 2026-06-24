"""The macOS Sparkle controller must be stored unwrapped so
check_for_updates_with_ui() can call checkForUpdates_ (regression: a 2-tuple
was stored, so hasattr(updater, 'checkForUpdates_') was always False)."""
import sys
import types

import pytest


def test_darwin_stores_controller_not_tuple(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    class FakeController:
        def checkForUpdates_(self, _):
            self.called = True

    fake_controller = FakeController()
    fake_delegate = object()

    fake_init = types.ModuleType("locksmith.update.sparkle_init")
    fake_init.init_sparkle = lambda **kw: (fake_controller, fake_delegate)
    monkeypatch.setitem(sys.modules, "locksmith.update.sparkle_init", fake_init)

    from locksmith.core import apping
    app = apping.LocksmithApplication.__new__(apping.LocksmithApplication)
    app._native_updater = None
    app._native_updater_dll = None
    app._native_updater_callbacks = None
    app._native_updater_delegate = None
    app._init_native_updater()

    assert app._native_updater is fake_controller
    assert hasattr(app._native_updater, "checkForUpdates_")
    assert app._native_updater_delegate is fake_delegate
