# -*- encoding: utf-8 -*-
"""Tests for HoaVaultPage — the peel-light VaultPage that suppresses the
built-in wallet pages for an HOA shell while keeping the string-keyed page
registry and the plugin surface intact.

VaultPage.__init__ requires a non-None parent exposing an ``.app`` attribute
(it asserts on this and reads ``parent.app`` unconditionally), so tests build
a minimal fake parent — the same pattern used elsewhere in this repo, e.g.
tests/test_keri_v2_compat.py::test_add_identifier_flow_opens_dialog_with_keri_v2_salt.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtWidgets import QPushButton, QWidget

from locksmith.ui.vault.hoa_page import HoaVaultPage
from locksmith.ui.vault.menu import MenuButton
from locksmith.ui.vault.page import VaultPage


def _fake_parent() -> QWidget:
    parent = QWidget()
    plugin_manager = MagicMock()
    plugin_manager.all_states.return_value = []
    parent.app = SimpleNamespace(
        config=SimpleNamespace(), vault=None, plugin_manager=plugin_manager,
    )
    return parent


# objectName suffixes stamped on the core-page nav buttons in
# VaultNavMenu._add_menu_items()/_create_credentials_menu_items(). These are
# the buttons that must NOT appear on an HOA build since no widget is
# registered under their page keys (see hoa_page.py module docstring).
_CORE_NAV_BUTTON_NAMES = {
    "vaultNavMenu.identifiersButton",
    "vaultNavMenu.remoteIdentifiersButton",
    "vaultNavMenu.groupIdentifiersButton",
    "vaultNavMenu.credentialsButton",
    "vaultNavMenu.settingsButton",
    "vaultNavMenu.credentialsBackButton",
    "vaultNavMenu.issuedCredentialsButton",
    "vaultNavMenu.receivedCredentialsButton",
    "vaultNavMenu.schemaButton",
}


def test_hoa_page_registers_no_core_wallet_pages(qtbot):
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)
    # Core wallet page keys that stock Locksmith registers in _register_core_pages()
    core_keys = {"identifiers", "credentials", "groups", "remotes", "settings", "notifications"}
    assert core_keys.isdisjoint(set(page.registered_page_keys()))


def test_hoa_page_still_accepts_plugin_pages(qtbot):
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)
    page.register_page("carrier", QWidget())
    assert "carrier" in page.registered_page_keys()


def test_hoa_page_nav_menu_has_no_core_page_buttons(qtbot):
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)

    assert page.nav_menu.nav_buttons == []
    assert page.nav_menu.credentials_nav_buttons == []

    found_names = {
        btn.objectName()
        for btn in page.nav_menu.findChildren(QPushButton)
        if btn.objectName()
    }
    assert found_names.isdisjoint(_CORE_NAV_BUTTON_NAMES)


def test_hoa_page_nav_menu_still_shows_plugin_entries(qtbot):
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)

    entry_button = MenuButton(icon=__import__("PySide6.QtGui", fromlist=["QIcon"]).QIcon())
    entry_button.setObjectName("vaultNavMenu.carrierEntryButton")
    page.nav_menu.register_plugin_section("carrier", entry_button, [])

    found_names = {
        btn.objectName()
        for btn in page.nav_menu.findChildren(QPushButton)
        if btn.objectName()
    }
    assert "vaultNavMenu.carrierEntryButton" in found_names
    assert found_names.isdisjoint(_CORE_NAV_BUTTON_NAMES)


def test_hoa_page_toolbar_config_hides_plugins_and_notifications(qtbot):
    """Acceptance-demo fix wave item 6: neither "plugins" nor
    "notifications" is ever registered for a peeled HOA build (see
    ``test_hoa_page_registers_no_core_wallet_pages`` above), so their
    toolbar icons must be hidden rather than dead clicks (live log: "No
    page registered for key 'plugins'")."""
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)

    config = page.get_toolbar_config()
    assert config["show_plugins_button"] is False
    assert config["show_notifications_button"] is False
    # Untouched keys still come from the stock VaultPage config.
    assert config["show_vaults_button"] is True
    assert config["show_settings_button"] is True


def test_default_vault_page_toolbar_config_unaffected(qtbot):
    """Sanity guard: the stock (non-HOA) VaultPage's toolbar config must
    stay byte-for-behavior unchanged — no `show_plugins_button` key at all
    (the toolbar's own default of True applies)."""
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = VaultPage(parent)
    qtbot.addWidget(page)
    config = page.get_toolbar_config()
    assert "show_plugins_button" not in config


def test_default_vault_page_still_has_core_nav_buttons(qtbot):
    """Sanity guard: the DEFAULT (non-HOA) VaultPage must be byte-for-behavior
    unchanged — it still shows every core-page nav button."""
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = VaultPage(parent)
    qtbot.addWidget(page)

    found_names = {
        btn.objectName()
        for btn in page.nav_menu.findChildren(QPushButton)
        if btn.objectName()
    }
    assert _CORE_NAV_BUTTON_NAMES.issubset(found_names)
