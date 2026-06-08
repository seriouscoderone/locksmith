"""Tests for UpdateConsentDialog.

Pure-Python logic only: signal emission, prefs binding, helper static
methods. We construct the dialog under the offscreen Qt platform plugin
so import/init failures surface, but never assert on rendered visuals.
"""
from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication, QLabel

from locksmith.ui.dialogs.update_consent import UpdateConsentDialog
from locksmith.update.prefs import UpdatePrefs


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def _isolate_qsettings(tmp_path, monkeypatch):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path),
    )
    QCoreApplication.setOrganizationName("LocksmithTest")
    QCoreApplication.setApplicationName("LocksmithConsentTest")
    yield


def _all_label_texts(dialog: UpdateConsentDialog) -> list[str]:
    return [w.text() for w in dialog.findChildren(QLabel)]


def test_dialog_constructs():
    dlg = UpdateConsentDialog(prefs=UpdatePrefs())
    assert dlg is not None
    assert dlg.objectName() == "updateConsentDialog"


def test_dialog_exposes_two_named_buttons():
    dlg = UpdateConsentDialog(prefs=UpdatePrefs())
    assert dlg.allow_button is not None
    assert dlg.not_now_button is not None
    assert dlg.allow_button.objectName() == "updateConsentDialog.allowButton"
    assert dlg.not_now_button.objectName() == "updateConsentDialog.notNowButton"


def test_headline_text_present():
    dlg = UpdateConsentDialog(prefs=UpdatePrefs())
    texts = _all_label_texts(dlg)
    assert any("check for updates automatically" in t.lower() for t in texts)


def test_privacy_subtext_mentions_no_telemetry():
    dlg = UpdateConsentDialog(prefs=UpdatePrefs())
    texts = _all_label_texts(dlg)
    assert any("no telemetry" in t.lower() for t in texts)


def test_body_mentions_keri_verification():
    dlg = UpdateConsentDialog(prefs=UpdatePrefs())
    texts = _all_label_texts(dlg)
    body = " ".join(texts).lower()
    assert "keri" in body
    assert "verif" in body  # "verified" / "verification"


def test_accept_sets_both_prefs_to_true():
    prefs = UpdatePrefs()
    prefs.consent_seen = False
    prefs.check_automatically = False
    dlg = UpdateConsentDialog(prefs=prefs)
    dlg._on_accept()
    assert prefs.consent_seen is True
    assert prefs.check_automatically is True


def test_accept_emits_consent_accepted_signal():
    dlg = UpdateConsentDialog(prefs=UpdatePrefs())
    fired = []
    dlg.consent_accepted.connect(lambda: fired.append(True))
    dlg._on_accept()
    assert fired == [True]


def test_decline_marks_consent_seen_but_does_not_change_auto():
    prefs = UpdatePrefs()
    prefs.check_automatically = False  # already off; ensure we don't flip
    prefs.consent_seen = False
    dlg = UpdateConsentDialog(prefs=prefs)
    dlg._on_decline()
    assert prefs.consent_seen is True
    assert prefs.check_automatically is False


def test_decline_emits_consent_declined_signal():
    dlg = UpdateConsentDialog(prefs=UpdatePrefs())
    fired = []
    dlg.consent_declined.connect(lambda: fired.append(True))
    dlg._on_decline()
    assert fired == [True]


def test_should_show_returns_true_when_unseen():
    prefs = UpdatePrefs()
    prefs.consent_seen = False
    assert UpdateConsentDialog.should_show(prefs) is True


def test_should_show_returns_false_when_already_seen():
    prefs = UpdatePrefs()
    prefs.consent_seen = True
    assert UpdateConsentDialog.should_show(prefs) is False
