import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.reactions import ReactionsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_reaction_rail_items_have_subtitles(qapp, regulator_model):
    page = ReactionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "exn" in subtitle
    assert "emission" in subtitle


def test_reaction_pane_renders_trigger_card(qapp, regulator_model):
    page = ReactionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "exn_received" in text
    assert "/insurance/cmd/submit_application" in text


def test_reaction_pane_renders_emissions(qapp, regulator_model):
    page = ReactionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "aggregate_event" in text
    assert "license_registry" in text


def test_reaction_pane_renders_failure_policy(qapp, regulator_model):
    page = ReactionsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "log_and_spurn" in text
