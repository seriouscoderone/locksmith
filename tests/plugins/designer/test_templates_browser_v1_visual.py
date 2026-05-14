import pytest

from locksmith.plugins.designer.editors.templates_browser import (
    TemplatesBrowserPage,
)
from locksmith.plugins.designer.store import TemplateStore


@pytest.fixture
def seeded_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCKSMITH_DESIGNER_SEED_FIXTURES", "1")
    from locksmith.plugins.designer import seed_fixtures
    store = TemplateStore(root=tmp_path)
    seed_fixtures.maybe_seed(store)
    return store


def test_count_summary_reflects_valid_and_draft_totals(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    assert page.summary_label.text() == "2 templates · 2 valid · 0 drafts"


def test_filter_strip_has_validity_role_ecosystem_facets(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    chips = page.filter_chips_text()
    assert "All (2)" in chips
    assert "Valid (2)" in chips
    assert "Draft (0)" in chips
    assert "government (1)" in chips
    assert "organization (1)" in chips
    assert "insurance (2)" in chips


def test_grid_renders_two_cards_in_two_up(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    assert page.card_count() == 2
