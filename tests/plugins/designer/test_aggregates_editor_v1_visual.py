import json
from pathlib import Path

import pytest

from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.editors.aggregates import AggregatesEditorPage
from locksmith.plugins.designer.model import TemplateModel


@pytest.fixture
def regulator_model():
    doc = json.loads(
        (Path(__file__).parent / "fixtures"
         / "regulator-grants-carrier-license.json").read_text()
    )
    return TemplateModel(doc=doc)


def test_aggregate_rail_items_have_subtitles(qapp, regulator_model):
    page = AggregatesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    rail = page.shell.rail_list
    item = rail.item(0)
    text = item.text()
    assert "\n" in text
    subtitle = text.split("\n", 1)[1]
    assert "witnessed" in subtitle
    assert "invariant" in subtitle


def test_aggregate_pane_renders_inception_chip_and_log_scope(
    qapp, regulator_model,
):
    page = AggregatesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    text = page.section_text()
    assert "regulator.licensing.inaugurated" in text
    assert "witnessed" in text


def test_aggregate_pane_renders_invariants_via_rule_chip_strip(
    qapp, regulator_model,
):
    from locksmith.plugins.designer.widgets.rule_chip_strip import RuleChipStrip
    page = AggregatesEditorPage(
        model=regulator_model,
        crossrefs=compute_crossrefs(regulator_model.doc),
    )
    strips = page._pane.findChildren(RuleChipStrip)
    assert len(strips) >= 1
    all_chip_texts: list[str] = []
    for s in strips:
        all_chip_texts.extend(s.chip_texts())
    assert "no_duplicate_active_license_per_carrier" in all_chip_texts
