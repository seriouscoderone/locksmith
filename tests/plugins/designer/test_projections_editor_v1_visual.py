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
