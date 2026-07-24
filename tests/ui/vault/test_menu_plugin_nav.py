# -*- encoding: utf-8 -*-
"""Tests for the plugin nav-menu dead-end fix (live-demo regression).

A role-plugin that declares a page but no submenu (get_menu_section() -> [])
must not blank the left nav when its entry is clicked. Two layers of
hardening are covered:

  (a) menu.register_plugin_section auto-injects a menu-owned BackButton when a
      plugin pushes a submenu with no back of its own, so no submenu is ever a
      dead end; it is tracked symmetrically so unregister removes it too.
  (b) VaultPage._on_plugin_entry_clicked opens a page-only plugin's page
      directly (via _show_vault_page) instead of pushing an empty submenu.

Follows the sibling idiom in tests/ui/vault/test_hoa_page.py: a minimal fake
parent exposing ``.app`` (VaultPage.__init__ asserts a non-None parent and
reads parent.app), the qtbot offscreen harness from tests/conftest.py.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, VaultNavMenu
from locksmith.ui.vault.page import VaultPage


def _fake_parent() -> QWidget:
    parent = QWidget()
    plugin_manager = MagicMock()
    plugin_manager.all_states.return_value = []
    parent.app = SimpleNamespace(
        config=SimpleNamespace(), vault=None, plugin_manager=plugin_manager,
    )
    return parent


# -------------------------------------------------------------------------
# Part (a) — menu safety net: auto back-button for empty submenus
# -------------------------------------------------------------------------

def test_register_plugin_section_empty_submenu_gets_back_button(qtbot):
    """A plugin section registered with NO submenu items must still receive a
    menu-owned BackButton so a pushed submenu is never a dead end."""
    menu = VaultNavMenu()
    qtbot.addWidget(menu)

    entry = MenuButton(icon=QIcon())
    menu.register_plugin_section("actuary", entry, [])

    submenu = menu._plugin_menus["actuary"]
    back_buttons = [w for w in submenu if isinstance(w, BackButton)]
    assert len(back_buttons) == 1, "empty submenu must gain exactly one BackButton"


def test_auto_back_button_returns_to_vault_menu(qtbot):
    """Clicking the auto-injected BackButton pops back to the vault menu."""
    menu = VaultNavMenu()
    qtbot.addWidget(menu)

    entry = MenuButton(icon=QIcon())
    menu.register_plugin_section("actuary", entry, [])

    # Push into the (now non-empty) submenu, then click the back button.
    menu.push_plugin_menu("actuary")
    assert menu._active_plugin_id == "actuary"

    back = next(w for w in menu._plugin_menus["actuary"] if isinstance(w, BackButton))
    back.click()

    assert menu._active_plugin_id is None, "back button must return to vault menu"


def test_plugin_section_with_own_back_button_not_duplicated(qtbot):
    """A plugin that supplies its own BackButton must not get a second one."""
    menu = VaultNavMenu()
    qtbot.addWidget(menu)

    entry = MenuButton(icon=QIcon())
    own_back = BackButton(dark_mode=False)
    menu.register_plugin_section("actuary", entry, [own_back])

    back_buttons = [w for w in menu._plugin_menus["actuary"] if isinstance(w, BackButton)]
    assert back_buttons == [own_back], "must not inject a duplicate back button"


def test_unregister_removes_auto_back_button(qtbot):
    """The auto-injected BackButton must be tracked so unregister removes the
    whole section with no leak."""
    menu = VaultNavMenu()
    qtbot.addWidget(menu)

    entry = MenuButton(icon=QIcon())
    menu.register_plugin_section("actuary", entry, [])
    back = next(w for w in menu._plugin_menus["actuary"] if isinstance(w, BackButton))
    assert back in menu._plugin_sections["actuary"]

    menu.unregister_plugin_section("actuary")

    assert "actuary" not in menu._plugin_sections
    assert "actuary" not in menu._plugin_menus
    assert "actuary" not in menu._plugin_nav_buttons


# -------------------------------------------------------------------------
# Part (b) — page-only plugin entry opens its page, no empty submenu push
# -------------------------------------------------------------------------

def test_page_only_plugin_entry_opens_page_without_pushing_menu(qtbot):
    """Clicking a page-only plugin's entry (page registered under plugin_id,
    no submenu nav buttons) must show that page directly and NOT push an empty
    plugin submenu that would blank the nav."""
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = VaultPage(parent)
    qtbot.addWidget(page)

    # A non-AccountProvider plugin whose surface is page-only.
    plugin = SimpleNamespace(plugin_id="actuary")
    parent.app.plugin_manager.get_plugin = MagicMock(return_value=plugin)

    # Reveal the surface exactly like RevealBundledSurface does: a page under
    # the plugin_id key + a menu entry with an empty submenu.
    page.register_page("actuary", QWidget())
    entry = MenuButton(icon=QIcon())
    page.add_menu_entry("actuary", entry, [])

    page._on_plugin_entry_clicked("actuary")

    assert page._current_page_key == "actuary", "page-only plugin must open its page"
    assert page.nav_menu._active_plugin_id is None, "must NOT push an empty plugin submenu"
    # The entry stays highlighted so the nav reflects where the user is.
    assert page.nav_menu._plugin_entry_buttons["actuary"].is_active is True


def test_plugin_with_submenu_pages_still_pushes_menu(qtbot):
    """Regression guard: a plugin WITH submenu nav buttons keeps the existing
    push_plugin_menu + navigate-to-first-page behavior."""
    parent = _fake_parent()
    qtbot.addWidget(parent)
    page = VaultPage(parent)
    qtbot.addWidget(page)

    plugin = SimpleNamespace(plugin_id="actuary")
    parent.app.plugin_manager.get_plugin = MagicMock(return_value=plugin)

    page.register_page("actuary", QWidget())
    entry = MenuButton(icon=QIcon())
    nav_btn = MenuButton(icon=QIcon())
    page.add_menu_entry("actuary", entry, [nav_btn])

    page._on_plugin_entry_clicked("actuary")

    assert page.nav_menu._active_plugin_id == "actuary", "submenu plugin must push its menu"
