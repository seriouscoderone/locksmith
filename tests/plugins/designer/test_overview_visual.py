# -*- encoding: utf-8 -*-
"""Overview page: structural + visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.overview import TemplateOverviewPage
from locksmith.plugins.designer.model import TemplateModel


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def _grab(widget, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pix = widget.grab()
    assert not pix.isNull()
    assert pix.save(str(path))
    return path


def test_overview_renders_eight_facet_cards(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = TemplateOverviewPage(model=model)
    page.resize(1100, 900)
    page.show()
    qapp.processEvents()
    QTest.qWait(200)

    cards = page.card_kinds()
    expected = [
        "imports", "exports", "commands", "reactions",
        "workflows", "aggregates", "projections", "rules",
    ]
    assert cards == expected
    _grab(page, "overview_regulator_grants_license")


def test_overview_card_emits_drilldown(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = TemplateOverviewPage(model=model)
    received: list[str] = []
    page.drilldown_requested.connect(lambda kind: received.append(kind))
    page.click_card("commands")
    assert received == ["commands"]


def test_overview_header_strip_shows_label_and_role(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = TemplateOverviewPage(model=model)
    page.show()
    qapp.processEvents()
    assert page.header_label_text() == "Regulator Grants Carrier License"
    assert "State Department of Insurance" in page.role_chip_text()
