"""Two defects that sat directly in the landing path.

Both were found while building role-based landing, and both predate it.
"""
from unittest.mock import MagicMock

from PySide6.QtWidgets import QLabel, QWidget

from locksmith.ui.vault.menu import VaultNavMenu
from locksmith.ui.vault.page import VaultPage


def test_a_peeled_menu_reset_does_not_navigate_to_a_core_page(qtbot):
    """`pop_to_vault_menu` activated the first nav item and then emitted
    `identifiers_clicked` UNCONDITIONALLY -- whatever that first item was.

    `identifiers` is a core wallet page. A peeled HOA builds no core nav items
    and registers no such page, so every unlock and every menu reset asked the
    vault page to route to a key that does not exist. Measured in a live
    session: "No page registered for key 'identifiers'" at 23:06:38, the moment
    the vault opened.
    """
    host = QWidget()
    qtbot.addWidget(host)
    peeled = VaultNavMenu(host, include_core_items=False,
                          include_settings_item=True)
    fired = []
    peeled.identifiers_clicked.connect(lambda: fired.append(1))
    peeled.pop_to_vault_menu()
    assert fired == [], "a peeled HOA routed to a core page it never registered"

    core = VaultNavMenu(host, include_core_items=True)
    core_fired = []
    core.identifiers_clicked.connect(lambda: core_fired.append(1))
    core.pop_to_vault_menu()
    assert core_fired == [1], (
        "the stock wallet must still land on identifiers — the guard is about "
        "peeled builds, not about removing the behaviour")


def test_unregistering_the_open_page_moves_the_user_somewhere_real(qtbot):
    """`unregister_page` destroyed the widget and left `_current_page_key`
    naming it, so a live revocation stranded the user on a dead key and the next
    show tried to restore it.

    This is the live-revocation path: the role-gate strategy calls
    `unregister_page` the moment a credential flips satisfied -> unsatisfied,
    with that page on screen.
    """
    page = VaultPage.__new__(VaultPage)
    page._pages = {}
    page._current_page_key = None
    page.content_stack = MagicMock(name="content_stack")
    shown = []
    page._show_page = lambda key: (shown.append(key),
                                   setattr(page, "_current_page_key", key))[0]

    for key in ("home", "cuo"):
        page._pages[key] = QLabel(key)
    page._current_page_key = "cuo"

    page.unregister_page("cuo")

    assert page._current_page_key == "home", "stranded on the destroyed page"
    assert shown == ["home"]


def test_unregistering_some_other_page_leaves_you_where_you_are(qtbot):
    """The redirect must fire only for the page actually on screen."""
    page = VaultPage.__new__(VaultPage)
    page._pages = {"home": QLabel("home"), "cuo": QLabel("cuo")}
    page._current_page_key = "cuo"
    page.content_stack = MagicMock(name="content_stack")
    shown = []
    page._show_page = lambda key: shown.append(key)

    page.unregister_page("home")

    assert page._current_page_key == "cuo"
    assert shown == []
