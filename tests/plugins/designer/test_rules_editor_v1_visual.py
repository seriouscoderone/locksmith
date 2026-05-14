import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.rules import RulesEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_rules_editor_has_typed_filter_chip_bar(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.rail_filter_chip_bar import (
        RailFilterChipBar,
    )
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    bar = page.findChild(RailFilterChipBar)
    assert bar is not None
    assert bar.chip_text("all") == "all (7)"
    assert bar.chip_text("prose") == "prose (2)"
    assert bar.chip_text("predicate") == "predicate (3)"
    assert bar.chip_text("validation") == "validation (1)"
    assert bar.chip_text("link") == "link (1)"


def test_rules_editor_rail_groups_by_type(qapp, regulator_model):
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    assert rail.count() == 11  # 7 rules + 4 group headers
    assert rail.item(0).text() == "LEGAL PROSE"


def test_rule_rail_items_have_subtitles(qapp, regulator_model):
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(1)
    assert "\n" in item.text()


def test_rule_pane_renders_type_color_badge(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.type_color_badge import (
        TypeColorBadge,
    )
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    badge = page._pane.findChild(TypeColorBadge)
    assert badge is not None
    assert badge.text() == "LEGAL PROSE"


def test_predicate_rule_renders_dark_expression_block(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.dark_code_block import DarkCodeBlock
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    page.shell.rail_list.setCurrentRow(
        _find_rule_row(page, "financial_solvency_demonstrated"),
    )
    block = page._pane.findChild(DarkCodeBlock)
    assert block is not None
    assert "market_conduct_status" in block.toPlainText() \
        or "lines_of_business" in block.toPlainText()


def test_rule_pane_renders_referenced_from_section(qapp, regulator_model):
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    page.shell.rail_list.setCurrentRow(
        _find_rule_row(page, "financial_solvency_demonstrated"),
    )
    text = page.section_text()
    assert "referenced" in text.lower() or "REFERENCED" in text


def test_binding_link_rule_renders_links_list(qapp, regulator_model):
    page = RulesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    page.shell.rail_list.setCurrentRow(
        _find_rule_row(page, "authority_articulation"),
    )
    text = page.section_text()
    assert "issued_under_statutory_authority" in text
    assert "financial_solvency_demonstrated" in text


def _find_rule_row(page, rule_id: str) -> int:
    from PySide6.QtCore import Qt
    rail = page.shell.rail_list
    for i in range(rail.count()):
        if rail.item(i).data(Qt.UserRole) == rule_id:
            return i
    return -1
