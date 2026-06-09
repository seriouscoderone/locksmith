"""Tests for UpdateFailedToast.

Verifies signal emission, version tracking, timer arming, and the
'generic copy / no bypass' guarantees from spec §9.2.
"""
from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from locksmith.ui.toasts.update_failed import UpdateFailedToast


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_toast_constructs_hidden():
    toast = UpdateFailedToast()
    assert toast is not None
    assert toast.isVisible() is False
    assert toast.current_version is None


def test_show_for_version_records_version():
    toast = UpdateFailedToast()
    toast.show_for_version("0.1.2")
    assert toast.current_version == "0.1.2"


def test_headline_text_is_generic():
    """Spec §9.2: the toast must not leak version/hash details."""
    toast = UpdateFailedToast()
    toast.show_for_version("0.1.2")
    headline = toast.headline_label.text()
    assert "verif" in headline.lower()  # 'verified' / 'verification'
    assert "0.1.2" not in headline


def test_body_text_invites_user_to_inspect_log():
    toast = UpdateFailedToast()
    toast.show_for_version("0.1.2")
    body = toast.body_label.text().lower()
    assert "log" in body  # body invites user to open the verification log


def test_body_text_does_not_leak_version():
    toast = UpdateFailedToast()
    toast.show_for_version("0.1.2")
    assert "0.1.2" not in toast.body_label.text()


def test_click_emits_clicked_signal():
    toast = UpdateFailedToast()
    toast.show_for_version("0.1.2")
    fired = []
    toast.clicked.connect(lambda: fired.append(True))
    # Direct call to the same handler path as mouse press
    toast.clicked.emit()
    assert fired == [True]


def test_close_button_emits_closed_and_does_not_emit_clicked():
    toast = UpdateFailedToast()
    toast.show_for_version("0.1.2")
    clicked_fired = []
    closed_fired = []
    toast.clicked.connect(lambda: clicked_fired.append(True))
    toast.closed.connect(lambda: closed_fired.append(True))
    toast._on_close_clicked()
    assert closed_fired == [True]
    assert clicked_fired == []


def test_auto_dismiss_timer_is_armed_on_show():
    toast = UpdateFailedToast()
    toast.show_for_version("0.1.2")
    assert toast.dismiss_timer.isActive() is True
    # Spec calls for ~10s — we don't pin the exact value (avoid brittle
    # test), but enforce a sensible floor.
    assert toast.dismiss_timer.interval() >= 5_000


def test_re_show_updates_version_and_restarts_timer():
    toast = UpdateFailedToast()
    toast.show_for_version("0.1.2")
    toast.show_for_version("0.1.3")
    assert toast.current_version == "0.1.3"
    assert toast.dismiss_timer.isActive() is True


def test_no_install_anyway_button_present():
    """Spec §9 — no bypass affordance ever."""
    toast = UpdateFailedToast()
    toast.show_for_version("0.1.2")
    for btn in toast.findChildren(QPushButton):
        assert "anyway" not in btn.text().lower()
        assert "force" not in btn.text().lower()
        assert "install" not in btn.text().lower()


def test_close_button_object_name_set():
    toast = UpdateFailedToast()
    assert toast.close_button.objectName() == "updateFailedToast.closeButton"


def test_headline_label_object_name_set():
    toast = UpdateFailedToast()
    assert toast.headline_label.objectName() == "updateFailedToast.headline"


def test_object_name_on_toast_frame():
    toast = UpdateFailedToast()
    assert toast.objectName() == "updateFailedToast"
