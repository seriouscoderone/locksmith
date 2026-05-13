# -*- encoding: utf-8 -*-
"""Validation panel visual smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.widgets.validation_panel import ValidationPanel
from locksmith.plugins.designer.validation import ValidationEngine


META_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "docs" / "superpowers" / "specs" / "schemas"
    / "micro-app-template.schema.json"
)
SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def test_panel_groups_issues_by_surface(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "broken-references.json").read_text())
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    report = engine.validate(doc)

    panel = ValidationPanel()
    panel.set_report(report)
    panel.resize(400, 600)
    panel.show()
    qapp.processEvents()
    QTest.qWait(150)

    # Broken fixture has cross-ref errors on exports and commands surfaces.
    assert panel.surface_count() >= 2
    assert panel.total_issue_count() >= 3

    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    panel.grab().save(str(SHOTS_DIR / "validation_panel.png"))


def test_panel_emits_signal_on_click(qapp, fixture_dir):
    doc = json.loads((fixture_dir / "broken-references.json").read_text())
    engine = ValidationEngine(meta_schema_path=META_SCHEMA)
    panel = ValidationPanel()
    panel.set_report(engine.validate(doc))
    panel.show()
    qapp.processEvents()
    received: list[tuple[str, str]] = []
    panel.issue_clicked.connect(lambda s, p: received.append((s, p)))
    panel.click_first_issue()
    assert len(received) == 1


def test_panel_empty_report_shows_valid(qapp):
    from locksmith.plugins.designer.validation import ValidationReport
    panel = ValidationPanel()
    panel.set_report(ValidationReport(errors=(), warnings=()))
    panel.show()
    qapp.processEvents()
    assert panel.total_issue_count() == 0
    assert panel.surface_count() == 0
