"""Tests for UpdatesSettingsWidget.

Asserts: prefs binding (toggle <-> UpdatePrefs.check_automatically),
callback invocation, last-checked label updates, object-name selectors.
"""
from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication, QLabel

from locksmith.ui.vault.settings.updates_widget import (
    UpdatesSettingsWidget,
)
from locksmith.update.prefs import UpdatePrefs


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def _isolate_qsettings(tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path),
    )
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithUpdatesTest")
    yield


def test_widget_constructs():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    assert w is not None
    assert w.objectName() == "updatesSettingsWidget"


def test_toggle_default_reflects_existing_pref_value():
    prefs = UpdatePrefs()
    prefs.check_automatically = True
    w = UpdatesSettingsWidget(prefs=prefs)
    assert w.auto_check_toggle.isChecked() is True


def test_toggle_default_reflects_disabled_pref():
    prefs = UpdatePrefs()
    prefs.check_automatically = False
    w = UpdatesSettingsWidget(prefs=prefs)
    assert w.auto_check_toggle.isChecked() is False


def test_toggle_writes_to_prefs_when_user_toggles_off():
    prefs = UpdatePrefs()
    prefs.check_automatically = True
    w = UpdatesSettingsWidget(prefs=prefs)
    w.auto_check_toggle.setChecked(False)
    assert prefs.check_automatically is False


def test_toggle_writes_to_prefs_when_user_toggles_on():
    prefs = UpdatePrefs()
    prefs.check_automatically = False
    w = UpdatesSettingsWidget(prefs=prefs)
    w.auto_check_toggle.setChecked(True)
    assert prefs.check_automatically is True


def test_set_auto_check_does_not_double_write_prefs():
    """Programmatic set_auto_check must NOT trip the pref-write handler.

    Otherwise the controller updating the widget state would clobber
    the user's preference with the displayed value.
    """
    prefs = UpdatePrefs()
    prefs.check_automatically = True
    w = UpdatesSettingsWidget(prefs=prefs)
    # Now simulate the controller programmatically toggling display:
    w.set_auto_check(False)
    # Pref must NOT have been overwritten by the programmatic set.
    assert prefs.check_automatically is True
    # But the display did flip:
    assert w.auto_check_toggle.isChecked() is False


def test_check_now_invokes_callback():
    fired = []
    w = UpdatesSettingsWidget(
        prefs=UpdatePrefs(),
        check_now_callback=lambda: fired.append("now"),
    )
    w.check_now_button.click()
    assert fired == ["now"]


def test_check_now_without_callback_is_noop():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    # Must not raise even when no callback is wired yet.
    w.check_now_button.click()


def test_view_log_invokes_callback():
    fired = []
    w = UpdatesSettingsWidget(
        prefs=UpdatePrefs(),
        view_log_callback=lambda: fired.append("log"),
    )
    w.view_log_button.click()
    assert fired == ["log"]


def test_view_log_without_callback_is_noop():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    w.view_log_button.click()


def test_set_last_checked_updates_label():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    w.set_last_checked("2026-06-07 10:15 UTC")
    assert "2026-06-07" in w.last_checked_value.text()


def test_set_last_checked_none_renders_never():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    w.set_last_checked("2026-06-07 10:15 UTC")
    w.set_last_checked(None)
    assert w.last_checked_value.text() == "Never"


def test_default_last_checked_is_never():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    assert w.last_checked_value.text() == "Never"


def test_buttons_have_object_names():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    assert w.check_now_button.objectName() == (
        "updatesSettingsWidget.checkNowButton"
    )
    assert w.view_log_button.objectName() == (
        "updatesSettingsWidget.viewLogButton"
    )
    assert w.auto_check_toggle.objectName() == (
        "updatesSettingsWidget.autoCheckToggle"
    )


def test_late_bind_check_now_callback():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    fired = []
    w.set_check_now_callback(lambda: fired.append("late"))
    w.check_now_button.click()
    assert fired == ["late"]


def test_late_bind_view_log_callback():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    fired = []
    w.set_view_log_callback(lambda: fired.append("late"))
    w.view_log_button.click()
    assert fired == ["late"]


def test_header_label_present():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    labels = w.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    assert "Updates" in texts


def test_subheader_mentions_keri_verification():
    w = UpdatesSettingsWidget(prefs=UpdatePrefs())
    labels = w.findChildren(QLabel)
    blob = " ".join(lbl.text() for lbl in labels).lower()
    assert "keri" in blob
    assert "verif" in blob
