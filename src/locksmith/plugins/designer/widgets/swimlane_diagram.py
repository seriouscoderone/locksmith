# -*- encoding: utf-8 -*-
"""SwimlaneDiagram: self-vs-counterparty workflow visualization.

Renders workflow steps in horizontal actor-lanes ("self" and
"counterparty"), with arrows between consecutive steps. Pure
QGraphicsScene — no external SVG.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


_ACTOR_COLOR: dict[str, str] = {
    "self": "#0ABFB0",
    "counterparty": "#D97757",
}


@dataclass
class SwimlaneStep:
    label: str
    actor: str


class SwimlaneDiagram(QGraphicsView):
    LANE_HEIGHT = 80
    STEP_WIDTH = 160
    STEP_HEIGHT = 50
    STEP_GAP = 30
    LEFT_MARGIN = 110

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setStyleSheet(
            "background:#fff;border:1px solid #e0e3ea;border-radius:6px;"
        )
        self._step_count = 0

    @property
    def step_count(self) -> int:
        return self._step_count

    def render(self, *, lanes: list[str], steps: list[SwimlaneStep]) -> None:
        self._scene.clear()
        self._step_count = len(steps)

        label_font = QFont()
        label_font.setPointSize(9)
        label_font.setBold(True)

        # Lane headers + background stripes
        total_width = max(800, self.LEFT_MARGIN + len(steps) * (self.STEP_WIDTH + self.STEP_GAP))
        for i, lane in enumerate(lanes):
            y = i * self.LANE_HEIGHT
            bg = QColor("#fafbfc") if i % 2 == 0 else QColor("#fff")
            self._scene.addRect(
                QRectF(0, y, total_width, self.LANE_HEIGHT),
                QPen(QColor("#e0e3ea")), QBrush(bg),
            )
            text = self._scene.addText(lane, label_font)
            text.setDefaultTextColor(QColor("#666"))
            text.setPos(8, y + 4)

        lane_index = {lane: i for i, lane in enumerate(lanes)}

        for j, step in enumerate(steps):
            x = self.LEFT_MARGIN + j * (self.STEP_WIDTH + self.STEP_GAP)
            y = lane_index.get(step.actor, 0) * self.LANE_HEIGHT + 15
            color = QColor(_ACTOR_COLOR.get(step.actor, "#888"))
            self._scene.addRect(
                QRectF(x, y, self.STEP_WIDTH, self.STEP_HEIGHT),
                QPen(color, 2), QBrush(color.lighter(180)),
            )
            label_font.setBold(False)
            t = self._scene.addText(step.label, label_font)
            t.setDefaultTextColor(QColor("#1A1C20"))
            t.setPos(x + 6, y + 6)
            label_font.setBold(True)

            if j > 0:
                prev_x = self.LEFT_MARGIN + (j - 1) * (self.STEP_WIDTH + self.STEP_GAP) + self.STEP_WIDTH
                prev_y = (lane_index.get(steps[j - 1].actor, 0) * self.LANE_HEIGHT
                          + 15 + self.STEP_HEIGHT // 2)
                cur_y = y + self.STEP_HEIGHT // 2
                self._scene.addLine(prev_x, prev_y, x, cur_y, QPen(QColor("#888"), 1))
