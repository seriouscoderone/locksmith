"""Tests for the AppSettingsDialog (toolbar Settings entry)."""
from types import SimpleNamespace

from PySide6.QtWidgets import QLabel

from locksmith.core.configing import LocksmithConfig
from locksmith.ui.dialogs.app_settings import AppSettingsDialog
from locksmith.ui.dialogs.defaults_settings_widget import DefaultsSettingsWidget


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


def test_defaults_widget_binds_temp_toggle_to_config(qapp):
    config = LocksmithConfig.get_instance()
    original = config.temp
    try:
        config.temp = False
        widget = DefaultsSettingsWidget()
        assert widget.objectName() == "defaultsSettingsWidget"
        assert widget.temp_toggle.isChecked() is False

        widget.temp_toggle.setChecked(True)
        assert config.temp is True
    finally:
        config.temp = original


def test_defaults_widget_binds_tier_radio_to_config(qapp):
    config = LocksmithConfig.get_instance()
    original = config.tier
    try:
        config.tier = "low"
        widget = DefaultsSettingsWidget()
        assert widget.tier_low.isChecked() is True

        widget.tier_high.setChecked(True)
        assert config.tier == "high"
    finally:
        config.tier = original


def test_defaults_widget_hides_salt_row_when_algo_is_randy(qapp):
    config = LocksmithConfig.get_instance()
    original_algo = config.algo
    try:
        config.algo = "randy"
        widget = DefaultsSettingsWidget()
        widget.show()  # required for isVisible() to reflect setVisible() state
        try:
            assert widget.salt_row_widget.isVisible() is False

            widget.algo_salty.setChecked(True)
            assert widget.salt_row_widget.isVisible() is True
        finally:
            widget.hide()
    finally:
        config.algo = original_algo
