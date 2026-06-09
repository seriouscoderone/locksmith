"""Tests for the AppSettingsDialog (toolbar Settings entry)."""
from types import SimpleNamespace

from PySide6.QtWidgets import QLabel, QWidget

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


def test_app_settings_dialog_contains_defaults_section(qapp):
    dialog = AppSettingsDialog(app=_fake_app())
    widgets = dialog.findChildren(QWidget, "defaultsSettingsWidget")
    assert len(widgets) == 1


def test_app_settings_dialog_contains_updates_section(qapp):
    dialog = AppSettingsDialog(app=_fake_app())
    widgets = dialog.findChildren(QWidget, "updatesSettingsWidget")
    assert len(widgets) == 1


def test_app_settings_dialog_wires_check_now_to_controller(qapp):
    called = []
    fake_controller = SimpleNamespace(
        prefs=None,
        check_now=lambda: called.append("check_now"),
    )
    app = SimpleNamespace(update_controller=fake_controller)
    dialog = AppSettingsDialog(app=app)

    btn = dialog.findChild(
        QWidget, "updatesSettingsWidget.checkNowButton"
    )
    assert btn is not None
    btn.click()
    assert called == ["check_now"]


def test_app_settings_dialog_contains_about_section(qapp):
    dialog = AppSettingsDialog(app=_fake_app())
    labels = dialog.findChildren(QLabel, "appSettingsDialog.aboutVersionLabel")
    assert len(labels) == 1
    # Version string format: "Version: <something non-empty>"
    assert labels[0].text().startswith("Version: ")
    assert labels[0].text() != "Version: "


def test_vault_settings_page_no_longer_mounts_updates_widget(qapp):
    """The vault sidebar Settings entry must not double-mount Updates;
    that section lives in the toolbar AppSettingsDialog now."""
    # Build a minimal VaultPage-like parent for SettingsPage construction.
    fake_app = SimpleNamespace(
        vault=None,
        config=LocksmithConfig.get_instance(),
        update_controller=None,
        is_vault_open=False,
    )
    parent = QWidget()
    parent.app = fake_app  # SettingsPage reads `parent.app`

    from locksmith.ui.vault.settings.page import SettingsPage
    page = SettingsPage(parent=parent)

    assert page.findChild(QWidget, "updatesSettingsWidget") is None
    # Sanity: the per-vault Peer Mode placeholder still exists.
    assert page._peer_section_placeholder is not None


def test_vault_settings_page_no_longer_mounts_defaults_widget(qapp):
    fake_app = SimpleNamespace(
        vault=None,
        config=LocksmithConfig.get_instance(),
        update_controller=None,
        is_vault_open=False,
    )
    parent = QWidget()
    parent.app = fake_app

    from locksmith.ui.vault.settings.page import SettingsPage
    page = SettingsPage(parent=parent)

    assert page.findChild(QWidget, "defaultsSettingsWidget") is None
