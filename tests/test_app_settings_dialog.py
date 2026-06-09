"""Tests for the AppSettingsDialog (toolbar Settings entry)."""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QLabel

from locksmith.ui.dialogs.app_settings import AppSettingsDialog


def _fake_app():
    """A minimal app stub the dialog can read from without a live controller."""
    return SimpleNamespace(update_controller=None)


def test_app_settings_dialog_constructs(qapp):
    dialog = AppSettingsDialog(app=_fake_app())
    assert dialog.objectName() == "appSettingsDialog"
    # Header label visible at the top of the dialog.
    headers = dialog.findChildren(QLabel, "appSettingsDialog.titleLabel")
    assert len(headers) == 1
    assert headers[0].text() == "Settings"
