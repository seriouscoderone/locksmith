# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.side_panel module

The slide-in details panel that appears on the right edge of the
ecosystem graph view when a node is selected. Per design §5.6/§5.7.

Two modes of content:

- Schema mode (`show_schema`): renders title + version, description,
  full SAID with copy, large §2 classification glyphs, lists of
  outgoing / incoming chain-of-authority edges (clickable to navigate
  selection within the graph), and an "Open detail page" button.

- Issuer mode (`show_issuer`): renders alias, AID with copy, KEL
  stats (sn, witnesses, transferable), and an "Open contact page"
  button.

The panel is overlay-positioned by its parent (the EcosystemGraphView)
via setGeometry on each resize. Slide animation is a QPropertyAnimation
on `maximumWidth` (180ms ease-out): collapsed = 0, open = 280px.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    Signal,
)
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from keri import help

logger = help.ogler.getLogger(__name__)

from locksmith.acdc import icons
from locksmith.plugins.ecosystem_viewer.widgets import (
    DisclosureTierWidget,
    LifecycleWidget,
    SectionFingerprintWidget,
)
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import LocksmithIconButton


PANEL_WIDTH = 280
PANEL_ANIM_MS = 180


def _truncate(s: str, head: int = 10, tail: int = 6) -> str:
    if len(s) <= head + tail + 1:
        return s
    return f"{s[:head]}…{s[-tail:]}"


class SidePanel(QFrame):
    """Floating overlay panel on the right edge of the graph view."""

    open_schema_detail = Signal(str)         # emits schema SAID
    open_issuer = Signal(str, bool)          # emits (aid, is_self)
    schema_link_clicked = Signal(str)        # emits SAID — caller selects node
    issuer_link_clicked = Signal(str)        # emits AID — caller selects node
    role_link_clicked = Signal(str)          # emits role_name — caller selects node

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("egvSidePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            "QFrame#egvSidePanel {"
            " background-color: white;"
            f" border-left: 1px solid {colors.BORDER};"
            "}"
            "QFrame#egvSidePanel QLabel { background: transparent; }"
        )

        # Animate panel_width (custom property). Setting it adjusts BOTH
        # minimum and maximum width to the same value, which is the only
        # reliable way to grow/shrink a widget that isn't in a layout —
        # animating maximumWidth alone leaves min at 0, so geometry's
        # width is clamped to 0 even when max grows.
        self._width_anim = QPropertyAnimation(self, b"panel_width", self)
        self._width_anim.setDuration(PANEL_ANIM_MS)
        self._width_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._panel_width = 0
        self.setFixedWidth(0)
        self.hide()

        # Inner content widget: fixed width = PANEL_WIDTH. As the outer
        # panel's animated fixedWidth grows from 0 to PANEL_WIDTH, this
        # child *slides* in from negative-x rather than resizing — so
        # word-wrapped labels never reflow during the animation.
        self._inner = QFrame(self)
        self._inner.setFixedWidth(PANEL_WIDTH)
        self._inner.setStyleSheet("background: transparent;")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(16, 14, 16, 14)
        self._inner_layout.setSpacing(10)
        self._inner_layout.addStretch()
        # Initial inner-x: fully off-screen to the left; revealed as panel grows.
        self._inner.move(-PANEL_WIDTH, 0)

    def _get_panel_width(self) -> int:
        return self._panel_width

    def _set_panel_width(self, value: int) -> None:
        self._panel_width = value
        self.setFixedWidth(value)
        # Slide the inner content: its right edge stays glued to the
        # outer panel's right edge as the outer grows.
        self._inner.move(value - PANEL_WIDTH, 0)
        # Re-anchor the panel to the right edge of the parent.
        parent = self.parentWidget()
        if parent is not None:
            self.move(parent.width() - value, self.y())

    panel_width = Property(int, _get_panel_width, _set_panel_width)

    def reposition(self, parent_width: int, parent_height: int,
                   bottom_inset: int = 36) -> None:
        """Called by the parent on resize / first show — sets the panel's
        Y and height to fill the canvas above the bottom toolbar. X is
        managed by the panel itself via _set_panel_width."""
        panel_h = max(0, parent_height - bottom_inset)
        self.setFixedHeight(panel_h)
        self._inner.setFixedHeight(panel_h)
        self.move(parent_width - self._panel_width, 0)

    # ------------------------------------------------------------------
    # Show / hide
    # ------------------------------------------------------------------

    def open(self) -> None:
        # Force on top of sibling widgets every time — the QGraphicsView
        # next to us in the parent layout will otherwise paint over the
        # panel and the slide-in disappears.
        self.raise_()
        self.show()
        if self._panel_width >= PANEL_WIDTH:
            return
        try:
            self._width_anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._width_anim.stop()
        self._width_anim.setStartValue(self._panel_width)
        self._width_anim.setEndValue(PANEL_WIDTH)
        self._width_anim.start()

    def close(self) -> None:
        self._width_anim.stop()
        self._width_anim.setStartValue(self._panel_width)
        self._width_anim.setEndValue(0)
        try:
            self._width_anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._width_anim.finished.connect(self._on_collapse_finished)
        self._width_anim.start()

    def _on_collapse_finished(self) -> None:
        if self._panel_width == 0:
            self.hide()

    # ------------------------------------------------------------------
    # Schema content
    # ------------------------------------------------------------------

    def show_schema(
        self,
        inspection: Any,
        edges_out: list[tuple[str, str]],   # (dst_said, op)
        edges_in: list[tuple[str, str]],    # (src_said, op)
        schema_titles: dict[str, str],      # said -> title (for link labels)
        permitted_issuers: list[tuple[str, str, bool]] | None = None,
        # ^ list of (aid, alias, is_self) for each permitted issuer
        ecosystem_has_issuers: bool = True,
    ) -> None:
        self._clear_inner()

        # Title + version
        title_lbl = QLabel(inspection.title or "(unnamed schema)")
        title_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {colors.TEXT_DARK};"
        )
        title_lbl.setWordWrap(True)
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, title_lbl)

        if inspection.schema_version:
            ver_lbl = QLabel(f"v{inspection.schema_version}")
            ver_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
            self._inner_layout.insertWidget(self._inner_layout.count() - 1, ver_lbl)

        if inspection.description:
            desc_lbl = QLabel(inspection.description)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_DARK};")
            self._inner_layout.insertWidget(self._inner_layout.count() - 1, desc_lbl)

        # SAID + copy
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1,
            self._build_id_row("SAID", inspection.schema_said),
        )

        # Classification glyph row
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1,
            self._build_classification_row(inspection),
        )

        # Lifecycle glyph cell — registry-backed (revocable) vs one-shot.
        # Same visual register as the classification glyph row; tooltip
        # carries the prose. Per design §3.2 / §4.3.
        revocable = bool(getattr(inspection, "requires_registry", False))
        lifecycle_row = QHBoxLayout()
        lifecycle_row.setContentsMargins(0, 4, 0, 0)
        lifecycle_row.setSpacing(8)
        lifecycle_row.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        glyph = LifecycleWidget(revocable=revocable)
        # Use the default 18px size for chip-scale.
        lifecycle_row.addWidget(glyph)

        lifecycle_text_lbl = QLabel("Revocable" if revocable else "One-shot")
        lifecycle_text_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: "
            f"{'#0D9488' if revocable else colors.TEXT_SECONDARY};"
        )
        lifecycle_row.addWidget(lifecycle_text_lbl)
        lifecycle_row.addStretch()

        lifecycle_w = QWidget()
        lifecycle_w.setLayout(lifecycle_row)
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, lifecycle_w,
        )

        # Outgoing edges
        if edges_out:
            self._inner_layout.insertWidget(
                self._inner_layout.count() - 1,
                self._build_edges_section("Chains to", edges_out, schema_titles),
            )
        # Incoming edges
        if edges_in:
            self._inner_layout.insertWidget(
                self._inner_layout.count() - 1,
                self._build_edges_section("Chained from", edges_in, schema_titles),
            )

        # Permitted issuers section (Stage 9 EGF overlay).
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1,
            self._build_permitted_issuers_section(
                permitted_issuers or [], ecosystem_has_issuers,
            ),
        )

        # Open detail button
        open_btn = QPushButton("Open detail page →")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(
            "QPushButton {"
            f" background: white; border: 1px solid {colors.BORDER};"
            f" border-radius: 6px; padding: 6px 12px;"
            f" font-size: 12px; color: {colors.TEXT_DARK};"
            "}"
            f"QPushButton:hover {{ background: {colors.BACKGROUND_HOVER}; }}"
        )
        captured_said = inspection.schema_said
        open_btn.clicked.connect(lambda: self.open_schema_detail.emit(captured_said))
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, open_btn)

        self.open()

    # ------------------------------------------------------------------
    # Ghost (unresolved schema) content
    # ------------------------------------------------------------------

    def show_ghost(self, said: str, edges_in: list[tuple[str, str]],
                   schema_titles: dict[str, str]) -> None:
        """Render a ghost-node panel for an unresolved schema target."""
        self._clear_inner()

        title_lbl = QLabel("(Unresolved schema)")
        title_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {colors.TEXT_SECONDARY};"
            " font-style: italic;"
        )
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, title_lbl)

        explain_lbl = QLabel(
            "This schema is referenced by edges in your ecosystem but isn't "
            "in your wallet yet. Resolve its OOBI via Credentials → Schemas → Add "
            "to bring it in."
        )
        explain_lbl.setWordWrap(True)
        explain_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_DARK};")
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, explain_lbl)

        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, self._build_id_row("SAID", said)
        )

        if edges_in:
            self._inner_layout.insertWidget(
                self._inner_layout.count() - 1,
                self._build_edges_section("Chained from", edges_in, schema_titles),
            )

        self.open()

    # ------------------------------------------------------------------
    # Issuer content
    # ------------------------------------------------------------------

    def show_issuer(self, aid: str, meta: dict) -> None:
        self._clear_inner()

        alias_lbl = QLabel(meta.get("alias") or "(no alias)")
        alias_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {colors.TEXT_DARK};"
        )
        alias_lbl.setWordWrap(True)
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, alias_lbl)

        kind_lbl = QLabel("Your AID" if meta.get("is_self") else "Remote contact")
        kind_lbl.setStyleSheet(
            f"font-size: 11px; color: "
            f"{colors.PRIMARY if meta.get('is_self') else colors.TEXT_SECONDARY};"
            " font-weight: 600;"
        )
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, kind_lbl)

        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1, self._build_id_row("AID", aid)
        )

        # KEL stats
        kever = meta.get("kever")
        stats: list[str] = []
        if kever is not None:
            stats.append(f"sn {kever.sn}")
            wits = getattr(kever, "wits", None) or []
            if wits:
                noun = "witness" if len(wits) == 1 else "witnesses"
                stats.append(f"{len(wits)} {noun}")
            stats.append("transferable" if kever.transferable else "non-transferable")
        else:
            stats.append("KEL not yet resolved")

        stats_lbl = QLabel(" · ".join(stats))
        stats_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
        stats_lbl.setWordWrap(True)
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, stats_lbl)

        # Open contacts/identifiers button
        is_self = bool(meta.get("is_self"))
        open_btn = QPushButton(
            "Open in Identifiers →" if is_self else "Open in Contacts →"
        )
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(
            "QPushButton {"
            f" background: white; border: 1px solid {colors.BORDER};"
            f" border-radius: 6px; padding: 6px 12px;"
            f" font-size: 12px; color: {colors.TEXT_DARK};"
            "}"
            f"QPushButton:hover {{ background: {colors.BACKGROUND_HOVER}; }}"
        )
        open_btn.clicked.connect(
            lambda _c=False, a=aid, s=is_self: self.open_issuer.emit(a, s)
        )
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, open_btn)

        self.open()

    # ------------------------------------------------------------------
    # Role content (Stage 14 T6)
    # ------------------------------------------------------------------

    def show_role(
        self,
        role: Any,
        members: list[str],
        qualification_schema_title: str | None,
        issuer_role_label: str | None,
    ) -> None:
        """Render a RoleNode's detail panel — see Stage 14 T6 spec."""
        self._clear_inner()

        # Header
        header_lbl = QLabel(f"Role: {role.name}")
        header_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 600; color: {colors.TEXT_DARK};"
        )
        header_lbl.setWordWrap(True)
        self._inner_layout.insertWidget(self._inner_layout.count() - 1, header_lbl)

        # Description
        if getattr(role, "description", ""):
            desc_lbl = QLabel(role.description)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_DARK};")
            self._inner_layout.insertWidget(
                self._inner_layout.count() - 1, desc_lbl,
            )

        # Qualification credential — clickable link to the schema node.
        qual_said = getattr(role, "qualification_schema_said", "") or ""
        qual_text = qualification_schema_title or (
            f"{qual_said[:18]}…" if len(qual_said) > 18 else (qual_said or "(none)")
        )
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1,
            self._build_schema_link_row(
                "Qualification credential", qual_text, qual_said,
            ),
        )

        # Trust source: chained role link OR root-issuer list.
        if issuer_role_label is not None:
            self._inner_layout.insertWidget(
                self._inner_layout.count() - 1,
                self._build_role_link_row(
                    "Issuer role", issuer_role_label, role.issuer_role_name,
                ),
            )
        else:
            self._inner_layout.insertWidget(
                self._inner_layout.count() - 1,
                self._build_trust_roots_section(
                    list(role.root_issuer_aids or [])
                ),
            )

        # Resolved members section.
        self._inner_layout.insertWidget(
            self._inner_layout.count() - 1,
            self._build_members_section(list(members)),
        )

        self.open()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _clear_inner(self) -> None:
        # Remove every widget in front of the trailing stretch.
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()

    def _build_id_row(self, label: str, value: str) -> QWidget:
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        label_lbl = QLabel(label)
        label_lbl.setStyleSheet(
            f"font-size: 10px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.04em;"
        )
        layout.addWidget(label_lbl)

        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(4)
        value_lbl = QLabel(_truncate(value, head=12, tail=6))
        value_lbl.setStyleSheet(
            f"font-family: monospace; font-size: 11px; color: {colors.TEXT_DARK};"
        )
        value_lbl.setToolTip(value)
        value_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        inner.addWidget(value_lbl)

        copy_btn = LocksmithIconButton(
            icons.ICON_COPY, tooltip=f"Copy {label} to clipboard", icon_size=14
        )
        copy_btn.setFixedSize(20, 20)
        captured = value
        copy_btn.clicked.connect(
            lambda _c=False, v=captured: QGuiApplication.clipboard().setText(v)
        )
        inner.addWidget(copy_btn)
        inner.addStretch()
        layout.addLayout(inner)

        return row

    def _build_classification_row(self, inspection: Any) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Variant glyph
        var_path = (
            icons.ICON_PRIVACY_PRIVATE if inspection.requires_nonce
            else icons.ICON_PRIVACY_PUBLIC
        )
        var_lbl = QLabel()
        var_lbl.setPixmap(_load_pixmap(var_path, 22))
        var_lbl.setFixedSize(22, 22)
        var_lbl.setToolTip(
            "Private (requires u nonce)"
            if inspection.requires_nonce else "Public credential"
        )
        layout.addWidget(var_lbl)

        # Targeting glyph
        tgt_path = (
            icons.ICON_TARGETING_TARGETED if inspection.requires_targeted
            else icons.ICON_TARGETING_UNTARGETED
        )
        tgt_lbl = QLabel()
        tgt_lbl.setPixmap(_load_pixmap(tgt_path, 22))
        tgt_lbl.setFixedSize(22, 22)
        tgt_lbl.setToolTip(
            "Targeted to a holder"
            if inspection.requires_targeted else "Untargeted attestation"
        )
        layout.addWidget(tgt_lbl)

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
        layout.addWidget(tier_widget)

        # Section fingerprint
        fp_widget = SectionFingerprintWidget(
            has_attribute=sd.declares_attribute,
            has_aggregate=sd.declares_aggregate,
            has_edges=sd.declares_edges,
            has_rules=sd.declares_rules,
        )
        layout.addWidget(fp_widget)

        layout.addStretch()
        return row

    def _build_permitted_issuers_section(
        self,
        permitted: list[tuple[str, str, bool]],
        ecosystem_has_issuers: bool,
    ) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)

        head = QLabel("Permitted issuers")
        head.setStyleSheet(
            f"font-size: 10px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.04em;"
        )
        layout.addWidget(head)

        if not permitted:
            body_text = (
                "Any ecosystem issuer accepted"
                if ecosystem_has_issuers
                else "Add an issuer AID to this ecosystem first"
            )
            body = QLabel(body_text)
            body.setWordWrap(True)
            body.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; font-style: italic;"
            )
            layout.addWidget(body)
            return section

        # Flow chips left-to-right, wrapping naturally via stretch at the end.
        chips_row = QVBoxLayout()
        chips_row.setContentsMargins(0, 0, 0, 0)
        chips_row.setSpacing(3)
        for aid, alias, is_self in permitted:
            chip = self._build_permitted_chip(aid, alias, is_self)
            chips_row.addWidget(chip)
        chips_w = QWidget()
        chips_w.setLayout(chips_row)
        layout.addWidget(chips_w)
        return section

    def _build_permitted_chip(
        self, aid: str, alias: str, is_self: bool,
    ) -> QWidget:
        chip = QFrame()
        chip.setObjectName("egvSidePanelAuthChip")
        chip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setStyleSheet(
            "QFrame#egvSidePanelAuthChip {"
            f" background: {colors.BACKGROUND_SELECTION};"
            " border-radius: 9px; padding: 1px 8px;"
            "}"
            f"QFrame#egvSidePanelAuthChip:hover {{"
            f" background: {colors.BACKGROUND_TABLE_ROW_HOVER}; }}"
            "QFrame#egvSidePanelAuthChip QLabel { background: transparent; }"
        )
        layout = QHBoxLayout(chip)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        text = alias
        if is_self:
            text = f"{alias} ★"
        label = QLabel(text)
        label.setStyleSheet(
            f"font-size: 11px; color: {colors.TEXT_DARK};"
            + (f" font-weight: 600;" if is_self else "")
        )
        label.setToolTip(f"{aid}\n(click to open in {'Identifiers' if is_self else 'Contacts'})")
        layout.addWidget(label)

        chip.mousePressEvent = (
            lambda _ev, a=aid, s=is_self: self.open_issuer.emit(a, s)
        )
        return chip

    def _build_edges_section(
        self,
        title: str,
        edges: list[tuple[str, str]],   # (other_said, op)
        schema_titles: dict[str, str],
    ) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(2)

        head = QLabel(title)
        head.setStyleSheet(
            f"font-size: 10px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.04em;"
        )
        layout.addWidget(head)

        for other_said, op in edges:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            # Operator badge
            op_lbl = QLabel(op)
            op_lbl.setStyleSheet(
                f"font-size: 10px; color: {colors.TEXT_DARK};"
                f" background: {colors.BACKGROUND_NEUTRAL}; border-radius: 4px;"
                " padding: 1px 4px; font-weight: 600;"
            )
            row.addWidget(op_lbl)

            label_text = schema_titles.get(other_said) or "(unresolved)"
            link_lbl = QLabel(
                f'<a href="#nav" style="color:{colors.BLUE_BORDER};text-decoration:none;">'
                f'{label_text}</a>'
            )
            link_lbl.setStyleSheet("font-size: 12px;")
            link_lbl.setToolTip(other_said)
            link_lbl.setOpenExternalLinks(False)
            captured = other_said
            link_lbl.linkActivated.connect(
                lambda _l, s=captured: self.schema_link_clicked.emit(s)
            )
            row.addWidget(link_lbl, 1)

            row_w = QWidget()
            row_w.setLayout(row)
            layout.addWidget(row_w)

        return section


    def _build_schema_link_row(
        self, label: str, link_text: str, schema_said: str,
    ) -> QWidget:
        """Labelled row with a clickable link that emits schema_link_clicked."""
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        label_lbl = QLabel(f"{label}:")
        label_lbl.setStyleSheet(
            f"font-size: 10px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.04em;"
        )
        layout.addWidget(label_lbl)

        link_lbl = QLabel(
            f'<a href="#nav" style="color:{colors.BLUE_BORDER};text-decoration:none;">'
            f'{link_text}</a>'
        )
        link_lbl.setStyleSheet("font-size: 12px;")
        link_lbl.setToolTip(schema_said or link_text)
        link_lbl.setOpenExternalLinks(False)
        link_lbl.setWordWrap(True)
        captured = schema_said
        link_lbl.linkActivated.connect(
            lambda _l, s=captured: self.schema_link_clicked.emit(s)
        )
        layout.addWidget(link_lbl)
        return row

    def _build_role_link_row(
        self, label: str, link_text: str, role_name: str,
    ) -> QWidget:
        """Labelled row with a clickable link that emits role_link_clicked."""
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        label_lbl = QLabel(f"{label}:")
        label_lbl.setStyleSheet(
            f"font-size: 10px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.04em;"
        )
        layout.addWidget(label_lbl)

        link_lbl = QLabel(
            f'<a href="#nav" style="color:{colors.BLUE_BORDER};text-decoration:none;">'
            f'{link_text}</a>'
        )
        link_lbl.setStyleSheet("font-size: 12px;")
        link_lbl.setToolTip(role_name or link_text)
        link_lbl.setOpenExternalLinks(False)
        link_lbl.setWordWrap(True)
        captured = role_name
        link_lbl.linkActivated.connect(
            lambda _l, n=captured: self.role_link_clicked.emit(n)
        )
        layout.addWidget(link_lbl)
        return row

    def _build_trust_roots_section(self, aids: list[str]) -> QWidget:
        """Labelled list of clickable trust-root AIDs (root role only)."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(2)

        head = QLabel("Trust roots:")
        head.setStyleSheet(
            f"font-size: 10px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.04em;"
        )
        layout.addWidget(head)

        if not aids:
            empty = QLabel("No trust roots configured.")
            empty.setWordWrap(True)
            empty.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; font-style: italic;"
            )
            layout.addWidget(empty)
            return section

        for aid in aids:
            text = _truncate(aid, head=12, tail=6)
            link_lbl = QLabel(
                f'<a href="#nav" style="color:{colors.BLUE_BORDER};text-decoration:none;'
                f'font-family:monospace;">{text}</a>'
            )
            link_lbl.setStyleSheet("font-size: 11px;")
            link_lbl.setToolTip(aid)
            link_lbl.setOpenExternalLinks(False)
            captured = aid
            link_lbl.linkActivated.connect(
                lambda _l, a=captured: self.issuer_link_clicked.emit(a)
            )
            layout.addWidget(link_lbl)

        return section

    def _build_members_section(self, members: list[str]) -> QWidget:
        """Labelled scrollable list of resolved-member AIDs."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(2)

        head = QLabel(f"Resolved members ({len(members)}):")
        head.setStyleSheet(
            f"font-size: 10px; color: {colors.TEXT_SECONDARY};"
            " font-weight: 600; letter-spacing: 0.04em;"
        )
        layout.addWidget(head)

        if not members:
            empty = QLabel("No qualifying credentials found in this wallet.")
            empty.setWordWrap(True)
            empty.setStyleSheet(
                f"font-size: 11px; color: {colors.TEXT_SECONDARY}; font-style: italic;"
            )
            layout.addWidget(empty)
            return section

        # Wrap the AID rows in a scroll area so long lists don't push the
        # rest of the panel off-screen.
        list_inner = QWidget()
        list_inner_layout = QVBoxLayout(list_inner)
        list_inner_layout.setContentsMargins(0, 0, 0, 0)
        list_inner_layout.setSpacing(2)
        for aid in members:
            text = _truncate(aid, head=12, tail=6)
            link_lbl = QLabel(
                f'<a href="#nav" style="color:{colors.BLUE_BORDER};text-decoration:none;'
                f'font-family:monospace;">{text}</a>'
            )
            link_lbl.setStyleSheet("font-size: 11px;")
            link_lbl.setToolTip(aid)
            link_lbl.setOpenExternalLinks(False)
            captured = aid
            link_lbl.linkActivated.connect(
                lambda _l, a=captured: self.issuer_link_clicked.emit(a)
            )
            list_inner_layout.addWidget(link_lbl)
        list_inner_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll.setWidget(list_inner)
        scroll.setMaximumHeight(180)
        layout.addWidget(scroll)
        return section


def _load_pixmap(path: str, size: int) -> QPixmap:
    px = QPixmap(path)
    if px.isNull():
        return px
    return px.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
