# -*- encoding: utf-8 -*-
"""SwimlaneDiagram: self-vs-counterparty workflow visualization.

v2: step numbers, branch diamonds, time-bound footnotes, legend,
internal-step dashed style. Pure QGraphicsScene — no external SVG.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


_ACTOR_COLOR: dict[str, str] = {
    "self":         "#D97757",
    "counterparty": "#4A90E2",
    "internal":     "#888888",
}


@dataclass
class SwimlaneStep:
    step_id: str
    label: str
    actor: str
    subtitle: str = ""
    branches: list[dict] | None = None
    time_bound: str | None = None
    is_internal: bool = False


class SwimlaneDiagram(QGraphicsView):
    LANE_HEIGHT = 110
    STEP_WIDTH = 170
    STEP_HEIGHT = 60
    STEP_GAP = 50
    LEFT_MARGIN = 130

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setStyleSheet("background:#fff;border:0;")
        self._step_count = 0
        self._step_numbers: dict[str, str] = {}
        self._internal_ids: list[str] = []
        self._time_bounds: dict[str, str] = {}

    @property
    def step_count(self) -> int:
        return self._step_count

    def step_number_map(self) -> dict[str, str]:
        return dict(self._step_numbers)

    def internal_step_ids(self) -> list[str]:
        return list(self._internal_ids)

    def time_bound_map(self) -> dict[str, str]:
        return dict(self._time_bounds)

    def render(self, *, lanes: list[str], steps: list[SwimlaneStep]) -> None:
        self._scene.clear()
        self._step_count = len(steps)
        self._step_numbers = {}
        self._internal_ids = [s.step_id for s in steps if s.is_internal]
        self._time_bounds = {
            s.step_id: s.time_bound for s in steps if s.time_bound
        }
        self._assign_step_numbers(steps)

        total_width = max(
            900,
            self.LEFT_MARGIN + len(steps) * (self.STEP_WIDTH + self.STEP_GAP),
        )
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        small_font = QFont()
        small_font.setPointSize(8)

        for i, lane in enumerate(lanes):
            y = i * self.LANE_HEIGHT
            bg = QColor("#fafbfc") if i % 2 == 0 else QColor("#fff")
            self._scene.addRect(
                QRectF(0, y, total_width, self.LANE_HEIGHT),
                QPen(QColor("#e0e3ea")), QBrush(bg),
            )
            label_text = self._scene.addText(lane, title_font)
            label_text.setDefaultTextColor(QColor("#666"))
            label_text.setPos(8, y + 8)

        lane_index = {lane: i for i, lane in enumerate(lanes)}

        positions: dict[str, tuple[float, float]] = {}
        for j, step in enumerate(steps):
            x = self.LEFT_MARGIN + j * (self.STEP_WIDTH + self.STEP_GAP)
            row = lane_index.get(step.actor, 0)
            y = row * self.LANE_HEIGHT + 22
            positions[step.step_id] = (x, y)

            if step.is_internal:
                color = QColor(_ACTOR_COLOR["internal"])
                pen = QPen(color, 1.5, Qt.DashLine)
                fill = QColor("#fafbfc")
            else:
                color = QColor(_ACTOR_COLOR.get(step.actor, "#888"))
                pen = QPen(color, 2)
                fill = QColor(color.red(), color.green(), color.blue(), 38)
            self._scene.addRect(
                QRectF(x, y, self.STEP_WIDTH, self.STEP_HEIGHT),
                pen, QBrush(fill),
            )

            num = self._step_numbers.get(step.step_id, "")
            label_text = f"{num}. {step.label}" if num else step.label
            t = self._scene.addText(label_text, title_font)
            t.setDefaultTextColor(QColor("#1A1C20"))
            t.setPos(x + 8, y + 6)

            if step.subtitle:
                sub = self._scene.addText(step.subtitle, small_font)
                sub.setDefaultTextColor(QColor("#666"))
                sub.setPos(x + 8, y + 28)

            if step.time_bound:
                tb = self._scene.addText(f"⏱ {step.time_bound}", small_font)
                tb.setDefaultTextColor(QColor("#888"))
                tb.setPos(x + 4, y + self.STEP_HEIGHT + 4)

            if step.branches:
                self._draw_branch_diamond(step, x, y)

        for j in range(1, len(steps)):
            prev = steps[j - 1]
            cur = steps[j]
            if prev.branches:
                continue
            self._draw_arrow(positions[prev.step_id], positions[cur.step_id])

        self._draw_legend(total_width, len(lanes))

    def _assign_step_numbers(self, steps: list[SwimlaneStep]) -> None:
        counter = 0
        i = 0
        while i < len(steps):
            counter += 1
            s = steps[i]
            self._step_numbers[s.step_id] = str(counter)
            if s.branches:
                letters = "abcdefghij"
                outs = [b.get("next_step") for b in s.branches]
                j = i + 1
                k = 0
                while j < len(steps) and steps[j].step_id in outs and k < len(letters):
                    self._step_numbers[steps[j].step_id] = (
                        f"{counter + 1}{letters[k]}"
                    )
                    j += 1
                    k += 1
                if k > 0:
                    counter += 1
                i = j
            else:
                i += 1

    def _draw_branch_diamond(
        self, step: SwimlaneStep, sx: float, sy: float,
    ) -> None:
        cx = sx + self.STEP_WIDTH + self.STEP_GAP / 2
        cy = sy + self.STEP_HEIGHT / 2
        size = 18
        poly = QPolygonF([
            QPointF(cx, cy - size),
            QPointF(cx + size, cy),
            QPointF(cx, cy + size),
            QPointF(cx - size, cy),
        ])
        self._scene.addPolygon(
            poly,
            QPen(QColor("#A36AE6"), 1.5),
            QBrush(QColor("#f3edfb")),
        )
        small_font = QFont()
        small_font.setPointSize(7)
        small_font.setBold(True)
        labels: list[str] = []
        for b in step.branches or []:
            if b.get("rule_ref"):
                labels.append(b["rule_ref"])
        if labels:
            t = self._scene.addText(labels[0], small_font)
            t.setDefaultTextColor(QColor("#A36AE6"))
            t.setPos(cx - 40, cy - size - 14)

    def _draw_arrow(
        self, start: tuple[float, float], end: tuple[float, float],
    ) -> None:
        x1 = start[0] + self.STEP_WIDTH
        y1 = start[1] + self.STEP_HEIGHT / 2
        x2 = end[0]
        y2 = end[1] + self.STEP_HEIGHT / 2
        pen = QPen(QColor("#888"), 1)
        self._scene.addLine(x1, y1, x2, y2, pen)
        angle = math.atan2(y2 - y1, x2 - x1)
        ahx = x2 - 8 * math.cos(angle - math.pi / 6)
        ahy = y2 - 8 * math.sin(angle - math.pi / 6)
        ahx2 = x2 - 8 * math.cos(angle + math.pi / 6)
        ahy2 = y2 - 8 * math.sin(angle + math.pi / 6)
        poly = QPolygonF(
            [QPointF(x2, y2), QPointF(ahx, ahy), QPointF(ahx2, ahy2)]
        )
        self._scene.addPolygon(poly, pen, QBrush(QColor("#888")))

    def _draw_legend(self, total_width: float, n_lanes: int) -> None:
        y = n_lanes * self.LANE_HEIGHT + 12
        small_font = QFont()
        small_font.setPointSize(8)
        items = [
            ("self command", _ACTOR_COLOR["self"], False),
            ("counterparty / inbound", _ACTOR_COLOR["counterparty"], False),
            ("internal step", _ACTOR_COLOR["internal"], True),
            ("branch", "#A36AE6", False),
        ]
        x = 10
        for label, color_hex, dashed in items:
            color = QColor(color_hex)
            pen = QPen(color, 1.5, Qt.DashLine if dashed else Qt.SolidLine)
            fill = QColor(color.red(), color.green(), color.blue(), 38)
            self._scene.addRect(QRectF(x, y, 14, 12), pen, QBrush(fill))
            t = self._scene.addText(label, small_font)
            t.setDefaultTextColor(QColor("#666"))
            t.setPos(x + 18, y - 2)
            x += 18 + max(110, len(label) * 7)
