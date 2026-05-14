# -*- encoding: utf-8 -*-
"""Projections editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.projections import ProjectionsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def test_projections_editor_renders(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = ProjectionsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1200, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert page.shell.rail_list.count() == 2
    assert page.preview_visible() is True
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "projections_editor.png"))


def test_projections_editor_preview_fallback_when_no_evaluator(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = ProjectionsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.show()
    qapp.processEvents()
    text = page.preview_text().lower()
    # When no UEL evaluator is importable, fallback shows the raw expression
    # with an explicit "evaluator pending" note.
    assert "evaluator pending" in text or "license.issued" in text
