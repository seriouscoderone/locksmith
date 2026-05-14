import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.editors.overview import TemplateOverviewPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.validation_panel import ValidationPanel
from locksmith.plugins.designer.widgets.json_source_view import JsonSourceView


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_overview_has_toolbar_toggles(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.panel_toggle is not None
    assert page.json_toggle is not None


def test_overview_toggles_show_hide_validation_panel(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    page.show()
    qapp.processEvents()
    assert page.side_panel_container.isVisible() is False
    page.panel_toggle.click()
    qapp.processEvents()
    assert page.side_panel_container.isVisible() is True


def test_overview_toggles_show_hide_json_source(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    page.show()
    qapp.processEvents()
    assert page.bottom_panel_container.isVisible() is False
    page.json_toggle.click()
    qapp.processEvents()
    assert page.bottom_panel_container.isVisible() is True


def test_overview_panels_are_correct_widget_types(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    side_layout = page.side_panel_container.layout()
    bottom_layout = page.bottom_panel_container.layout()
    assert isinstance(side_layout.itemAt(0).widget(), ValidationPanel)
    assert isinstance(bottom_layout.itemAt(0).widget(), JsonSourceView)
