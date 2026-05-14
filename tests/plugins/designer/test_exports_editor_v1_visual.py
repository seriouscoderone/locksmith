import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.exports import ExportsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_export_rail_items_have_subtitles(qapp, regulator_model):
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "carrier" in subtitle
    assert "4 states" in subtitle


def test_export_pane_has_five_tab_strip(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.editor_tab_bar import EditorTabBar
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    tab_bar = page._pane.findChild(EditorTabBar)
    assert tab_bar is not None
    assert tab_bar.tab_names() == [
        "Envelope", "Schema", "Lifecycle", "Rules", "Value flow",
    ]


def test_export_pane_lifecycle_tab_is_active_by_default(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.editor_tab_bar import EditorTabBar
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    tab_bar = page._pane.findChild(EditorTabBar)
    assert tab_bar.active_tab() == "Lifecycle"


def test_lifecycle_tab_renders_state_machine_diagram(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.state_machine_diagram import (
        StateMachineDiagram,
    )
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    diag = page._pane.findChild(StateMachineDiagram)
    assert diag is not None
    assert diag.state_count == 4


def test_lifecycle_tab_renders_transitions_list_with_rule_refs(
    qapp, regulator_model,
):
    page = ExportsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page._pane.text_summary() + " " + _scrape_lifecycle_text(page)
    assert "license_grant_workflow" in text
    assert "financial_solvency_demonstrated" in text


def _scrape_lifecycle_text(page) -> str:
    from PySide6.QtWidgets import QLabel
    from locksmith.plugins.designer.widgets.rule_chip_strip import RuleChipStrip
    parts: list[str] = []
    for lbl in page._pane.findChildren(QLabel):
        parts.append(lbl.text())
    for strip in page._pane.findChildren(RuleChipStrip):
        parts.extend(strip.chip_texts())
    return " ".join(parts)
