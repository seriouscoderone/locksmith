import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.workflows import WorkflowsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_workflow_rail_items_have_subtitles(qapp, regulator_model):
    page = WorkflowsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    grant_item = rail.item(0)
    text = grant_item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "carrier" in subtitle
    assert "5 steps" in subtitle


def test_workflow_pane_renders_trigger_card(qapp, regulator_model):
    page = WorkflowsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "exn_received" in text
    assert "/insurance/cmd/submit_application" in text


def test_workflow_pane_renders_step_details(qapp, regulator_model):
    page = WorkflowsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "intake" in text or "Carrier submits application" in text
    assert "grant_license" in text or "Grant license" in text


def test_workflow_swimlane_v2_step_count(qapp, regulator_model):
    page = WorkflowsEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    assert page.swimlane_step_count() == 5
