# -*- encoding: utf-8 -*-
"""Aggregates editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.aggregates import AggregatesEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def test_aggregates_editor_renders(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = AggregatesEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert page.shell.rail_list.count() == 1
    text = page.section_text()
    assert "license_register" in text
    assert "witnessed" in text
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "aggregates_editor.png"))
