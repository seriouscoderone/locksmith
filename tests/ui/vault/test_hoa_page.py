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

# Settings is the ONE core page a peeled HOA deliberately keeps, and the ONE core
# nav button with it: peer transport is configured there and nowhere else, so a
# peeled build without it could not enable its own listener, be dialled, or reach
# its own admin (HoaVaultPage._register_core_pages / _create_nav_menu spell this
# out; the §8.4 manual demo pass is what forced it). The three assertions below
# predate that decision and had been failing since it landed -- red for a product
# choice, which is the state where nobody reads the suite.
_PEELED_PAGE_KEYS_ADMITTED = {"settings"}
_PEELED_NAV_BUTTON_NAMES = _CORE_NAV_BUTTON_NAMES - {"vaultNavMenu.settingsButton"}


def test_hoa_page_registers_no_core_wallet_pages_except_settings(qtbot):
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)
    # Core wallet page keys that stock Locksmith registers in _register_core_pages()
    core_keys = {"identifiers", "credentials", "groups", "remotes", "settings", "notifications"}
    registered = set(page.registered_page_keys())
    admitted = core_keys & registered
    # Asserted as EQUALITY, not disjointness: the point is that exactly one core
    # page is re-admitted, so re-admitting a second (say "identifiers", which would
    # bring the wallet surface back) fails here instead of quietly widening the peel.
    assert admitted == _PEELED_PAGE_KEYS_ADMITTED, (
        f"peeled HOA admits {admitted}, expected exactly {_PEELED_PAGE_KEYS_ADMITTED}")


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

    assert page.nav_menu.credentials_nav_buttons == []

    found_names = {
        btn.objectName()
        for btn in page.nav_menu.findChildren(QPushButton)
        if btn.objectName()
    }
    assert found_names.isdisjoint(_PEELED_NAV_BUTTON_NAMES)
    # ...and the one button that IS kept is present, so a peel that swallows
    # Settings again (leaving the build unable to configure its transport) fails.
    assert "vaultNavMenu.settingsButton" in found_names


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
    assert found_names.isdisjoint(_PEELED_NAV_BUTTON_NAMES)


def test_hoa_page_toolbar_config_hides_plugins_and_notifications(qtbot):
    """Acceptance-demo fix wave item 6: neither "plugins" nor
    "notifications" is ever registered for a peeled HOA build (see
    ``test_hoa_page_registers_no_core_wallet_pages_except_settings`` above), so
    their toolbar icons must be hidden rather than dead clicks (live log: "No
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


def test_peeled_page_never_defaults_to_an_unregistered_page(qtbot):
    """``VaultPage`` hardcoded "identifiers" as both the back-navigation target and
    ``on_show``'s restore key. A peeled HOA registers no such page, so both pointed
    at a page that does not exist: the navigation was a silent no-op and
    ``_show_page`` logged ERROR "No page registered for key 'identifiers'" on a
    completely healthy HOA — teaching everyone to ignore that message, which is the
    only thing that would report a REAL missing page.

    Both now resolve through ``default_page_key()`` against the live registry."""
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = HoaVaultPage(parent)
    qtbot.addWidget(page)

    registered = set(page.registered_page_keys())
    assert page.default_page_key() in registered
    assert page._previous_vault_page_key in registered
    assert page.default_page_key() != "identifiers"

    # "home" is registered by hoa_shell, not by this class, so with only the core
    # peel in place the honest answer is "settings" -- never a dead key.
    assert page.default_page_key() == "settings"
    page.register_page("home", QWidget())
    assert page.default_page_key() == "home", "home must win once it exists"


def test_stock_vault_page_default_is_still_identifiers(qtbot):
    """Sanity guard: the stock wallet's behaviour is unchanged by the hook."""
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = VaultPage(parent)
    qtbot.addWidget(page)
    assert page.default_page_key() == "identifiers"
    assert page._previous_vault_page_key == "identifiers"


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
