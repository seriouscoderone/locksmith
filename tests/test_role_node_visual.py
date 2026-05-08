from __future__ import annotations
from pathlib import Path
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from locksmith.plugins.ecosystem_viewer.graph_items import RoleNode

SHOTS_DIR = Path(__file__).parent / "_screenshots"


def _grab(widget, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pixmap = widget.grab()
    assert pixmap.save(str(path))
    return path


def test_role_node_renders_hexagon_with_label_and_member_count(qapp):
    scene = QGraphicsScene()
    view = QGraphicsView(scene)
    view.resize(360, 200)

    node = RoleNode(role_name="state-doi", member_count=3)
    node.setPos(QPointF(40, 40))
    scene.addItem(node)

    other = RoleNode(role_name="aggregator", member_count=0)
    other.setPos(QPointF(180, 40))
    scene.addItem(other)

    view.show()
    QTest.qWait(200)
    qapp.processEvents()

    assert node.role_name == "state-doi"
    assert node.member_count == 3
    assert node.boundingRect().width() == 64
    items = scene.items()
    assert len(items) == 2

    shot = _grab(view, "role_node_two_hexagons")
    assert shot.exists()
