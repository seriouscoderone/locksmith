# -*- encoding: utf-8 -*-
"""Reactions editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.reactions import ReactionsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def test_reactions_editor_renders(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "carrier-license-application.json").read_text())
    model = TemplateModel(doc)
    page = ReactionsEditorPage(model=model, crossrefs=compute_crossrefs(doc))
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(150)
    assert page.shell.rail_list.count() == 1
    text = page.section_text()
    assert "credential_received" in text or "grant" in text.lower()
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.grab().save(str(SHOTS_DIR / "reactions_editor.png"))
