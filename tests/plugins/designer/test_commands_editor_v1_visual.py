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
