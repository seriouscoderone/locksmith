# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.widgets module

Domain-aware painted Qt widgets that communicate ACDC primitives visually.

Both widgets are entirely runtime-painted (no SVG) because their visual
state encodes inspector data — they react to property changes rather
than being static assets.

- DisclosureTierWidget: §2.3 disclosure tier ziggurat
- SectionFingerprintWidget: §2.4 section-presence dot fingerprint

Citations to the design doc are by section number; see
docs/superpowers/designs/2026-05-06-ecosystem-viewer-redesign.md.
"""
from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from locksmith.ui import colors


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Color for the third (split) selective-disclosure bar segments — same as the
# other filled bars; we just split the geometry, not the color.
_TIER_BAR_COLOR = colors.TEXT_DARK

# Aggregate (selective disclosure) section dot color — teal, per design §2.4.
_AGGREGATE_TEAL = "#0D9488"


# ---------------------------------------------------------------------------
# DisclosureTierWidget
# ---------------------------------------------------------------------------

DisclosureTier = Literal["metadata", "partial", "selective", "full"]


class DisclosureTierWidget(QWidget):
    """4-bar ziggurat glyph indicating a schema's disclosure tier (§2.3).

    Set `tier` to one of "metadata", "partial", "selective", "full" to
    update which bars are filled. The 'selective' tier renders bar 3 as
    three small split segments (evoking individually-disclosable
    attributes); other tiers render bars as solid filled rectangles or
    hairline outlines.

    All bars use colors.TEXT_DARK (no color encoding here — color is
    reserved for variant per the design language).
    """

    # Geometry constants. Total widget bounds are approximately 22×14.
    _BAR_HEIGHT = 2
    _BAR_GAP = 1
    _BAR_WIDTHS = (8, 11, 14, 17)  # top to bottom — ziggurat
    _TOTAL_WIDTH = max(_BAR_WIDTHS)
    _TOTAL_HEIGHT = (_BAR_HEIGHT * 4) + (_BAR_GAP * 3)

    def __init__(self, tier: DisclosureTier = "metadata", parent: QWidget | None = None):
        super().__init__(parent)
        self._tier: DisclosureTier = tier
        self.setFixedSize(self._TOTAL_WIDTH + 4, self._TOTAL_HEIGHT + 4)  # padding
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    @property
    def tier(self) -> DisclosureTier:
        return self._tier

    @tier.setter
    def tier(self, value: DisclosureTier) -> None:
        if value not in ("metadata", "partial", "selective", "full"):
            raise ValueError(f"Invalid tier: {value!r}")
        if self._tier != value:
            self._tier = value
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._TOTAL_WIDTH + 4, self._TOTAL_HEIGHT + 4)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(_TIER_BAR_COLOR)

        # How many bars are "active" (i.e., not just hairline outlines).
        # tier "metadata" = 1, "partial" = 2, "selective" = 3, "full" = 4
        filled_count = {"metadata": 1, "partial": 2, "selective": 3, "full": 4}[self._tier]

        # Bars are stacked top-to-bottom, centered horizontally.
        center_x = self.width() / 2
        # Vertical layout starts with 2px top padding
        y = 2
        for i, bar_width in enumerate(self._BAR_WIDTHS):
            bar_rect = QRectF(
                center_x - bar_width / 2,
                y,
                bar_width,
                self._BAR_HEIGHT,
            )

            is_filled = (i + 1) <= filled_count
            is_split_bar = self._tier == "selective" and (i + 1) == 3

            if not is_filled:
                # Hairline outline: 1px stroke, no fill.
                painter.setPen(QPen(color, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(bar_rect)
            elif is_split_bar:
                # Three small segments centered in the bar with small gaps.
                # Use a 1px gap between segments; segment_width = (bar_width - 2*gap) / 3.
                gap = 1.0
                seg_width = (bar_width - 2 * gap) / 3.0
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                for s in range(3):
                    seg_rect = QRectF(
                        bar_rect.left() + s * (seg_width + gap),
                        bar_rect.top(),
                        seg_width,
                        bar_rect.height(),
                    )
                    painter.drawRect(seg_rect)
            else:
                # Solid filled bar.
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRect(bar_rect)

            y += self._BAR_HEIGHT + self._BAR_GAP

        painter.end()


# ---------------------------------------------------------------------------
# SectionFingerprintWidget
# ---------------------------------------------------------------------------


class SectionFingerprintWidget(QWidget):
    """2x2 dot grid indicating which ACDC sections a schema declares (§2.4).

    Stable per-position assignment lets users learn to read the fingerprint
    at a glance:
        top-left = attribute, top-right = aggregate
        bottom-left = edges,  bottom-right = rules

    Each filled dot uses a section-specific color (attribute neutral,
    aggregate teal, edges PRIMARY orange, rules WARNING_YELLOW). Empty
    slots render as 1px hairline outline rings.
    """

    _SIZE = 24
    _DOT_DIAMETER = 7

    def __init__(
        self,
        has_attribute: bool = False,
        has_aggregate: bool = False,
        has_edges: bool = False,
        has_rules: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._has_attribute = has_attribute
        self._has_aggregate = has_aggregate
        self._has_edges = has_edges
        self._has_rules = has_rules
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    @property
    def has_attribute(self) -> bool:
        return self._has_attribute

    @has_attribute.setter
    def has_attribute(self, value: bool) -> None:
        if self._has_attribute != value:
            self._has_attribute = value
            self.update()

    @property
    def has_aggregate(self) -> bool:
        return self._has_aggregate

    @has_aggregate.setter
    def has_aggregate(self, value: bool) -> None:
        if self._has_aggregate != value:
            self._has_aggregate = value
            self.update()

    @property
    def has_edges(self) -> bool:
        return self._has_edges

    @has_edges.setter
    def has_edges(self, value: bool) -> None:
        if self._has_edges != value:
            self._has_edges = value
            self.update()

    @property
    def has_rules(self) -> bool:
        return self._has_rules

    @has_rules.setter
    def has_rules(self, value: bool) -> None:
        if self._has_rules != value:
            self._has_rules = value
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._SIZE, self._SIZE)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 2×2 grid: each cell is half the widget. Centers of the four dots
        # are at (¼, ¼), (¾, ¼), (¼, ¾), (¾, ¾).
        size = self._SIZE
        d = self._DOT_DIAMETER
        positions = [
            # (cx, cy, color, is_filled)
            (size / 4,     size / 4,     QColor(colors.TEXT_DARK),       self._has_attribute),
            (3 * size / 4, size / 4,     QColor(_AGGREGATE_TEAL),        self._has_aggregate),
            (size / 4,     3 * size / 4, QColor(colors.PRIMARY),         self._has_edges),
            (3 * size / 4, 3 * size / 4, QColor(colors.WARNING_YELLOW),  self._has_rules),
        ]

        empty_color = QColor(colors.TEXT_SECONDARY)

        for cx, cy, color, filled in positions:
            rect = QRectF(cx - d / 2, cy - d / 2, d, d)
            if filled:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(rect)
            else:
                painter.setPen(QPen(empty_color, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(rect)

        painter.end()


# ---------------------------------------------------------------------------
# LifecycleWidget
# ---------------------------------------------------------------------------


class LifecycleWidget(QWidget):
    """Painted glyph for the registry-backed (revocable) vs registryless
    (one-shot) lifecycle axis (design 2026-05-07-acdc-parties-lifecycle §3.2).

    - revocable=True : clockface — circle with a single hand at 12 o'clock.
      Reads as "state can change after issuance." Color teal #0D9488 to
      match the aggregate-section dot from redesign §2.4.
    - revocable=False: open-bottom circle (270° arc) with a center dot.
      Reads as "anchored point, no clockwork." Color TEXT_SECONDARY.

    Painted (not SVG) for the same reason as DisclosureTierWidget — the
    state encodes inspector data and re-tinting at runtime is cleaner via
    QPainter than via QPixmap.SourceIn.
    """

    _SIZE = 18  # default pixel size; callers can resize

    _REVOCABLE_COLOR = "#0D9488"

    def __init__(self, revocable: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._revocable = revocable
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setToolTip(
            "Revocable via TEL" if revocable else "One-shot — no revocation"
        )

    @property
    def revocable(self) -> bool:
        return self._revocable

    @revocable.setter
    def revocable(self, value: bool) -> None:
        if self._revocable != value:
            self._revocable = value
            self.setToolTip(
                "Revocable via TEL" if value else "One-shot — no revocation"
            )
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._SIZE, self._SIZE)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        size = min(self.width(), self.height())
        margin = 2
        rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)

        if self._revocable:
            color = QColor(self._REVOCABLE_COLOR)
            # Clockface ring
            painter.setPen(QPen(color, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)
            # Single hand at 12 (vertical from center to top)
            cx = rect.center().x()
            cy = rect.center().y()
            painter.setPen(QPen(color, 1.5))
            painter.drawLine(QPointF(cx, cy), QPointF(cx, rect.top() + 2))
            # Center pivot dot
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(cx - 1, cy - 1, 2, 2))
        else:
            color = QColor(colors.TEXT_SECONDARY)
            # Open-bottom 270° arc — start at -45° (bottom-right) sweeping
            # 270° counter-clockwise to -45°+270° = 225° (bottom-left).
            # QPainter uses 1/16-degree units and CCW positive.
            painter.setPen(QPen(color, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Start angle -45° = -45*16, span 270° = 270*16
            painter.drawArc(rect, -45 * 16, 270 * 16)
            # Center anchor dot
            cx = rect.center().x()
            cy = rect.center().y()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(cx - 1.5, cy - 1.5, 3, 3))

        painter.end()
