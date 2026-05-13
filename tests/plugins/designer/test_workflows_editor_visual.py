# -*- encoding: utf-8 -*-
"""Workflows editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.workflows import WorkflowsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def test_workflows_editor_renders_swimlane(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = WorkflowsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1200, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(200)
    assert page.shell.rail_list.count() == 1
    assert page.swimlane_step_count() == 3  # review_application has 3 steps
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "workflows_editor.png"))
