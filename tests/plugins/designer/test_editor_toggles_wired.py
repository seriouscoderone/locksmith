import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.validation_panel import ValidationPanel
from locksmith.plugins.designer.widgets.json_source_view import JsonSourceView


@pytest.fixture
def regulator_doc():
    return json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )


@pytest.mark.parametrize("editor_module,editor_class", [
    ("commands", "CommandsEditorPage"),
    ("aggregates", "AggregatesEditorPage"),
    ("reactions", "ReactionsEditorPage"),
    ("workflows", "WorkflowsEditorPage"),
    ("projections", "ProjectionsEditorPage"),
    ("rules", "RulesEditorPage"),
    ("imports", "ImportsEditorPage"),
    ("exports", "ExportsEditorPage"),
])
def test_editor_wires_validation_panel_and_json_source(
    qapp, regulator_doc, editor_module, editor_class,
):
    mod = __import__(
        f"locksmith.plugins.designer.editors.{editor_module}",
        fromlist=[editor_class],
    )
    cls = getattr(mod, editor_class)
    model = TemplateModel(regulator_doc)
    page = cls(model=model, crossrefs=compute_crossrefs(regulator_doc))
    side_layout = page.shell.side_panel_container.layout()
    assert side_layout.count() == 1
    assert isinstance(side_layout.itemAt(0).widget(), ValidationPanel)
    bottom_layout = page.shell.bottom_panel_container.layout()
    assert bottom_layout.count() == 1
    assert isinstance(bottom_layout.itemAt(0).widget(), JsonSourceView)
