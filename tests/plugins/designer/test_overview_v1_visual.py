import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.editors.overview import TemplateOverviewPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_header_has_role_badge_with_government_glyph(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.role_badge.glyph_label.text() == "🏛️"


def test_header_has_version_chip(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.version_chip.text() == "v1.0"


def test_header_subtitle_includes_first_person_role(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    sub = page.role_subtitle.text()
    assert "I am" in sub
    assert "State Department of Insurance" in sub
    assert "government" in sub


def test_header_description_renders(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert "carriers to bear insurance risk" in page.description_label.text()


def test_header_said_truncated(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    text = page.said_label.text()
    assert text.startswith("EGCp")
    assert text.endswith("6yAv")


def test_header_walkthrough_cta_exists(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.walkthrough_button.text() == "Walk me through it"


def test_header_kebab_button_exists(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.kebab_button.text() == "⋯"


def test_overview_renders_eight_facet_cards_no_role_card(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert "role" not in page.card_kinds()
    assert len(page.card_kinds()) == 8


def test_overview_grid_is_four_columns_by_two_rows(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    rows = {page._grid.itemAtPosition(r, c).widget()
            for r in range(2) for c in range(4)
            if page._grid.itemAtPosition(r, c) is not None}
    assert len(rows) == 8


def test_i_issue_card_shows_qualifier_subline(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    card = page._cards["exports"]
    assert card.framing_label.text() == "I ISSUE"
    assert "Carrier License" in card.entries_text()


def test_i_bound_by_card_uses_rule_type_chips(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    card = page._cards["rules"]
    chips = card.chips_text()
    assert "prose" in chips
    assert "predicate" in chips or "predicates" in chips


def test_i_hold_card_uses_root_authority_empty_state(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    card = page._cards["imports"]
    assert "root authority" in card.entries_text()


def test_bottom_strip_renders_ecosystem_chips(qapp, regulator_model):
    page = TemplateOverviewPage(
        model=regulator_model,
        ecosystem_tags=["insurance", "compliance"],
    )
    chip_texts = [c.text() for c in page.ecosystem_chips]
    assert chip_texts == ["insurance", "compliance"]


def test_bottom_strip_renders_lineage_no_parent(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.lineage_label.text() == "No parent template"


def test_bottom_strip_renders_validation_pill(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.bottom_validation_pill.text() == "Valid"
