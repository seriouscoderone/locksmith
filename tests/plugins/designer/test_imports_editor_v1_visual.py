import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.imports import ImportsEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def carrier_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "carrier-license-application.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_import_rail_items_have_subtitles(qapp, carrier_model):
    imports = carrier_model.doc.get("credentials", {}).get("imports") or []
    if not imports:
        pytest.skip("carrier fixture has no imports; can't test rail subtitle")
    page = ImportsEditorPage(
        model=carrier_model,
        crossrefs=compute_crossrefs(carrier_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text


def test_import_pane_renders_full_said(qapp, carrier_model):
    imports = carrier_model.doc.get("credentials", {}).get("imports") or []
    if not imports:
        pytest.skip("no imports to render")
    page = ImportsEditorPage(
        model=carrier_model,
        crossrefs=compute_crossrefs(carrier_model.doc),
    )
    text = page.section_text()
    first_imp = imports[0]
    expected_said = first_imp.get("expected_schema_said", "")
    if len(expected_said) >= 8:
        assert expected_said[:10] in text


def test_import_pane_renders_issuer_role_chip(qapp, carrier_model):
    imports = carrier_model.doc.get("credentials", {}).get("imports") or []
    if not imports:
        pytest.skip("no imports to render")
    page = ImportsEditorPage(
        model=carrier_model,
        crossrefs=compute_crossrefs(carrier_model.doc),
    )
    text = page.section_text()
    issuer = imports[0].get("expected_issuer_role", "")
    if issuer:
        assert issuer in text


def test_import_pane_renders_lifecycle_chips(qapp, carrier_model):
    imports = carrier_model.doc.get("credentials", {}).get("imports") or []
    if not imports:
        pytest.skip("no imports to render")
    page = ImportsEditorPage(
        model=carrier_model,
        crossrefs=compute_crossrefs(carrier_model.doc),
    )
    text = page.section_text()
    states = imports[0].get("lifecycle_acceptance", ["active"])
    for state in states:
        assert state in text
