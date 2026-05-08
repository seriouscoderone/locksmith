from __future__ import annotations
from pathlib import Path
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from locksmith.plugins.ecosystem_viewer.graph_items import (
    QualificationEdge,
    RoleNode,
    SchemaNode,
)

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
    assert node.boundingRect().width() == RoleNode.NODE_DIAMETER
    items = scene.items()
    assert len(items) == 2

    shot = _grab(view, "role_node_two_hexagons")
    assert shot.exists()


def test_qualification_edge_renders_dashed_with_if_badge(qapp):
    scene = QGraphicsScene()
    view = QGraphicsView(scene)
    view.resize(400, 360)

    schema = SchemaNode(
        said="ESchemaSAIDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        title="DOI Charter",
        version="1.0.0",
    )
    schema.setPos(QPointF(120, 30))
    scene.addItem(schema)

    role = RoleNode(role_name="state-doi", member_count=2)
    role.setPos(QPointF(150, 220))
    scene.addItem(role)

    edge = QualificationEdge(source_schema=schema, target_role=role)
    scene.addItem(edge)
    edge.refresh()

    view.show()
    QTest.qWait(200)
    qapp.processEvents()

    assert edge.schema_said == schema.said
    assert edge.role_name == "state-doi"
    assert not edge.path().isEmpty()

    captured = []
    edge._emitter.remove_requested.connect(lambda said, rname: captured.append((said, rname)))
    edge._emitter.remove_requested.emit(edge.schema_said, edge.role_name)
    assert captured == [(schema.said, "state-doi")]

    shot = _grab(view, "qualification_edge_schema_to_role")
    assert shot.exists()
