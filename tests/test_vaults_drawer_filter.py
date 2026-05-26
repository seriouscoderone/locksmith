from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QWidget

from locksmith.ui.vaults.drawer import VaultDrawer


@pytest.fixture
def drawer(qapp):
    vault_names = ["alpha", "albatross", "beta", "balanced", "charlie"]
    parent = QWidget()
    parent.resize(1024, 768)
    parent.app = SimpleNamespace(environments=lambda: list(vault_names))
    toolbar = QWidget(parent)
    toolbar.resize(1024, 60)

    drawer = VaultDrawer(parent=parent, toolbar_ref=toolbar)
    yield drawer
    parent.close()


def _visible_items(drawer):
    return [
        drawer.vault_list.item(i).text()
        for i in range(drawer.vault_list.count())
        if not drawer.vault_list.item(i).isHidden()
    ]


def test_no_query_shows_all_alphabetically(drawer):
    assert _visible_items(drawer) == ["albatross", "alpha", "balanced", "beta", "charlie"]
    assert drawer.empty_state_label.isHidden()


def test_substring_match_hides_non_matches(drawer):
    drawer._filter_vaults("bal")
    assert _visible_items(drawer) == ["balanced"]
    assert drawer.empty_state_label.isHidden()


def test_prefix_matches_sort_above_substring_matches(drawer):
    # "al" prefixes "albatross" and "alpha"; "al" is also a substring of "balanced".
    drawer._filter_vaults("al")
    assert _visible_items(drawer) == ["albatross", "alpha", "balanced"]


def test_empty_state_shown_when_no_match(drawer):
    drawer._filter_vaults("zzz")
    assert _visible_items(drawer) == []
    assert not drawer.empty_state_label.isHidden()
    assert "zzz" in drawer.empty_state_label.text()
    assert drawer.vault_list.isHidden()


def test_clear_query_restores_full_list(drawer):
    drawer._filter_vaults("bal")
    drawer._filter_vaults("")
    assert _visible_items(drawer) == ["albatross", "alpha", "balanced", "beta", "charlie"]
    assert drawer.empty_state_label.isHidden()


def test_show_drawer_widgets_clears_query(drawer):
    drawer.search_field.setText("bal")
    drawer.show_drawer_widgets()
    assert drawer.search_field.text() == ""
    assert _visible_items(drawer) == ["albatross", "alpha", "balanced", "beta", "charlie"]
