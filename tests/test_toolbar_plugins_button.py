"""Tests for `LocksmithToolbar.update_for_config`'s Plugins-button handling
(acceptance-demo fix wave item 6): a peeled HOA build registers no "plugins"
page, so its `HoaVaultPage.get_toolbar_config()` sets `show_plugins_button`
False — this pins the toolbar's OWN reaction to that key. The `HoaVaultPage`
side of the fix (that it actually sets the key) is covered separately in
`tests/ui/vault/test_hoa_page.py`.
"""
from types import SimpleNamespace

from locksmith.ui.toolbar import LocksmithToolbar


def _toolbar(qapp) -> LocksmithToolbar:
    app = SimpleNamespace(vault=None, name=None)
    return LocksmithToolbar(app)


def test_plugins_button_visible_by_default(qapp):
    """Stock behavior, unchanged: omitting `show_plugins_button` entirely
    (as every pre-existing `get_toolbar_config()` caller does) must leave
    the Plugins button visible, matching its previous always-on behavior."""
    tb = _toolbar(qapp)
    try:
        tb.update_for_config({})
        assert tb.plugins_action.isVisible()
    finally:
        tb.deleteLater()


def test_plugins_button_hidden_when_config_says_so(qapp):
    tb = _toolbar(qapp)
    try:
        tb.update_for_config({"show_plugins_button": False})
        assert not tb.plugins_action.isVisible()
    finally:
        tb.deleteLater()


def test_plugins_button_shown_again_after_hidden(qapp):
    """Config is re-applied on every page change (on_page_changed) — a
    later page whose config omits the key (default True) must re-show the
    button, not leave it stuck hidden from a previous peeled page's config."""
    tb = _toolbar(qapp)
    try:
        tb.update_for_config({"show_plugins_button": False})
        assert not tb.plugins_action.isVisible()
        tb.update_for_config({"show_plugins_button": True})
        assert tb.plugins_action.isVisible()
    finally:
        tb.deleteLater()
