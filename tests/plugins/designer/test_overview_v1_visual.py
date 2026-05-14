import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.editors.overview import TemplateOverviewPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_header_has_role_badge_with_government_glyph(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.role_badge.glyph_label.text() == "🏛️"


def test_header_has_version_chip(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.version_chip.text() == "v1.0"


def test_header_subtitle_includes_first_person_role(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    sub = page.role_subtitle.text()
    assert "I am" in sub
    assert "State Department of Insurance" in sub
    assert "government" in sub


def test_header_description_renders(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert "carriers to bear insurance risk" in page.description_label.text()


def test_header_said_truncated(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    text = page.said_label.text()
    assert text.startswith("EGCp")
    assert text.endswith("6yAv")


def test_header_walkthrough_cta_exists(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.walkthrough_button.text() == "Walk me through it"


def test_header_kebab_button_exists(qapp, regulator_model):
    page = TemplateOverviewPage(model=regulator_model)
    assert page.kebab_button.text() == "⋯"
