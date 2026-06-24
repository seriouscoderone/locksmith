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


def test_darwin_on_failure_routes_to_controller(monkeypatch):
    """on_failure lambda must call update_controller.report_verification_failed."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QSignalSpy

    # Ensure a QApplication exists (no-op if one is already running).
    _qapp = QApplication.instance() or QApplication([])

    monkeypatch.setattr(sys, "platform", "darwin")

    # Capture the on_failure kwarg that init_sparkle receives.
    captured: dict = {}

    class FakeController:
        def checkForUpdates_(self, _):
            pass

    fake_controller = FakeController()
    fake_delegate = object()

    fake_sparkle = types.ModuleType("locksmith.update.sparkle_init")

    def _fake_init_sparkle(**kw):
        captured["on_failure"] = kw["on_failure"]
        return (fake_controller, fake_delegate)

    fake_sparkle.init_sparkle = _fake_init_sparkle
    monkeypatch.setitem(sys.modules, "locksmith.update.sparkle_init", fake_sparkle)

    # Stub _make_update_verifier so it doesn't need a real publisher anchor.
    from locksmith.core import apping as _apping
    monkeypatch.setattr(_apping, "_make_update_verifier", lambda: (lambda staged, info: True))

    # Build just enough of LocksmithApplication for _init_update_controller.
    app = _apping.LocksmithApplication.__new__(_apping.LocksmithApplication)
    app._native_updater = None
    app._native_updater_dll = None
    app._native_updater_callbacks = None
    app._native_updater_delegate = None
    app.update_controller = None  # will be set by _init_update_controller

    app._init_update_controller()

    # After _init_update_controller: update_controller must exist and
    # on_failure must have been captured by our fake init_sparkle.
    assert app.update_controller is not None, "update_controller was not constructed"
    assert "on_failure" in captured, "on_failure kwarg was not passed to init_sparkle"

    spy = QSignalSpy(app.update_controller.verification_failed)
    captured["on_failure"]("0.2.0")
    assert spy.count() == 1, (
        f"verification_failed signal not emitted; spy count={spy.count()}"
    )
