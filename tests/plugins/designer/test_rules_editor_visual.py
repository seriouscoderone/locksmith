# -*- encoding: utf-8 -*-
"""Rules editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.rules import RulesEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def test_rules_editor_renders_typed_rail(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = RulesEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    # 7 rules + 4 type-group headers = 11 rows.
    assert page.shell.rail_list.count() == 11
    text = page.section_text().lower()
    # Selected is first rule (issued_under_statutory_authority / legal_prose)
    assert "statutory" in text or "legal_prose" in text or "issued" in text
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "rules_editor.png"))
