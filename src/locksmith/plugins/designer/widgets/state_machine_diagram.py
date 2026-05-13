# -*- encoding: utf-8 -*-
"""StateMachineDiagram: TEL lifecycle visualization for exported credentials.

Color-coded by tel_primitive:
  issue=orange, update=teal, revoke=pink.
Pure QGraphicsScene; no external SVG.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Union

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


_TRANSITION_COLOR: dict[str, str] = {
    "issue": "#D97757",
    "update": "#0ABFB0",
    "revoke": "#E94B7B",
}


@dataclass
class StateTransition:
    from_state: Union[str, list[str]]
    to_state: str
    tel_primitive: str


class StateMachineDiagram(QGraphicsView):
    NODE_W = 110
    NODE_H = 44
    H_GAP = 70
    BASE_Y = 60

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setStyleSheet(
            "background:#fff;border:1px solid #e0e3ea;border-radius:6px;"
        )
        self._state_count = 0

    @property
    def state_count(self) -> int:
        return self._state_count

    def _expand(self, transitions: list[StateTransition]) -> list[tuple[str, str, str]]:
        out: list[tuple[str, str, str]] = []
        for t in transitions:
            srcs = t.from_state if isinstance(t.from_state, list) else [t.from_state]
            for src in srcs:
                out.append((src, t.to_state, t.tel_primitive))
        return out

    def render(self, transitions: list[StateTransition]) -> None:
        self._scene.clear()
        expanded = self._expand(transitions)
        seen: list[str] = []
        for src, dst, _ in expanded:
            for s in (src, dst):
                if s and s not in seen:
                    seen.append(s)
        self._state_count = len(seen)

        positions: dict[str, QPointF] = {}
        for i, s in enumerate(seen):
            x = 20 + i * (self.NODE_W + self.H_GAP)
            y = self.BASE_Y
            positions[s] = QPointF(x, y)
            self._scene.addRect(
                QRectF(x, y, self.NODE_W, self.NODE_H),
                QPen(QColor("#1A1C20"), 1.5),
                QBrush(QColor("#fff")),
            )
            label_font = QFont()
            label_font.setPointSize(10)
            label_font.setBold(True)
            text = self._scene.addText(s, label_font)
            text.setDefaultTextColor(QColor("#1A1C20"))
            text.setPos(x + 8, y + 10)

        for src, dst, prim in expanded:
            if src not in positions or dst not in positions:
                continue
            start = positions[src]
            end = positions[dst]
            color = QColor(_TRANSITION_COLOR.get(prim, "#666"))
            pen = QPen(color, 2)
            if src == dst:
                # Self-loop: small arc above the node
                self._scene.addEllipse(
                    QRectF(start.x() + self.NODE_W / 2 - 18, start.y() - 28, 36, 28),
                    pen,
                    QBrush(Qt.NoBrush),
                )
                continue
            x1 = start.x() + self.NODE_W
            y1 = start.y() + self.NODE_H / 2
            x2 = end.x()
            y2 = end.y() + self.NODE_H / 2
            self._scene.addLine(x1, y1, x2, y2, pen)
            angle = math.atan2(y2 - y1, x2 - x1)
            ahx = x2 - 10 * math.cos(angle - math.pi / 6)
            ahy = y2 - 10 * math.sin(angle - math.pi / 6)
            ahx2 = x2 - 10 * math.cos(angle + math.pi / 6)
            ahy2 = y2 - 10 * math.sin(angle + math.pi / 6)
            poly = QPolygonF(
                [QPointF(x2, y2), QPointF(ahx, ahy), QPointF(ahx2, ahy2)]
            )
            self._scene.addPolygon(poly, pen, QBrush(color))
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2 - 14
            label_font = QFont()
            label_font.setPointSize(8)
            label_font.setBold(True)
            text = self._scene.addText(prim, label_font)
            text.setDefaultTextColor(color)
            text.setPos(mid_x - 20, mid_y)
