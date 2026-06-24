"""UpdateController now owns prefs+scheduler and routes checks to a native
callback; it no longer does JSON discovery or emit action_decided."""
from locksmith.update.controller import UpdateController
from locksmith.update.prefs import UpdatePrefs


def test_check_now_invokes_on_check_even_when_auto_disabled():
    calls = []
    prefs = UpdatePrefs()
    prefs.check_automatically = False
    ctrl = UpdateController(prefs=prefs, on_check=lambda: calls.append(1))
    ctrl.check_now()
    assert calls == [1]  # manual bypasses the auto pref (SEV 3 fix)


def test_scheduled_tick_honors_auto_pref():
    calls = []
    prefs = UpdatePrefs()
    prefs.check_automatically = False
    ctrl = UpdateController(prefs=prefs, on_check=lambda: calls.append(1))
    ctrl.scheduler.trigger_now()      # simulate a scheduler tick
    assert calls == []                # suppressed when auto is off
    prefs.check_automatically = True
    ctrl.scheduler.trigger_now()
    assert calls == [1]


def test_report_verification_failed_emits_signal(qtbot=None):
    from PySide6.QtTest import QSignalSpy
    ctrl = UpdateController(on_check=lambda: None)
    spy = QSignalSpy(ctrl.verification_failed)
    ctrl.report_verification_failed("0.2.0")
    assert spy.count() == 1
