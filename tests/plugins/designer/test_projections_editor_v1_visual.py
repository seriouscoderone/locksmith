import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.projections import ProjectionsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_projection_rail_items_have_subtitles(qapp, regulator_model):
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "table" in subtitle
    assert "events" in subtitle


def test_projection_pane_uses_source_event_chip_strip(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.source_event_chip_strip import (
        SourceEventChipStrip,
    )
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    strip = page._pane.findChild(SourceEventChipStrip)
    assert strip is not None
    assert "application_recorded" in strip.chip_texts()


def test_projection_pane_renders_dark_fold_expression(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.dark_code_block import DarkCodeBlock
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    block = page._pane.findChild(DarkCodeBlock)
    assert block is not None
    assert "application_recorded" in block.toPlainText() \
        or "events.filter" in block.toPlainText()


def test_projection_pane_uses_view_type_picker(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.view_type_chip_picker import (
        ViewTypeChipPicker,
    )
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    picker = page._pane.findChild(ViewTypeChipPicker)
    assert picker is not None
    assert picker.active_view_type() == "table"


def test_projection_pane_renders_output_schema_table(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.payload_schema_table import (
        PayloadSchemaTable,
    )
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    tables = page._pane.findChildren(PayloadSchemaTable)
    assert len(tables) >= 1
    rows = tables[0].field_rows()
    fields = {r["field"] for r in rows}
    assert {"applicant_aid", "jurisdiction", "received_at"}.issubset(fields)


def test_projection_pane_renders_live_preview_pane(qapp, regulator_model):
    page = ProjectionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.preview_text().lower()
    assert "evaluator pending" in text or "events.filter" in text
