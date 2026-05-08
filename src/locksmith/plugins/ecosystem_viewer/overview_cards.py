# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.overview_cards module

Card and tile widgets used by EcosystemViewerPage's redesigned overview
(design doc §3). Each widget is responsible for one row/tile of the
overview's three regions:

- EcosystemTile      — a 240×180 hero-ribbon ecosystem tile (§3.2).
- CreateEcosystemTile — the matching "+ Define a new ecosystem" tile.
- ConstellationPreview — painted thumbnail block inside an ecosystem tile.
- SchemaCard         — compact full-width schema row card (§3.2).
- IssuerSigilCircle  — painted 48px sigil-in-circle avatar.
- IssuerCard         — compact issuer row card (§3.2).
- EmptyStateCard     — dashed-outline empty-state placeholder (§3.3).

The overview page builds these from inspector data and EcosystemBaser
records. Painting the variant/targeting/disclosure/section glyphs reuses
icons.py SVGs (24×24 source) and the painted widgets in widgets.py.

Citations are by section number from
docs/superpowers/designs/2026-05-06-ecosystem-viewer-redesign.md.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from locksmith.acdc import icons
from locksmith.plugins.ecosystem_viewer.widgets import (
    DisclosureTierWidget,
    SectionFingerprintWidget,
)
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton


# ---------------------------------------------------------------------------
# Geometry constants
# ---------------------------------------------------------------------------

ECOSYSTEM_TILE_W = 240
ECOSYSTEM_TILE_H = 180
SCHEMA_CARD_H = 88
ISSUER_CARD_H = 76
ISSUER_AVATAR_DIAMETER = 48


def _truncate_said(said: str, head: int = 8, tail: int = 4) -> str:
    """Mid-truncate a SAID/AID for compact display: 'ABCDEFGH…WXYZ'."""
    if len(said) <= head + tail + 1:
        return said
    return f"{said[:head]}…{said[-tail:]}"


def _load_tinted_pixmap(path: str, size: int, color: str | None) -> QPixmap:
    """Load an SVG resource at `size`×`size`, optionally tinting with SourceIn."""
    px = QPixmap(path)
    if px.isNull():
        return px
    px = px.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if color is None:
        return px
    out = QPixmap(px.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    p.drawPixmap(0, 0, px)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor(color))
    p.end()
    return out


# ---------------------------------------------------------------------------
# Constellation preview (mini schema thumbnails)
# ---------------------------------------------------------------------------


class ConstellationPreview(QWidget):
    """Painted preview of up to 6 schema thumbnails for an ecosystem tile.

    Per design §3.2 each thumbnail is a 28px rounded notched rectangle (no
    inner detail). The full hierarchical Sugiyama layout is Phase D work;
    for v1 we render a left-to-right horizontal flow, capped at 6 with
    a "+N" badge floating over the last visible thumbnail when overflow.
    """

    THUMB_W = 28
    THUMB_H = 18
    THUMB_RADIUS = 4
    THUMB_NOTCH = 4
    THUMB_GAP = 4
    MAX_VISIBLE = 6

    def __init__(self, schema_count: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._schema_count = max(0, int(schema_count))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumHeight(self.THUMB_H + 6)

    def sizeHint(self) -> QSize:
        return QSize(
            (self.THUMB_W + self.THUMB_GAP) * self.MAX_VISIBLE,
            self.THUMB_H + 6,
        )

    def set_schema_count(self, n: int) -> None:
        if self._schema_count != n:
            self._schema_count = max(0, int(n))
            self.update()

    def paintEvent(self, event):
        if self._schema_count <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        visible = min(self._schema_count, self.MAX_VISIBLE)
        overflow = self._schema_count - visible

        thumb_color = QColor(colors.TEXT_DARK)
        thumb_color.setAlphaF(0.65)

        x = 0
        y = (self.height() - self.THUMB_H) // 2
        last_rect = None
        for _ in range(visible):
            path = QPainterPath()
            # Rounded-rect with a simple right-edge notch (always present —
            # placeholder; per-schema targeting requires Phase D layout).
            r = self.THUMB_RADIUS
            w, h = self.THUMB_W, self.THUMB_H
            n = self.THUMB_NOTCH
            path.moveTo(x + r, y)
            path.lineTo(x + w - r, y)
            path.quadTo(x + w, y, x + w, y + r)
            path.lineTo(x + w, y + (h - n) / 2)
            path.lineTo(x + w + n / 2, y + h / 2)
            path.lineTo(x + w, y + (h + n) / 2)
            path.lineTo(x + w, y + h - r)
            path.quadTo(x + w, y + h, x + w - r, y + h)
            path.lineTo(x + r, y + h)
            path.quadTo(x, y + h, x, y + h - r)
            path.lineTo(x, y + r)
            path.quadTo(x, y, x + r, y)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(thumb_color)
            p.drawPath(path)
            last_rect = QRectF(x, y, w + n / 2, h)
            x += self.THUMB_W + self.THUMB_NOTCH + self.THUMB_GAP

        if overflow > 0 and last_rect is not None:
            badge_text = f"+{overflow}"
            font = QFont()
            font.setPointSizeF(8)
            font.setBold(True)
            p.setFont(font)
            metrics = p.fontMetrics()
            tw = metrics.horizontalAdvance(badge_text) + 8
            th = metrics.height() + 2
            bx = last_rect.right() - tw / 2
            by = last_rect.top() - th / 2
            badge_rect = QRectF(bx, by, tw, th)
            p.setBrush(QColor(colors.PRIMARY))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(badge_rect, th / 2, th / 2)
            p.setPen(QPen(QColor("white")))
            p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        p.end()


# ---------------------------------------------------------------------------
# Ecosystem tile
# ---------------------------------------------------------------------------


class EcosystemTile(QFrame):
    """240×180 ecosystem tile per design §3.2 — diamond glyph, name, counts,
    constellation preview. Click navigates to the ecosystem detail page."""

    clicked = Signal(str)  # emits ecosystem name

    def __init__(self, eco: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._name = eco.name
        self.setObjectName("ecoTile")
        self.setFixedSize(ECOSYSTEM_TILE_W, ECOSYSTEM_TILE_H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QFrame#ecoTile { background-color: white; border: 1px solid #E0E3EA; border-radius: 8px; }"
            f"QFrame#ecoTile:hover {{ border: 2px solid {colors.BLUE_BORDER}; }}"
            "QFrame#ecoTile QLabel { background: transparent; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # Header row: diamond glyph + name
        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(8)
        head_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        diamond_lbl = QLabel()
        diamond_lbl.setPixmap(_load_tinted_pixmap(icons.ICON_ECOSYSTEM, 16, colors.PRIMARY))
        diamond_lbl.setFixedSize(16, 16)
        head_row.addWidget(diamond_lbl)

        name_lbl = QLabel(eco.name)
        name_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {colors.TEXT_PRIMARY};"
        )
        head_row.addWidget(name_lbl, 1)
        layout.addLayout(head_row)

        # Counts
        n_schemas = len(eco.schema_saids)
        n_aids = len(eco.issuer_aids)
        counts_lbl = QLabel(
            f"{n_schemas} schema{'s' if n_schemas != 1 else ''} · "
            f"{n_aids} issuer{'s' if n_aids != 1 else ''}"
        )
        counts_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
        layout.addWidget(counts_lbl)

        # Description (optional, single-line truncated)
        if eco.description:
            desc_lbl = QLabel(eco.description)
            desc_lbl.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_SECONDARY};")
            desc_lbl.setWordWrap(False)
            metrics = desc_lbl.fontMetrics()
            elided = metrics.elidedText(
                eco.description, Qt.TextElideMode.ElideRight, ECOSYSTEM_TILE_W - 28
            )
            desc_lbl.setText(elided)
            layout.addWidget(desc_lbl)

        layout.addStretch()

        # Constellation preview
        constellation = ConstellationPreview(schema_count=n_schemas)
        constellation.setFixedHeight(28)
        layout.addWidget(constellation)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._name)
            event.accept()
        else:
            super().mousePressEvent(event)


class CreateEcosystemTile(QFrame):
    """240×180 'create new ecosystem' tile per design §3.2."""

    clicked = Signal()

    def __init__(self, expanded: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ecoCreateTile")
        # When expanded (no other ecosystems exist), tile is wider so the
        # explainer text reads as a hero CTA per §3.3.
        if expanded:
            self.setFixedSize(ECOSYSTEM_TILE_W * 2 + 12, ECOSYSTEM_TILE_H)
        else:
            self.setFixedSize(ECOSYSTEM_TILE_W, ECOSYSTEM_TILE_H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QFrame#ecoCreateTile {"
            f" background-color: {colors.BACKGROUND_CONTENT};"
            f" border: 2px dashed {colors.BORDER}; border-radius: 8px;"
            "}"
            "QFrame#ecoCreateTile:hover {"
            f" border: 2px dashed {colors.PRIMARY}; background-color: white;"
            "}"
            "QFrame#ecoCreateTile QLabel { background: transparent; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        plus_lbl = QLabel()
        plus_lbl.setPixmap(_load_tinted_pixmap(icons.ICON_ADD_PLUS, 28, colors.PRIMARY))
        plus_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus_lbl.setFixedHeight(28)
        layout.addWidget(plus_lbl)

        title_lbl = QLabel("Define a new ecosystem")
        title_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {colors.TEXT_PRIMARY};"
        )
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        if expanded:
            explain_lbl = QLabel(
                "Group schemas and issuers that work together — "
                "your private trust map."
            )
            explain_lbl.setStyleSheet(
                f"font-size: 12px; color: {colors.TEXT_SECONDARY};"
            )
            explain_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            explain_lbl.setWordWrap(True)
            layout.addWidget(explain_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Schema card (compact)
# ---------------------------------------------------------------------------


class SchemaCard(QFrame):
    """Compact full-width schema card per design §3.2.

    Layout:
      ┌────────────────────────────────────────────────────────┐
      │ [variant]  Title v1                  [▥] EOP_…vK [⎘]   │
      │            credentialType                              │
      │            [targeting] [disclosure] [fingerprint]      │
      └────────────────────────────────────────────────────────┘
    """

    clicked = Signal(str)  # emits schema SAID

    def __init__(self, inspection: Any, parent: QWidget | None = None):
        super().__init__(parent)
        self._said = inspection.schema_said
        self.setObjectName("evSchemaCard")
        self.setMinimumHeight(SCHEMA_CARD_H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QFrame#evSchemaCard {"
            " background-color: white; border: 1px solid #E0E3EA; border-radius: 6px;"
            "}"
            "QFrame#evSchemaCard:hover {"
            f" background-color: {colors.BACKGROUND_TABLE_ROW_HOVER};"
            "}"
            "QFrame#evSchemaCard QLabel { background: transparent; }"
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(12)
        outer.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Variant glyph (24px)
        variant_path = (
            icons.ICON_PRIVACY_PRIVATE if inspection.requires_nonce
            else icons.ICON_PRIVACY_PUBLIC
        )
        variant_lbl = QLabel()
        variant_lbl.setPixmap(_load_tinted_pixmap(variant_path, 24, None))
        variant_lbl.setFixedSize(24, 24)
        variant_lbl.setToolTip(
            "Private (requires u nonce)"
            if inspection.requires_nonce else "Public credential"
        )
        outer.addWidget(variant_lbl, 0, Qt.AlignmentFlag.AlignTop)

        # Center text block
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(2)

        # Title row: title + version
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_lbl = QLabel(inspection.title or "(untitled schema)")
        title_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {colors.TEXT_DARK};"
        )
        title_row.addWidget(title_lbl)
        if inspection.schema_version:
            ver_lbl = QLabel(f"v{inspection.schema_version}")
            ver_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
            title_row.addWidget(ver_lbl)
        title_row.addStretch()
        center.addLayout(title_row)

        # Subtitle (credentialType if known)
        cred_type = getattr(inspection, "credential_type", None) or ""
        if cred_type:
            sub_lbl = QLabel(cred_type)
            sub_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
            center.addWidget(sub_lbl)

        # Glyph row: targeting + disclosure tier + section fingerprint
        glyph_row = QHBoxLayout()
        glyph_row.setContentsMargins(0, 2, 0, 0)
        glyph_row.setSpacing(10)
        glyph_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Targeting badge
        targeting_path = (
            icons.ICON_TARGETING_TARGETED if inspection.requires_targeted
            else icons.ICON_TARGETING_UNTARGETED
        )
        targeting_lbl = QLabel()
        targeting_lbl.setPixmap(_load_tinted_pixmap(targeting_path, 18, colors.TEXT_DARK))
        targeting_lbl.setFixedSize(18, 18)
        targeting_lbl.setToolTip(
            "Targeted to a holder (a.i required)"
            if inspection.requires_targeted else "Untargeted attestation"
        )
        glyph_row.addWidget(targeting_lbl)

        # Disclosure tier
        sd = inspection.declared_sections
        if sd.declares_aggregate:
            tier = "selective"
        elif sd.declares_attribute and sd.declares_edges and sd.declares_rules:
            tier = "full"
        elif sd.declares_attribute:
            tier = "partial"
        else:
            tier = "metadata"
        tier_widget = DisclosureTierWidget(tier=tier)
        tier_widget.setToolTip(f"{tier.capitalize()} disclosure")
        glyph_row.addWidget(tier_widget)

        # Section fingerprint
        fp_widget = SectionFingerprintWidget(
            has_attribute=sd.declares_attribute,
            has_aggregate=sd.declares_aggregate,
            has_edges=sd.declares_edges,
            has_rules=sd.declares_rules,
        )
        declared_parts = []
        if sd.declares_attribute:
            declared_parts.append("attribute")
        if sd.declares_aggregate:
            declared_parts.append("aggregate")
        if sd.declares_edges:
            declared_parts.append("edges")
        if sd.declares_rules:
            declared_parts.append("rules")
        fp_widget.setToolTip(
            "Sections: " + (", ".join(declared_parts) if declared_parts else "(none)")
        )
        glyph_row.addWidget(fp_widget)

        glyph_row.addStretch()
        center.addLayout(glyph_row)

        outer.addLayout(center, 1)

        # Right block: SAID fingerprint icon + truncated SAID + copy
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(4)
        right.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        fp_icon = QLabel()
        fp_icon.setPixmap(_load_tinted_pixmap(icons.ICON_SAID_FINGERPRINT, 14, colors.TEXT_SECONDARY))
        fp_icon.setFixedSize(14, 14)
        right.addWidget(fp_icon)

        said_lbl = QLabel(_truncate_said(self._said, head=8, tail=4))
        said_lbl.setStyleSheet(
            f"font-family: monospace; font-size: 11px; color: {colors.TEXT_SECONDARY};"
        )
        said_lbl.setToolTip(self._said)
        right.addWidget(said_lbl)

        copy_btn = LocksmithIconButton(
            icons.ICON_COPY, tooltip="Copy SAID to clipboard", icon_size=14
        )
        copy_btn.setFixedSize(20, 20)
        _said_capture = self._said
        copy_btn.clicked.connect(
            lambda _c=False, s=_said_capture: QGuiApplication.clipboard().setText(s)
        )
        # Stop the click from bubbling to the card.
        copy_btn.installEventFilter(self)
        self._copy_btn = copy_btn
        right.addWidget(copy_btn)

        outer.addLayout(right, 0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._said)
            event.accept()
        else:
            super().mousePressEvent(event)

    def eventFilter(self, watched, event):
        # Prevent copy button clicks from also navigating to schema detail.
        if watched is self._copy_btn and event.type() in (
            event.Type.MouseButtonPress, event.Type.MouseButtonRelease
        ):
            event.accept()
            # Let the button still see the event by returning False after accepting?
            # Actually, returning True swallows it from the button too. We want
            # the button to receive the click, just not the parent. Qt delivers
            # to children before parents anyway — so the parent's mousePressEvent
            # only fires if the child didn't accept it. QToolButton accepts its
            # own clicks, so we don't actually need this filter. Keep as a
            # belt-and-braces no-op (return False).
            return False
        return super().eventFilter(watched, event)


# ---------------------------------------------------------------------------
# Issuer card (compact)
# ---------------------------------------------------------------------------


class IssuerSigilCircle(QWidget):
    """Painted 48px circular avatar containing the §2.8 issuer sigil glyph.

    Optional `role` decoration paints small directional ribbons on the
    circle to indicate the AID's role in a specific credential context:
      - "from": ribbon on bottom-right pointing right (issuer / outflow)
      - "to":   ribbon on bottom-left pointing left (issuee / inflow)
      - "both": both ribbons (self-issued — single AID is both parties)
      - None:   no decoration (used in directories where role is undefined)
    Per design 2026-05-07-acdc-parties-lifecycle.md §3.1.
    """

    DIAMETER = ISSUER_AVATAR_DIAMETER

    def __init__(
        self,
        is_self: bool = False,
        role: str | None = None,  # None | "from" | "to" | "both"
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._is_self = is_self
        self._role = role
        # Slightly wider hit area when ribbons attach so they're not clipped.
        extra = 8 if role else 0
        self.setFixedSize(self.DIAMETER + extra, self.DIAMETER)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        sigil_color = colors.PRIMARY if is_self else colors.TEXT_DARK
        self._sigil_px = _load_tinted_pixmap(
            icons.ICON_ISSUER_SIGIL, self.DIAMETER - 16, sigil_color
        )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Background ring
        ring_color = QColor(colors.PRIMARY) if self._is_self else QColor(colors.BORDER)
        p.setPen(QPen(ring_color, 1.5))
        p.setBrush(QColor(colors.BACKGROUND_CONTENT))
        # Center the circle when ribbons add horizontal padding.
        circle_x = (self.width() - self.DIAMETER) / 2
        p.drawEllipse(QRectF(circle_x + 1, 1, self.DIAMETER - 2, self.DIAMETER - 2))
        # Sigil centered in circle
        if not self._sigil_px.isNull():
            sx = circle_x + (self.DIAMETER - self._sigil_px.width()) / 2
            sy = (self.DIAMETER - self._sigil_px.height()) / 2
            p.drawPixmap(QPointF(sx, sy), self._sigil_px)

        # Role ribbons (small triangles attached to the bottom of the circle)
        if self._role in ("from", "both"):
            self._draw_ribbon(p, side="from", circle_x=circle_x, color=ring_color)
        if self._role in ("to", "both"):
            self._draw_ribbon(p, side="to", circle_x=circle_x, color=ring_color)

        p.end()

    def _draw_ribbon(self, p: QPainter, *, side: str, circle_x: float, color: QColor) -> None:
        """Paint a 6×8 directional triangle ribbon at the bottom of the circle.

        side="from" → right-pointing triangle on bottom-right (outflow).
        side="to"   → left-pointing triangle on bottom-left (inflow).
        """
        from PySide6.QtGui import QPolygonF
        d = self.DIAMETER
        # Anchor near the bottom of the circle.
        anchor_y = d - 6
        if side == "from":
            # Triangle just outside the right edge of the circle, pointing right.
            base_x = circle_x + d - 2
            points = [
                QPointF(base_x, anchor_y),         # base top
                QPointF(base_x, anchor_y + 8),     # base bottom
                QPointF(base_x + 6, anchor_y + 4), # tip pointing right
            ]
        else:  # "to"
            base_x = circle_x + 2
            points = [
                QPointF(base_x, anchor_y),         # base top
                QPointF(base_x, anchor_y + 8),     # base bottom
                QPointF(base_x - 6, anchor_y + 4), # tip pointing left
            ]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF(points))


class IssuerCard(QFrame):
    """Compact issuer-AID card per design §3.2."""

    clicked = Signal(str)  # emits AID

    def __init__(
        self,
        contact: dict[str, Any],
        kever: Any | None,
        is_self: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._aid = contact.get("id", "")
        self.setObjectName("evIssuerCard")
        self.setMinimumHeight(ISSUER_CARD_H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QFrame#evIssuerCard {"
            " background-color: white; border: 1px solid #E0E3EA; border-radius: 38px;"
            " padding-right: 6px;"
            "}"
            "QFrame#evIssuerCard:hover {"
            f" background-color: {colors.BACKGROUND_TABLE_ROW_HOVER};"
            "}"
            "QFrame#evIssuerCard QLabel { background: transparent; }"
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 14, 8)
        outer.setSpacing(12)
        outer.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        sigil = IssuerSigilCircle(is_self=is_self)
        outer.addWidget(sigil, 0)

        text_block = QVBoxLayout()
        text_block.setContentsMargins(0, 0, 0, 0)
        text_block.setSpacing(2)

        alias = contact.get("alias") or "(no alias)"
        alias_lbl = QLabel(alias)
        alias_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {colors.TEXT_DARK};"
        )
        text_block.addWidget(alias_lbl)

        aid_lbl = QLabel(_truncate_said(self._aid, head=10, tail=6))
        aid_lbl.setStyleSheet(
            f"font-family: monospace; font-size: 11px; color: {colors.TEXT_SECONDARY};"
        )
        aid_lbl.setToolTip(self._aid)
        text_block.addWidget(aid_lbl)

        # Stats line: "sn N · M witnesses · transferable"
        stats: list[str] = []
        if kever is not None:
            stats.append(f"sn {kever.sn}")
            wits = getattr(kever, "wits", None) or []
            if wits:
                noun = "witness" if len(wits) == 1 else "witnesses"
                stats.append(f"{len(wits)} {noun}")
            stats.append("transferable" if kever.transferable else "witness-shaped")
        else:
            stats.append("KEL not yet resolved")

        stats_lbl = QLabel(" · ".join(stats))
        stats_lbl.setStyleSheet(f"font-size: 11px; color: {colors.TEXT_SECONDARY};")
        text_block.addWidget(stats_lbl)

        outer.addLayout(text_block, 1)

        # Trailing chevron — clickability cue (no-op v1 per §8.1)
        chevron_lbl = QLabel()
        chevron_lbl.setPixmap(_load_tinted_pixmap(
            ":/assets/material-icons/chevron_right.svg", 16, colors.TEXT_SECONDARY
        ))
        chevron_lbl.setFixedSize(16, 16)
        outer.addWidget(chevron_lbl, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._aid)
            event.accept()
        else:
            super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Empty-state card (dashed outline)
# ---------------------------------------------------------------------------


class EmptyStateCard(QFrame):
    """Dashed-outline empty-state placeholder per design §3.3."""

    def __init__(self, message: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("evEmptyCard")
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#evEmptyCard {"
            f" background-color: transparent; border: 2px dashed {colors.BORDER};"
            " border-radius: 8px;"
            "}"
            "QFrame#evEmptyCard QLabel { background: transparent; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_lbl.setStyleSheet(
            f"font-size: 13px; color: {colors.TEXT_SECONDARY}; font-style: italic;"
        )
        layout.addWidget(msg_lbl)
