# -*- encoding: utf-8 -*-
"""Visual + structural smoke test for GraphCanvasToolbar."""
from __future__ import annotations
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

# Load Qt resources so icon paths like ":/assets/material-icons/schema.svg"
# resolve. main.py imports this for the same effect at app startup.
import locksmith.resources_rc  # noqa: F401

from locksmith.plugins.ecosystem_viewer.db import EcosystemRecord
from locksmith.plugins.ecosystem_viewer.graph_view import (
    EcosystemGraphView,
    GraphCanvasToolbar,
)


SHOTS_DIR = Path(__file__).parent / "_screenshots"


def _grab(widget, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pixmap = widget.grab()
    assert pixmap.save(str(path))
    return path


def test_canvas_toolbar_renders_three_buttons(qapp):
    bar = GraphCanvasToolbar()
    bar.resize(bar.sizeHint())
    bar.show()
    QTest.qWait(100)
    qapp.processEvents()

    captured = []
    bar.add_schema_clicked.connect(lambda: captured.append("schema"))
    bar.add_aid_clicked.connect(lambda: captured.append("aid"))
    bar.add_role_clicked.connect(lambda: captured.append("role"))

    from PySide6.QtWidgets import QToolButton
    buttons = bar.findChildren(QToolButton)
    assert len(buttons) == 3
    tooltips = [b.toolTip() for b in buttons]
    assert tooltips == [
        "Add schema to ecosystem",
        "Add issuer AID to ecosystem",
        "Add role to ecosystem",
    ]
    for b in buttons:
        # Icons are loaded as Qt resources — the icon should be non-null.
        assert not b.icon().isNull(), (
            f"button with tooltip '{b.toolTip()}' has no icon — Qt resources may "
            f"not be initialized in the test (does main.py import resources_rc?)"
        )
        b.click()
    qapp.processEvents()
    assert captured == ["schema", "aid", "role"]

    shot = _grab(bar, "graph_canvas_toolbar")
    assert shot.exists()


def test_graph_view_overlays_canvas_toolbar_top_left(qapp):
    eco = EcosystemRecord(
        name="Insurance",
        schema_saids=[],
        issuer_aids=[],
        role_names=[],
        issuer_qualification_rules={},
    )
    view = EcosystemGraphView()
    view.resize(600, 400)
    view.render_ecosystem(eco, vault=None)
    view.show()
    QTest.qWait(200)
    qapp.processEvents()

    bar = view._canvas_toolbar
    assert bar.isVisible()
    # Toolbar should be near the top-left, inside the view bounds.
    assert bar.x() < 30
    assert bar.y() < 30
    assert bar.x() + bar.width() < view.width()

    # Signals proxy through to view-level signals.
    captured = []
    view.add_schema_clicked.connect(lambda: captured.append("schema"))
    view.add_role_clicked.connect(lambda: captured.append("role"))
    bar.add_schema_clicked.emit()
    bar.add_role_clicked.emit()
    qapp.processEvents()
    assert captured == ["schema", "role"]

    shot = _grab(view, "graph_view_with_canvas_toolbar")
    assert shot.exists()
