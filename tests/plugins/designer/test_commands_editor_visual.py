# -*- encoding: utf-8 -*-
"""Commands editor visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.commands import CommandsEditorPage
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.crossref import compute_crossrefs


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def _grab(w, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    p = SHOTS_DIR / f"{name}.png"
    pix = w.grab()
    assert pix.save(str(p))
    return p


def test_commands_editor_renders_rail_and_sections(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "regulator-grants-carrier-license.json").read_text())
    model = TemplateModel(doc)
    cx = compute_crossrefs(doc)
    page = CommandsEditorPage(model=model, crossrefs=cx)
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(200)

    assert page.shell.rail_list.count() == 1
    text = page.section_text()
    assert "Issue License" in text
    assert "/issue" in text
    _grab(page, "commands_editor")
