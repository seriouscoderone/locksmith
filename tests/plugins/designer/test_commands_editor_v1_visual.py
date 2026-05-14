import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.commands import CommandsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_command_rail_items_have_subtitles(qapp, regulator_model):
    page = CommandsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    grant_item = rail.item(0)
    text = grant_item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "carrier" in subtitle
    assert "emission" in subtitle


def test_command_right_pane_renders_v1_sections(qapp, regulator_model):
    page = CommandsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "carrier" in text
    assert "license_number" in text
    assert "jurisdiction" in text
    assert "applicant_provided_all_required_fields" in text


def test_command_pane_uses_payload_schema_table(qapp, regulator_model):
    from locksmith.plugins.designer.widgets.payload_schema_table import (
        PayloadSchemaTable,
    )
    page = CommandsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    table = page._pane.findChild(PayloadSchemaTable)
    assert table is not None
    rows = table.field_rows()
    assert len(rows) == 5


def test_command_pane_uses_rule_chip_strip_for_auth_preconditions(
    qapp, regulator_model,
):
    from locksmith.plugins.designer.widgets.rule_chip_strip import (
        RuleChipStrip,
    )
    page = CommandsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    strips = page._pane.findChildren(RuleChipStrip)
    assert len(strips) >= 1
    all_chip_texts = []
    for s in strips:
        all_chip_texts.extend(s.chip_texts())
    assert "applicant_provided_all_required_fields" in all_chip_texts
