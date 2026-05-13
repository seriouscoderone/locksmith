# -*- encoding: utf-8 -*-
"""Exports editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.exports import ExportsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def test_exports_editor_renders_state_machine(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    page = ExportsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1200, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(200)
    assert page.shell.rail_list.count() == 1
    assert page.state_count() == 4  # pending, active, suspended, revoked
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "exports_editor.png"))
