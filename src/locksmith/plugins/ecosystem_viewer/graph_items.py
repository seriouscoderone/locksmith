# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.graph_items module

Custom QGraphicsItem subclasses for the chain-of-authority mini-graph
(Phase B3b) and the full ecosystem graph view (Phase D).

- SchemaNode: a notched-rectangle node representing one ACDC schema.
  Draws title, on-node glyph trio (variant, disclosure tier, section
  fingerprint), and a SAID glyph in the corner. Targeting determines
  the right-edge notch shape.

- EdgeLine: a directed line between two SchemaNodes with operator-
  specific visual treatment (solid for I2I/NI2I, dashed for DI2I, Ø
  overlay at midpoint for NOT). Draws an arrowhead at the target end.

Both items are designed for reuse: the same items power the depth-1
mini-graph on the schema detail page and (eventually) the full
hierarchical graph on the ecosystem detail page.
"""
from __future__ import annotations

import math
from typing import Any, Literal

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from locksmith.ui import colors


# ---------------------------------------------------------------------------
# Geometry constants
# ---------------------------------------------------------------------------

NODE_WIDTH = 140
NODE_HEIGHT = 80
NODE_RADIUS = 8           # rounded corners
NOTCH_DEPTH = 10          # how far the targeted-notch indents
NOTCH_HEIGHT = 24         # vertical extent of the notch on the right edge


# ---------------------------------------------------------------------------
# SchemaNode
# ---------------------------------------------------------------------------


class SchemaNode(QGraphicsObject):
    """A schema node: notched rectangle with on-node glyphs.

    Inherits from QGraphicsObject (not QGraphicsItem) so we can emit
    Qt signals for click/double-click. The notch on the right edge
    indicates a targeted ACDC; flat right edge indicates untargeted.

    Visual states (mutually exclusive): idle (default), hovered,
    selected. Selection persists across hover.

    Ghost mode: when set, the node renders as a dashed outline with no
    fill and a "?" glyph instead of full content — used for schemas
    referenced by an edge but not yet resolved into the wallet.
    """

    from PySide6.QtCore import Signal
    clicked = Signal(str)         # emits SAID
    double_clicked = Signal(str)  # emits SAID

    def __init__(
        self,
        *,
        said: str,
        title: str,
        version: str | None = None,
        is_targeted: bool = True,
        is_private: bool = False,
        disclosure_tier: Literal["metadata", "partial", "selective", "full"] = "metadata",
        has_attribute: bool = False,
        has_aggregate: bool = False,
        has_edges: bool = False,
        has_rules: bool = False,
        ghost: bool = False,
        parent: QGraphicsItem | None = None,
    ):
        super().__init__(parent)
        self.said = said
        self.title = title
        self.version = version
        self.is_targeted = is_targeted
        self.is_private = is_private
        self.disclosure_tier = disclosure_tier
        self.has_attribute = has_attribute
        self.has_aggregate = has_aggregate
        self.has_edges = has_edges
        self.has_rules = has_rules
        self.ghost = ghost

        self._hovered = False
        self._selected = False

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Tooltip
        title_line = title or "(unnamed schema)"
        if version:
            title_line += f" v{version}"
        said_short = said[:18] + "…" if len(said) > 20 else said
        self.setToolTip(f"{title_line}\n{said_short}")

    # --- Bounding & shape -------------------------------------------------

    def boundingRect(self) -> QRectF:
        # A small margin for hover/selected stroke + drop shadow
        margin = 2
        right_extra = NOTCH_DEPTH if self.is_targeted else 0
        return QRectF(
            -margin,
            -margin,
            NODE_WIDTH + right_extra + 2 * margin,
            NODE_HEIGHT + 2 * margin,
        )

    def shape(self) -> QPainterPath:
        return self._build_outline_path()

    def _build_outline_path(self) -> QPainterPath:
        """Build the rounded-rect outline with optional right-edge notch."""
        path = QPainterPath()
        if not self.is_targeted:
            path.addRoundedRect(QRectF(0, 0, NODE_WIDTH, NODE_HEIGHT), NODE_RADIUS, NODE_RADIUS)
            return path

        # Targeted: rounded rect with a notch (triangular cutout) on right.
        # Build manually so we can include the notch geometry.
        r = NODE_RADIUS
        w, h = NODE_WIDTH, NODE_HEIGHT
        notch_y0 = (h - NOTCH_HEIGHT) / 2
        notch_y1 = notch_y0 + NOTCH_HEIGHT
        notch_apex_x = w + NOTCH_DEPTH

        # Start at top-left + radius, go clockwise.
        path.moveTo(r, 0)
        path.lineTo(w - r, 0)
        path.quadTo(w, 0, w, r)              # top-right corner
        path.lineTo(w, notch_y0)              # down to notch start
        path.lineTo(notch_apex_x, h / 2)      # out to notch apex
        path.lineTo(w, notch_y1)              # back in to notch end
        path.lineTo(w, h - r)                 # down to bottom-right corner
        path.quadTo(w, h, w - r, h)           # bottom-right
        path.lineTo(r, h)                     # bottom edge
        path.quadTo(0, h, 0, h - r)           # bottom-left corner
        path.lineTo(0, r)                     # left edge
        path.quadTo(0, 0, r, 0)               # top-left corner
        path.closeSubpath()
        return path

    # --- Painting ---------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        outline = self._build_outline_path()

        if self.ghost:
            # Ghost: dashed outline, no fill
            pen = QPen(QColor(colors.TEXT_SECONDARY), 1.5)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(outline)

            # "?" glyph centered
            painter.setPen(QPen(QColor(colors.TEXT_SECONDARY), 1))
            font = QFont("Helvetica", 18, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, NODE_WIDTH, NODE_HEIGHT), Qt.AlignmentFlag.AlignCenter, "?")

            # SAID truncation below the glyph
            said_font = QFont()
            said_font.setPointSize(7)
            painter.setFont(said_font)
            said_short = self.said[:16] + "…" if len(self.said) > 18 else self.said
            painter.drawText(
                QRectF(4, NODE_HEIGHT - 18, NODE_WIDTH - 8, 14),
                Qt.AlignmentFlag.AlignCenter,
                said_short,
            )
            return

        # Fill + stroke based on state
        if self._selected:
            stroke_color = QColor(colors.PRIMARY)
            stroke_width = 2.5
            fill_color = QColor("#FFF5EB")  # faint orange-tinted background
        elif self._hovered:
            stroke_color = QColor(colors.PRIMARY)
            stroke_width = 1.5
            fill_color = QColor("white")
        else:
            stroke_color = QColor("#E0E3EA")
            stroke_width = 1.5
            fill_color = QColor("white")

        painter.setPen(QPen(stroke_color, stroke_width))
        painter.setBrush(QBrush(fill_color))
        painter.drawPath(outline)

        # Title (top-left, ellipsized)
        painter.setPen(QPen(QColor(colors.TEXT_DARK)))
        title_font = QFont()
        title_font.setPointSize(9)
        title_font.setBold(True)
        painter.setFont(title_font)

        # Reserve a 16x16 area top-right for the SAID glyph
        title_rect = QRectF(8, 8, NODE_WIDTH - 32, 16)
        title_text = self.title or "(unnamed)"
        if self.version:
            title_text += f"  v{self.version}"
        fm = QFontMetrics(title_font)
        elided = fm.elidedText(title_text, Qt.TextElideMode.ElideRight, int(title_rect.width()))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # SAID glyph (top-right, 16x16 — three concentric arcs, simplified)
        self._paint_said_glyph(painter, NODE_WIDTH - 20, 8)

        # Variant glyph (left of middle row)
        self._paint_variant_glyph(painter, 8, 30)

        # Disclosure tier glyph (right of variant)
        self._paint_disclosure_tier(painter, 30, 33)

        # Section fingerprint (bottom-right, 24x24)
        self._paint_section_fingerprint(painter, NODE_WIDTH - 30, NODE_HEIGHT - 30)

    def _paint_said_glyph(self, painter: QPainter, x: float, y: float) -> None:
        """Tiny three-arc rangefinder glyph, 16x16 at (x, y)."""
        painter.save()
        painter.translate(x, y)
        pen = QPen(QColor(colors.TEXT_SECONDARY), 1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Three arcs nested; drawn as upper-half circles (180°)
        for r in (6, 4, 2):
            arc_rect = QRectF(8 - r, 8 - r, 2 * r, 2 * r)
            painter.drawArc(arc_rect, 0 * 16, 180 * 16)  # 0° to 180°
        painter.restore()

    def _paint_variant_glyph(self, painter: QPainter, x: float, y: float) -> None:
        """14x14 variant indicator: open circle (public) or hatched circle (private)."""
        painter.save()
        painter.translate(x, y)
        size = 14
        pen = QPen(QColor(colors.TEXT_DARK), 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        circle = QRectF(0, 0, size, size)
        painter.drawEllipse(circle)
        if self.is_private:
            clip_path = QPainterPath()
            clip_path.addEllipse(circle)
            painter.setClipPath(clip_path)
            hatch_pen = QPen(QColor(colors.TEXT_DARK), 1)
            painter.setPen(hatch_pen)
            for offset in range(-size, size + 4, 3):
                painter.drawLine(QPointF(offset, 0), QPointF(offset + size, size))
        painter.restore()

    def _paint_disclosure_tier(self, painter: QPainter, x: float, y: float) -> None:
        """Small disclosure-tier ziggurat at (x, y); 4 bars, ~10x10 area."""
        painter.save()
        painter.translate(x, y)
        bar_h = 1.5
        gap = 1
        widths = (5, 7, 9, 11)
        filled_count = {"metadata": 1, "partial": 2, "selective": 3, "full": 4}.get(
            self.disclosure_tier, 1
        )
        color = QColor(colors.TEXT_DARK)
        cy = 0.0
        for i, bw in enumerate(widths):
            cx = (max(widths) - bw) / 2
            rect = QRectF(cx, cy, bw, bar_h)
            if (i + 1) <= filled_count:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRect(rect)
            else:
                painter.setPen(QPen(color, 0.6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
            cy += bar_h + gap
        painter.restore()

    def _paint_section_fingerprint(self, painter: QPainter, x: float, y: float) -> None:
        """24x24 region with 2x2 dot grid showing section presence."""
        painter.save()
        painter.translate(x, y)
        d = 5
        positions = [
            (6, 6, QColor(colors.TEXT_DARK), self.has_attribute),
            (18, 6, QColor("#0D9488"), self.has_aggregate),
            (6, 18, QColor(colors.PRIMARY), self.has_edges),
            (18, 18, QColor(colors.WARNING_YELLOW), self.has_rules),
        ]
        empty = QColor(colors.TEXT_SECONDARY)
        for cx, cy, color, filled in positions:
            rect = QRectF(cx - d / 2, cy - d / 2, d, d)
            if filled:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(rect)
            else:
                painter.setPen(QPen(empty, 0.8))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(rect)
        painter.restore()

    # --- Interaction ------------------------------------------------------

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.said)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.said)
        super().mouseDoubleClickEvent(event)

    def set_selected(self, selected: bool) -> None:
        if self._selected != selected:
            self._selected = selected
            self.update()

    # --- Anchors for edge connections -------------------------------------

    def left_anchor(self) -> QPointF:
        """Scene coordinates of the node's left-edge connection point."""
        return self.mapToScene(QPointF(0, NODE_HEIGHT / 2))

    def right_anchor(self) -> QPointF:
        """Scene coordinates of the node's right-edge connection point.

        For targeted nodes, this is the notch apex; for untargeted, the
        flat right edge.
        """
        x = NODE_WIDTH + NOTCH_DEPTH if self.is_targeted else NODE_WIDTH
        return self.mapToScene(QPointF(x, NODE_HEIGHT / 2))


# ---------------------------------------------------------------------------
# EdgeLine
# ---------------------------------------------------------------------------

EdgeOperatorVisual = Literal["I2I", "NI2I", "DI2I", "NOT"]


class EdgeLine(QGraphicsPathItem):
    """A directed edge between two SchemaNodes with operator-aware drawing.

    - I2I (default), NI2I: solid line, solid arrowhead
    - DI2I: dashed line, solid arrowhead (delegated chain)
    - NOT: solid line + Ø overlay at midpoint (inversion)

    The edge connects source.right_anchor() -> target.left_anchor() with
    a straight line (mini-graph) or a slight curve when multiple edges
    would overlap (Phase D).

    Owners are responsible for repositioning the edge when nodes move
    (call refresh()).
    """

    ARROW_LENGTH = 10
    ARROW_WIDTH = 6

    def __init__(
        self,
        source: SchemaNode,
        target: SchemaNode,
        operator: EdgeOperatorVisual = "I2I",
        label: str | None = None,
        parent: QGraphicsItem | None = None,
    ):
        super().__init__(parent)
        self.source = source
        self.target = target
        self.operator = operator
        self.label = label
        self.setZValue(-1)  # behind nodes
        self.setAcceptHoverEvents(True)
        self.refresh()

    def refresh(self) -> None:
        """Recompute the path from source/target anchors."""
        path = QPainterPath()
        p1 = self.source.right_anchor()
        p2 = self.target.left_anchor()
        path.moveTo(p1)
        path.lineTo(p2)
        self.setPath(path)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(colors.TEXT_SECONDARY)

        # Line style by operator
        pen = QPen(color, 1.5)
        if self.operator == "DI2I":
            pen.setStyle(Qt.PenStyle.DashLine)
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

        # Arrowhead at target end
        p1 = self.source.right_anchor()
        p2 = self.target.left_anchor()
        self._draw_arrowhead(painter, p1, p2, color)

        # NOT operator: Ø symbol at line midpoint
        if self.operator == "NOT":
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            self._draw_not_overlay(painter, mid)

        # Operator label pill at midpoint
        if self.label:
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            self._draw_label_pill(painter, mid, self.label)

    def _draw_arrowhead(self, painter: QPainter, p1: QPointF, p2: QPointF, color: QColor) -> None:
        """Draw a solid filled arrowhead at p2, oriented along p1->p2."""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        # Perpendicular
        px, py = -uy, ux
        tip = p2
        base_x = p2.x() - ux * self.ARROW_LENGTH
        base_y = p2.y() - uy * self.ARROW_LENGTH
        left = QPointF(base_x + px * (self.ARROW_WIDTH / 2), base_y + py * (self.ARROW_WIDTH / 2))
        right = QPointF(base_x - px * (self.ARROW_WIDTH / 2), base_y - py * (self.ARROW_WIDTH / 2))
        polygon = QPolygonF([tip, left, right])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(polygon)

    def _draw_not_overlay(self, painter: QPainter, mid: QPointF) -> None:
        """Draw Ø symbol at mid: a small circle with a diagonal slash."""
        r = 7
        painter.save()
        painter.setPen(QPen(QColor(colors.DANGER), 1.5))
        painter.setBrush(QBrush(QColor("white")))
        painter.drawEllipse(QRectF(mid.x() - r, mid.y() - r, 2 * r, 2 * r))
        painter.drawLine(
            QPointF(mid.x() - r * 0.6, mid.y() + r * 0.6),
            QPointF(mid.x() + r * 0.6, mid.y() - r * 0.6),
        )
        painter.restore()

    def _draw_label_pill(self, painter: QPainter, mid: QPointF, text: str) -> None:
        painter.save()
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(text)
        text_h = fm.height()
        pad_x = 4
        pad_y = 1
        rect = QRectF(
            mid.x() - text_w / 2 - pad_x,
            mid.y() - text_h / 2 - pad_y - 10,  # offset up so label doesn't sit on line
            text_w + 2 * pad_x,
            text_h + 2 * pad_y,
        )
        painter.setPen(QPen(QColor(colors.TEXT_SECONDARY), 0.5))
        painter.setBrush(QBrush(QColor("white")))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QPen(QColor(colors.TEXT_DARK)))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
