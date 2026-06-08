"""Tests for UpdateController scaffolding."""
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication, QSettings

from locksmith.update.controller import UpdateController
from locksmith.update.decision import Release, UpdateAction


@pytest.fixture(autouse=True)
def isolate_qsettings(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithTest")
    yield


def _release(**kw):
    defaults = dict(
        version="1.3.0", platform="macos",
        artifact_url="https://x/y", artifact_sha256="abc", artifact_size=1,
        anchor_url="https://x/y.cesr", anchor_said="ESAID",
        is_major=False, is_critical=False,
        release_notes_url="https://x/notes",
        released_at="2026-05-28T00:00:00Z",
        minimum_system_version="13.0",
    )
    defaults.update(kw)
    return Release(**defaults)


def test_controller_constructs_with_current_version(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    assert controller.current_version == "1.2.3"
    assert controller.platform == "macos"


def test_controller_skips_check_when_disabled(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    controller.prefs.check_automatically = False
    fake_fetcher = MagicMock(return_value=_release(version="1.3.0"))
    controller._fetch_latest_release = fake_fetcher

    controller._on_check_requested()
    fake_fetcher.assert_not_called()


def test_controller_evaluates_silent_install_action(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    controller._fetch_latest_release = MagicMock(
        return_value=_release(version="1.3.0"),
    )

    received = []
    controller.action_decided.connect(lambda decision: received.append(decision))

    controller._on_check_requested()
    assert len(received) == 1
    assert received[0].action == UpdateAction.SILENT_INSTALL


def test_controller_emits_check_failed_on_fetch_exception(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")

    def _boom():
        raise RuntimeError("network down")
    controller._fetch_latest_release = _boom

    errors = []
    controller.check_failed.connect(lambda msg: errors.append(msg))
    controller._on_check_requested()
    assert errors == ["network down"]


def test_controller_no_release_returns_silently(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    controller._fetch_latest_release = MagicMock(return_value=None)

    received = []
    controller.action_decided.connect(lambda d: received.append(d))
    controller._on_check_requested()
    assert received == []


def test_controller_no_op_release_emits_no_update_decision(qtbot):
    controller = UpdateController(current_version="1.3.0", platform="macos")
    controller._fetch_latest_release = MagicMock(
        return_value=_release(version="1.3.0"),
    )
    received = []
    controller.action_decided.connect(lambda d: received.append(d))
    controller._on_check_requested()
    assert len(received) == 1
    assert received[0].action == UpdateAction.NO_UPDATE


def test_check_now_triggers_immediate_check(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    controller._fetch_latest_release = MagicMock(
        return_value=_release(version="1.3.0"),
    )
    received = []
    controller.action_decided.connect(lambda d: received.append(d))

    controller.check_now()
    assert len(received) == 1
    assert received[0].action == UpdateAction.SILENT_INSTALL


def test_report_verification_failed_emits_signal(qtbot):
    controller = UpdateController(current_version="1.2.3", platform="macos")
    received = []
    controller.verification_failed.connect(lambda v: received.append(v))
    controller.report_verification_failed("1.3.0")
    assert received == ["1.3.0"]


def test_set_bridge_then_default_fetch_calls_bridge():
    controller = UpdateController(current_version="1.2.3", platform="macos")
    fake_bridge = MagicMock()
    fake_bridge.fetch_latest_release.return_value = _release(version="1.3.0")
    controller.set_bridge(fake_bridge)
    rel = controller._default_fetch_release()
    assert rel.version == "1.3.0"
    fake_bridge.fetch_latest_release.assert_called_once()
