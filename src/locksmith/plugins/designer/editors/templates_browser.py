# -*- encoding: utf-8 -*-
"""TemplatesBrowserPage: entry surface for the Designer.

Lists every template the workspace knows about as cards in a 2-up grid.
Click a card → emit template_open_requested(ref).

## Search & filter model (Phase A)

A single smart query bar parses tokens on space/Enter:
  - ``kind:<value>``  filters by role.kind (e.g. ``kind:government``)
  - ``eco:<value>``   filters by ecosystem tag
  - ``status:invalid`` filters to invalid-only templates
  - Anything else is free-text matched against display name,
    description and role.id/display_name.

Parsed tokens render as removable capsule chips in a "chip rail"
underneath the input. Within a token type chips OR together; across
types they AND, which is the same precedence the old pill UI used.

An amber ``⚠ N invalid`` notification pill appears at the right edge
of the search row *only* when ``invalid_count > 0``. Clicking it
adds ``status:invalid`` to the chip rail and morphs the pill into
``← Showing N invalid · back``. Clicking again (or removing the chip)
exits the invalid-only view.

Cards expose their role-kind and ecosystem tags as clickable affordances:
clicking one adds the matching token to the filter rail without drilling
into the editor (mouse event is accepted at the chip).

Phase B (deferred): ``aid:`` chips with paste auto-detect, ``rel:``
compound chip with hop-popover, and a token-help dropdown.
"""
from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import Qt, QSize, QStringListModel, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QCompleter, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.store import TemplateRef, TemplateStore


# ---------------------------------------------------------------------------
# Pill / chip widgets
# ---------------------------------------------------------------------------

class _PillButton(QLabel):
    """QLabel-based pill button.

    Renders its own rounded-rect background at exactly half-height
    radius. Qt's QSS ``border-radius`` was clipping pills into
    slightly-rounded rectangles instead of true capsules on macOS,
    so background painting is done in Python for guaranteed
    semi-circular end caps.
    """
    clicked = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent=parent)
        self.setCursor(Qt.PointingHandCursor)
        self._pill_color: str | None = None

    def set_pill_color(self, color: str | None) -> None:
        """Background color for the pill. Pass ``None`` to disable
        the rounded background (useful for non-pill labels)."""
        self._pill_color = color
        self.update()

    def paintEvent(self, event):
        if self._pill_color is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor(self._pill_color))
            p.setPen(Qt.NoPen)
            radius = self.height() / 2
            p.drawRoundedRect(self.rect(), radius, radius)
            p.end()
        super().paintEvent(event)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
            ev.accept()
            return
        super().mousePressEvent(ev)


# Token-type → chip-fill color. Status:invalid is amber so it visually
# tracks the notification pill that summons it. `aid:` and `rel:`
# chips use the UX agent's reserved purple for identity-graph tokens
# so they read visually distinct from facet tokens (kind/eco).
_CHIP_COLORS: dict[str, str] = {
    "kind":   "#0ABFB0",
    "eco":    "#0ABFB0",
    "status": "#F59E0B",
    "aid":    "#A36AE6",
    "rel":    "#A36AE6",
}


class _FilterChip(QFrame):
    """Removable capsule chip in the search-bar chip rail.

    Renders ``<token>: <value>`` followed by an ``×`` close button.
    Emits ``removed(token, value)`` on click of ``×``. Paints its own
    rounded background at half-height radius for a true capsule.
    """
    removed = Signal(str, str)

    def __init__(self, token: str, value: str, parent=None):
        super().__init__(parent=parent)
        self._token = token
        self._value = value
        self._color = _CHIP_COLORS.get(token, "#0ABFB0")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 8, 4)
        lay.setSpacing(6)
        label = QLabel(f"{token}: {value}")
        label.setStyleSheet(
            "font-size:11px;font-weight:600;color:#fff;background:transparent;"
        )
        lay.addWidget(label)
        x = _PillButton("×")
        x.setStyleSheet(
            "font-size:14px;font-weight:700;color:#fff;background:transparent;"
            "padding:0px 2px;"
        )
        x.clicked.connect(
            lambda: self.removed.emit(self._token, self._value)
        )
        lay.addWidget(x)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(self._color))
        p.setPen(Qt.NoPen)
        radius = self.height() / 2
        p.drawRoundedRect(self.rect(), radius, radius)
        p.end()
        super().paintEvent(event)


_REL_KINDS: tuple[str, ...] = (
    "any", "issued", "imported", "authored", "referenced", "forked_from",
)


class _RelChip(QFrame):
    """Compound capsule for ``rel:<hop>:<kind>:<aid>`` filters.

    Renders as a natural-language summary
    (``rel: 1-hop EXyz…id00 · issued``) and opens an inline popover
    on left-click of the chip body. The popover exposes a hop
    selector (1/2/3) and a relationship-kind dropdown
    (any / issued / imported / authored / referenced / forked_from).
    The ``×`` removes the chip.

    Value serialization in ``self._chips`` is the compact
    ``<hop>:<kind>:<aid>`` string so the chip round-trips through
    token parsing.

    Phase C scope: the chip + popover surface ships now; the
    graph-relationship index that would actually narrow the card
    grid is deferred. ``_passes_filters`` treats rel chips as
    no-ops with a tooltip hint, so power users can compose queries
    that will light up once the backend lands.
    """
    removed = Signal(str, str)       # ("rel", value)
    changed = Signal(str, str)       # old_value, new_value

    def __init__(self, value: str, parent=None):
        super().__init__(parent=parent)
        self._value = value
        self._hop, self._kind, self._aid = self._parse_value(value)
        self._color = _CHIP_COLORS["rel"]
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(
            "rel filters route through a relationship graph that "
            "isn't online yet — the chip composes the query for when "
            "the index ships. Click to edit hop or kind."
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 8, 4)
        lay.setSpacing(6)
        self._label = QLabel()
        self._label.setStyleSheet(
            "font-size:11px;font-weight:600;color:#fff;"
            "background:transparent;"
        )
        lay.addWidget(self._label)
        x = _PillButton("×")
        x.setStyleSheet(
            "font-size:14px;font-weight:700;color:#fff;"
            "background:transparent;padding:0px 2px;"
        )
        x.clicked.connect(
            lambda: self.removed.emit("rel", self._value)
        )
        lay.addWidget(x)
        self._update_label()

    # -- value parse / format -----------------------------------------

    @staticmethod
    def _parse_value(value: str) -> tuple[int, str, str]:
        """Accept either ``<hop>:<kind>:<aid>`` or ``<hop>:<aid>``.
        Anything else defaults to ``(1, "any", value)``."""
        parts = value.split(":", 2)
        if len(parts) == 3:
            try:
                hop = max(1, min(3, int(parts[0])))
            except ValueError:
                hop = 1
            kind = parts[1] if parts[1] in _REL_KINDS else "any"
            return hop, kind, parts[2]
        if len(parts) == 2:
            try:
                hop = max(1, min(3, int(parts[0])))
                return hop, "any", parts[1]
            except ValueError:
                return 1, "any", value
        return 1, "any", value

    @staticmethod
    def _format_value(hop: int, kind: str, aid: str) -> str:
        return f"{hop}:{kind}:{aid}"

    def _truncate_aid(self) -> str:
        if len(self._aid) >= 8:
            return f"{self._aid[:4]}…{self._aid[-4:]}"
        return self._aid

    def _update_label(self) -> None:
        kind_part = "" if self._kind == "any" else f" · {self._kind}"
        self._label.setText(
            f"rel: {self._hop}-hop {self._truncate_aid()}{kind_part}"
        )

    @property
    def value(self) -> str:
        return self._value

    @property
    def hop(self) -> int:
        return self._hop

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def aid(self) -> str:
        return self._aid

    def set_relationship(self, hop: int, kind: str) -> None:
        """Update hop/kind and emit ``changed(old, new)`` so the
        containing page can rewrite the entry in ``self._chips``.
        Test-friendly hook — the popover calls this when Apply is
        clicked, but unit tests can call it directly."""
        hop = max(1, min(3, int(hop)))
        if kind not in _REL_KINDS:
            kind = "any"
        if hop == self._hop and kind == self._kind:
            return
        old = self._value
        self._hop = hop
        self._kind = kind
        self._value = self._format_value(hop, kind, self._aid)
        self._update_label()
        self.changed.emit(old, self._value)

    # -- painting / interaction --------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(self._color))
        p.setPen(Qt.NoPen)
        radius = self.height() / 2
        p.drawRoundedRect(self.rect(), radius, radius)
        p.end()
        super().paintEvent(event)

    def mousePressEvent(self, ev):
        # Clicks on the × child are accepted there. Anything reaching
        # here is a click on the chip body → open the popover.
        if ev.button() == Qt.LeftButton:
            self._open_popover()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def _open_popover(self) -> None:
        from PySide6.QtWidgets import (
            QComboBox, QMenu, QPushButton, QWidgetAction,
        )
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#fff;border:1px solid #d8dbe1;"
            "padding:6px;}"
        )

        # Hop selector row.
        hop_row = QWidget()
        hop_lay = QHBoxLayout(hop_row)
        hop_lay.setContentsMargins(10, 6, 10, 6)
        hop_lay.setSpacing(8)
        hop_lbl = QLabel("Hops:")
        hop_lbl.setStyleSheet(
            "font-size:11px;color:#444;background:transparent;"
        )
        hop_lay.addWidget(hop_lbl)
        hop_combo = QComboBox()
        hop_combo.addItems(["1", "2", "3"])
        hop_combo.setCurrentText(str(self._hop))
        hop_lay.addWidget(hop_combo)
        hop_act = QWidgetAction(menu)
        hop_act.setDefaultWidget(hop_row)
        menu.addAction(hop_act)

        # Kind selector row.
        kind_row = QWidget()
        kind_lay = QHBoxLayout(kind_row)
        kind_lay.setContentsMargins(10, 0, 10, 6)
        kind_lay.setSpacing(8)
        kind_lbl = QLabel("Kind:")
        kind_lbl.setStyleSheet(
            "font-size:11px;color:#444;background:transparent;"
        )
        kind_lay.addWidget(kind_lbl)
        kind_combo = QComboBox()
        kind_combo.addItems(list(_REL_KINDS))
        kind_combo.setCurrentText(self._kind)
        kind_lay.addWidget(kind_combo)
        kind_act = QWidgetAction(menu)
        kind_act.setDefaultWidget(kind_row)
        menu.addAction(kind_act)

        # Apply button. Clicking apply closes the menu via menu.close().
        apply_row = QWidget()
        apply_lay = QHBoxLayout(apply_row)
        apply_lay.setContentsMargins(10, 0, 10, 2)
        apply_lay.addStretch(1)
        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(
            "QPushButton{background:#0ABFB0;color:#fff;border:0;"
            "border-radius:4px;padding:5px 14px;font-size:11px;"
            "font-weight:600;}"
            "QPushButton:hover{background:#09A89B;}"
        )
        apply_btn.clicked.connect(menu.close)
        apply_lay.addWidget(apply_btn)
        apply_act = QWidgetAction(menu)
        apply_act.setDefaultWidget(apply_row)
        menu.addAction(apply_act)

        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

        # After the menu closes, propagate any changes.
        self.set_relationship(
            int(hop_combo.currentText()), kind_combo.currentText(),
        )


class _ClickableLabel(QLabel):
    """Plain text label that emits ``clicked(text)`` on left-click
    and **accepts** the event so it doesn't bubble up to a containing
    ``_TemplateCard.mousePressEvent`` (which would drill into the
    editor instead of adding a filter).

    Sets ``WA_Hover`` so callers can use a QSS ``:hover`` rule on
    this widget — QLabel does not track mouse hover by default.
    """
    clicked = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent=parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self.text())
            ev.accept()
            return
        super().mousePressEvent(ev)


class _AIDBadgeLabel(QLabel):
    """Card-footer SAID badge. Displays a truncated SAID and emits
    ``clicked_aid(full_said)`` on click so the filter rail gets the
    complete identifier, not the ``ECAR…id00``-style display form.
    Accepts the event so it doesn't bubble up to the card body.
    """
    clicked_aid = Signal(str)

    def __init__(self, full_said: str, display_text: str, parent=None):
        super().__init__(display_text, parent=parent)
        self._full_said = full_said
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(f"Filter by aid:{full_said}")

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked_aid.emit(self._full_said)
            ev.accept()
            return
        super().mousePressEvent(ev)


_ROLE_KIND_COLOR: dict[str, str] = {
    "government":   "#0ABFB0",
    "organization": "#0ABFB0",
    "individual":   "#D97757",
    "system":       "#888888",
    "device":       "#888888",
    "agent":        "#A36AE6",
}


# Recognized token names in the smart query bar.
_TOKEN_NAMES = ("kind", "eco", "status", "aid", "rel")
_TOKEN_RE = re.compile(
    rf"^(?P<tok>{'|'.join(_TOKEN_NAMES)}):(?P<val>\S+)$"
)

# A bare 44-character CESR identifier (AID or SAID). When the user
# types or pastes one with no `aid:` prefix we promote it to an
# `aid:` chip automatically — the dominant flow for AIDs is paste-from-
# elsewhere, and demanding the user type the prefix first is friction.
# Prefix codes here are the well-known KERI matter primitives; if a
# user pastes something that doesn't match they can still type
# `aid:<value>` manually.
_CESR_AID_RE = re.compile(r"^[EABDOF][A-Za-z0-9_-]{43}$")


class _TemplateCard(QFrame):
    clicked = Signal()
    # Emitted when the user clicks an in-card chip (role-kind, eco)
    # rather than the card body. Carries the parsed filter token to
    # add to the rail.
    filter_requested = Signal(str, str)  # token, value

    def __init__(self, ref: TemplateRef, doc: dict[str, Any],
                 meta: dict[str, Any] | None = None, parent=None):
        super().__init__(parent=parent)
        self._ref = ref
        self._meta = meta or {}
        self._is_valid = (meta or {}).get("schema_validated", True)
        self.setObjectName("card")
        # The whole card is clickable (drills into the editor), so
        # the cursor is always a hand pointer on the card body.
        # In-card chips set their own hover/colour so the user can
        # tell which target their click will actually hit.
        self.setCursor(Qt.PointingHandCursor)
        # Cards in the Invalid view get a 4px amber left accent
        # via the ``[data-status=invalid]`` ObjectName flag; the
        # parent page applies/removes that flag in refresh().
        self._restyle()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._build(doc)

    @property
    def ref(self) -> TemplateRef:
        return self._ref

    @property
    def title(self) -> str:
        return self._title

    def set_alerted(self, alerted: bool) -> None:
        """Toggle the amber accent stripe (used when the parent page
        is showing only invalid templates)."""
        self.setProperty("alerted", alerted)
        self._restyle()

    def _restyle(self) -> None:
        alerted = bool(self.property("alerted"))
        left_border = (
            "border-left:4px solid #F59E0B;" if alerted else ""
        )
        self.setStyleSheet(
            "#card{background:#fff;border:1px solid #e0e3ea;"
            f"border-radius:8px;{left_border}}}"
            "#card:hover{border:1px solid #d97757;"
            f"{left_border}}}"
            "#card QLabel{background:transparent;}"
        )

    def _build(self, doc: dict[str, Any]) -> None:
        from locksmith.plugins.designer.widgets.role_icon_badge import (
            RoleIconBadge,
        )
        from locksmith.plugins.designer.widgets.validation_pill import (
            ValidationPill,
        )
        from locksmith.plugins.designer.widgets.ecosystem_chip import (
            CrossTemplateChip, EcosystemChip,
        )

        header = doc.get("header", {})
        role = doc.get("role", {})
        self._title = header.get("display_name", "(untitled)")
        kind = role.get("kind", "")
        meta = self._meta

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(8)

        top = QHBoxLayout()
        self.role_badge = RoleIconBadge(kind=kind, size=44)
        top.addWidget(self.role_badge)

        text = QVBoxLayout()
        title_row = QHBoxLayout()
        title = QLabel(self._title)
        title.setStyleSheet(
            "font-size:15px;font-weight:600;color:#1A1C20;"
        )
        title_row.addWidget(title)
        version = QLabel(f"v{header.get('version', '0.0')}")
        version.setStyleSheet(
            "color:#888;background:#f6f7f9;padding:2px 7px;"
            "border-radius:8px;font-size:10px;"
        )
        title_row.addWidget(version)
        title_row.addStretch(1)
        self.validation_pill = ValidationPill(
            error_count=meta.get("error_count", 0),
            warning_count=meta.get("warning_count", 0),
        )
        title_row.addWidget(self.validation_pill)
        text.addLayout(title_row)

        # Subtitle: role.id (display only) · clickable role.kind. The
        # role.id is an entity identifier we don't filter on directly
        # in Phase A; ``kind`` is the dimension that maps to the
        # ``kind:`` token. Clicking the kind text adds the filter.
        color = _ROLE_KIND_COLOR.get(kind, "#888888")
        sub_row = QHBoxLayout()
        sub_row.setSpacing(4)
        role_id_lbl = QLabel(role.get("id", ""))
        role_id_lbl.setStyleSheet(
            f"color:{color};font-weight:600;font-size:11px;background:transparent;"
        )
        sub_row.addWidget(role_id_lbl)
        sep = QLabel("·")
        sep.setStyleSheet("color:#666;font-size:11px;background:transparent;")
        sub_row.addWidget(sep)
        self.kind_chip = _ClickableLabel(kind)
        # The underline is the always-visible "I'm interactive" cue;
        # the :hover colour-flip to accent teal tells the user their
        # click is about to hit this chip (filter) and not the card
        # body (drill-in).
        self.kind_chip.setStyleSheet(
            "_ClickableLabel{color:#666;font-size:11px;"
            "background:transparent;text-decoration:underline;}"
            "_ClickableLabel:hover{color:#0ABFB0;}"
        )
        self.kind_chip.setToolTip(f"Filter by kind:{kind}")
        self.kind_chip.clicked.connect(
            lambda _t, k=kind: self.filter_requested.emit("kind", k)
        )
        sub_row.addWidget(self.kind_chip)
        sub_row.addStretch(1)
        text.addLayout(sub_row)
        top.addLayout(text, 1)
        outer.addLayout(top)

        desc = QLabel(header.get("description", ""))
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:12px;color:#444;")
        outer.addWidget(desc)

        # Ecosystem chips — clickable to add eco: filter.
        self.ecosystem_chips: list[EcosystemChip] = []
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        for tag in meta.get("ecosystem_tags", []):
            chip = EcosystemChip(tag)
            chip.clicked.connect(
                lambda t: self.filter_requested.emit("eco", t)
            )
            chip.setToolTip(f"Filter by eco:{tag}")
            self.ecosystem_chips.append(chip)
            chip_row.addWidget(chip)
        forked_from = (header.get("forked_from", {}) or {}).get(
            "template_said"
        )
        if forked_from:
            short = (
                forked_from[:4] + "…" + forked_from[-6:]
                if len(forked_from) > 12 else forked_from
            )
            chip_row.addWidget(
                CrossTemplateChip(kind="forked_from", target=short)
            )
        chip_row.addStretch(1)
        outer.addLayout(chip_row)

        # Pin the footer to the bottom so every card in a row ends
        # at the same y regardless of description length.
        outer.addStretch(1)

        def _pluralize(n: int, singular: str) -> str:
            return f"{n} {singular}{'' if n == 1 else 's'}"

        counts = " · ".join((
            _pluralize(len(doc.get("credentials", {}).get("imports", [])), "import"),
            _pluralize(len(doc.get("credentials", {}).get("exports", [])), "export"),
            _pluralize(len(doc.get("commands", [])), "command"),
            _pluralize(len(doc.get("workflows", [])), "workflow"),
        ))
        counts_label = QLabel(counts)
        counts_label.setStyleSheet("font-size:10px;color:#888;")
        outer.addWidget(counts_label)

        footer = QHBoxLayout()
        self.modified_label = QLabel(
            self._format_modified(meta.get("modified_at"))
        )
        self.modified_label.setStyleSheet("font-size:10px;color:#888;")
        footer.addWidget(self.modified_label)
        footer.addStretch(1)
        if self._ref.kind == "draft":
            badge: QLabel = QLabel("DRAFT")
            badge.setStyleSheet(
                "font-size:9px;color:#aaa;font-family:monospace;"
            )
        else:
            said = self._ref.said or ""
            display = (
                f"{said[:4]}…{said[-4:]}" if len(said) >= 8 else said
            )
            badge = _AIDBadgeLabel(full_said=said, display_text=display)
            badge.setStyleSheet(
                "_AIDBadgeLabel{font-size:9px;color:#aaa;"
                "font-family:monospace;text-decoration:underline;"
                "background:transparent;}"
                "_AIDBadgeLabel:hover{color:#0ABFB0;}"
            )
            badge.clicked_aid.connect(
                lambda s: self.filter_requested.emit("aid", s)
            )
        self.aid_badge = badge
        footer.addWidget(badge)
        outer.addLayout(footer)

    @staticmethod
    def _format_modified(ts: str | None) -> str:
        if not ts:
            return "Modified just now"
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = now - dt
            secs = int(delta.total_seconds())
            if secs < 60:
                return f"Modified {secs}s ago"
            if secs < 3600:
                return f"Modified {secs // 60}m ago"
            if secs < 86400:
                return f"Modified {secs // 3600}h ago"
            return f"Modified {secs // 86400}d ago"
        except (ValueError, TypeError):
            return "Modified just now"

    def mousePressEvent(self, ev):
        # Clicks on in-card chips are accepted by those widgets and
        # never reach here. Anything else = drill into the editor.
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

class TemplatesBrowserPage(QWidget):
    template_open_requested = Signal(object)  # TemplateRef
    new_template_requested = Signal()
    import_file_requested = Signal()

    def __init__(self, *, store: TemplateStore, parent=None):
        super().__init__(parent=parent)
        self._store = store
        self._cards: list[_TemplateCard] = []
        self._loaded: list[tuple] = []
        self._is_empty: bool = True
        # Filter state: ordered list of (token, value) pairs.
        # Within a token type chips OR together; across types they AND.
        self._chips: list[tuple[str, str]] = []
        # Free-text portion of the search bar (anything not parsed
        # into a chip). Used as a substring match against display
        # name, description and role identifiers.
        self._free_text: str = ""
        # Token-prefix dropdown selection inside the search box.
        # Empty string = "All" (free-text or auto-detected). Otherwise
        # the next plain-value submission (no `<token>:` prefix typed)
        # is wrapped in this token.
        self._selected_token: str = ""
        self._build()

    # -- properties -------------------------------------------------------

    @property
    def _showing_invalid_only(self) -> bool:
        """True iff a ``status:invalid`` chip is in the rail. The
        notification pill toggles this chip in/out; the chip × also
        exits the invalid-only view by removing itself."""
        return ("status", "invalid") in self._chips

    # -- UI build ---------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("templates-toolbar")
        toolbar.setStyleSheet(
            "#templates-toolbar{background:#fff;}"
            "#templates-toolbar QLabel{background:transparent;}"
        )
        toolbar_lay = QVBoxLayout(toolbar)
        toolbar_lay.setContentsMargins(20, 14, 20, 10)
        toolbar_lay.setSpacing(8)

        # ---- title + action buttons --------------------------------
        top_row = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        title = QLabel("Micro-Apps")
        title.setStyleSheet(
            "font-size:18px;font-weight:600;color:#1A1C20;"
        )
        title_block.addWidget(title)
        self.summary_label = QLabel("0 micro-apps")
        self.summary_label.setStyleSheet("font-size:11px;color:#888;")
        title_block.addWidget(self.summary_label)
        top_row.addLayout(title_block)
        top_row.addStretch(1)

        btn_import_file = QPushButton("⬇ Import file")
        btn_import_file.clicked.connect(self.import_file_requested.emit)
        btn_import_oobi = QPushButton("🌐 Import via OOBI")
        btn_import_oobi.setEnabled(False)
        btn_import_oobi.setToolTip("Coming in a future release")
        btn_new = QPushButton("+ New template")
        btn_new.setStyleSheet(
            "background:#d97757;color:#fff;font-weight:600;"
            "padding:7px 14px;border-radius:4px;"
        )
        btn_new.clicked.connect(self.new_template_requested.emit)
        for b in (btn_import_file, btn_import_oobi, btn_new):
            top_row.addWidget(b)
        toolbar_lay.addLayout(top_row)

        # ---- smart query bar --------------------------------------
        # The search bar is a single rounded container that holds:
        # an SVG search icon, a token-prefix dropdown (`All ▾`,
        # `Kind ▾`, ...), and the input field. The dropdown tells
        # the bar what kind of thing the user is searching for so
        # they just type a value — the typed value is wrapped in
        # the selected token at commit time. Typing a literal
        # ``<token>:<value>`` still works and wins over the
        # dropdown selection.
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self._search_box = QFrame()
        self._search_box.setObjectName("search-box")
        self._search_box.setStyleSheet(
            "#search-box{background:#F1F3F6;border-radius:14px;}"
            "#search-box[focused=\"true\"]{background:#fff;"
            "border:1px solid #0ABFB0;}"
        )
        self._search_box.setFixedHeight(28)
        box_lay = QHBoxLayout(self._search_box)
        box_lay.setContentsMargins(8, 0, 6, 0)
        box_lay.setSpacing(6)

        # Search SVG icon (replaces the emoji glyph). Resource path
        # comes from the qrc-baked material-icons folder.
        search_pix = QIcon(
            ":/assets/material-icons/search.svg"
        ).pixmap(QSize(18, 18))
        icon_label = QLabel()
        icon_label.setPixmap(search_pix)
        icon_label.setStyleSheet("background:transparent;")
        box_lay.addWidget(icon_label)

        # Token-prefix dropdown — sits left of the input so the
        # user sees "I'm searching for an X" before they type.
        # Default = All (free-text + autodetect).
        self._token_prefix_btn = QPushButton("Auto ▾")
        self._token_prefix_btn.setCursor(Qt.PointingHandCursor)
        self._token_prefix_btn.setFlat(True)
        self._token_prefix_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#5A5F6A;"
            "border:0;padding:0px 6px;font-size:11px;"
            "font-weight:600;}"
            "QPushButton:hover{color:#1A1C20;}"
        )
        self._token_prefix_btn.clicked.connect(
            self._show_token_prefix_menu
        )
        box_lay.addWidget(self._token_prefix_btn)

        # Subtle divider between prefix and input.
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setFixedHeight(16)
        divider.setStyleSheet("background:#D8DBE1;")
        box_lay.addWidget(divider)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "Search micro-apps. Type kind:foo, eco:foo, "
            "or paste an AID — autodetected"
        )
        self._search_input.setStyleSheet(
            "QLineEdit{background:transparent;color:#1A1C20;"
            "border:0;padding:0px 4px;font-size:12px;}"
        )
        self._search_input.textChanged.connect(self._on_search_text_changed)
        self._search_input.returnPressed.connect(self._on_search_submitted)

        # Completer for value suggestions. Built once, model updated
        # in refresh() — replacing the completer mid-callback crashes
        # Qt when the user is actively typing.
        self._completer_model = QStringListModel(self._search_input)
        self._completer = QCompleter(
            self._completer_model, self._search_input,
        )
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.activated.connect(self._on_completer_activated)
        self._search_input.setCompleter(self._completer)

        box_lay.addWidget(self._search_input, 1)
        search_row.addWidget(self._search_box, 1)

        # Invalid notification pill — anchored right of the input.
        # Hidden when invalid_count == 0.
        self._invalid_pill = _PillButton("")
        self._invalid_pill.setStyleSheet(
            "padding:6px 14px;font-size:11px;"
            "font-weight:600;background:transparent;"
        )
        self._invalid_pill.hide()
        self._invalid_pill.clicked.connect(self._on_invalid_pill_clicked)
        search_row.addWidget(self._invalid_pill)

        toolbar_lay.addLayout(search_row)

        # ---- chip rail (parsed filters) ---------------------------
        self._chip_rail_container = QFrame()
        self._chip_rail_container.setStyleSheet("background:transparent;")
        self._chip_rail = QHBoxLayout(self._chip_rail_container)
        self._chip_rail.setContentsMargins(0, 0, 0, 0)
        self._chip_rail.setSpacing(6)
        self._chip_rail_container.hide()
        toolbar_lay.addWidget(self._chip_rail_container)

        root.addWidget(toolbar)

        # ---- card grid panel --------------------------------------
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border:0;background:#f6f7f9;")
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._panel = QFrame()
        self._panel.setObjectName("templates-panel")
        self._panel.setStyleSheet(
            "#templates-panel{background:#f6f7f9;"
            "border:1px solid #ECEEF1;border-radius:8px;}"
        )
        self._panel.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred,
        )
        self._grid = QGridLayout(self._panel)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self._grid.setSpacing(12)
        self._empty_label = QLabel(
            "No micro-apps yet. Click '+ New template' to author "
            "your first one."
        )
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            "color:#888;font-size:14px;padding:60px;"
        )
        self._grid.addWidget(self._empty_label, 0, 0)
        self._scroll.setWidget(self._panel)
        root.addWidget(self._scroll, 1)

    # -- filter logic ----------------------------------------------------

    def _passes_filters(self, loaded: tuple) -> bool:
        ref, doc, meta = loaded

        # Group active chips by token type so OR-within / AND-across
        # is enforced in one pass.
        kinds = [v for t, v in self._chips if t == "kind"]
        ecos = [v for t, v in self._chips if t == "eco"]
        statuses = [v for t, v in self._chips if t == "status"]
        aids = [v for t, v in self._chips if t == "aid"]

        if kinds:
            role_kind = doc.get("role", {}).get("kind", "")
            if role_kind not in kinds:
                return False

        if ecos:
            tags = set(meta.get("ecosystem_tags", []))
            if not (tags & set(ecos)):
                return False

        if statuses:
            is_valid = meta.get("schema_validated", True)
            for s in statuses:
                if s == "invalid" and is_valid:
                    return False
                if s == "valid" and not is_valid:
                    return False

        if aids:
            # The user may paste a partial SAID (e.g. the truncated
            # `ECAR…id00` form shown on the card). Substring match
            # against the template SAID and the forked-from SAID
            # handles both full and partial values; chips OR within
            # the aid facet so any matching haystack passes.
            haystacks = [
                (ref.said or "").lower(),
                ((doc.get("header", {}).get("forked_from") or {})
                 .get("template_said", "") or "").lower(),
            ]
            if not any(
                a.lower() in h for a in aids for h in haystacks if h
            ):
                return False

        # `rel:` chips are a no-op for now — the relationship graph
        # index they depend on isn't online yet. The chip is composed
        # via the popover but doesn't narrow the card set until the
        # backend lands. This keeps Phase C UI useful for shaping
        # queries ahead of the index.

        if self._free_text.strip():
            q = self._free_text.lower().strip()
            haystack = " ".join((
                doc.get("header", {}).get("display_name", ""),
                doc.get("header", {}).get("description", ""),
                doc.get("role", {}).get("display_name", ""),
                doc.get("role", {}).get("id", ""),
            )).lower()
            if q not in haystack:
                return False

        return True

    def _add_chip(self, token: str, value: str) -> None:
        """Add a chip to the rail unless it's already there."""
        chip = (token, value)
        if chip not in self._chips:
            self._chips.append(chip)
        self.refresh()

    def _remove_chip(self, token: str, value: str) -> None:
        self._chips = [c for c in self._chips if c != (token, value)]
        self.refresh()

    def _clear_search_input(self) -> None:
        """Reset the search input without re-firing textChanged."""
        self._search_input.blockSignals(True)
        self._search_input.clear()
        self._search_input.blockSignals(False)
        self._free_text = ""

    # -- search input handlers ------------------------------------------

    def _on_search_text_changed(self, text: str) -> None:
        """Watch for ``<token>:<value> `` (trailing space) and
        promote it to a chip on the fly. Otherwise the text remains
        as the free-text portion of the filter.

        Also auto-promotes a bare 44-char CESR identifier to an
        ``aid:`` chip the instant the buffer matches the pattern.
        This mirrors how browsers auto-detect URLs: pasting a SAID
        in from chat or another wallet shouldn't require the user
        to type the ``aid:`` prefix first.
        """
        if text.endswith(" "):
            stripped = text.strip()
            m = _TOKEN_RE.match(stripped)
            if m:
                self._clear_search_input()
                self._add_chip(m.group("tok"), m.group("val"))
                return
        # CESR AID/SAID heuristic — fires on the keystroke (or paste)
        # that completes the 44-char pattern.
        if _CESR_AID_RE.match(text):
            self._clear_search_input()
            self._add_chip("aid", text)
            return
        self._free_text = text
        self.refresh()

    def _on_search_submitted(self) -> None:
        """Enter: typed `<token>:<value>` always wins; pasted CESR
        always wins; otherwise wrap the bare value in whichever
        token the dropdown has selected. ``selected_token == ""``
        means "All" → leave as free-text."""
        text = self._search_input.text().strip()
        if not text:
            return
        m = _TOKEN_RE.match(text)
        if m:
            self._clear_search_input()
            self._add_chip(m.group("tok"), m.group("val"))
            return
        if _CESR_AID_RE.match(text):
            self._clear_search_input()
            self._add_chip("aid", text)
            return
        if self._selected_token:
            self._clear_search_input()
            self._add_chip(self._selected_token, text)
            return
        # Free text — refresh is already up-to-date from textChanged.
        self.refresh()

    def _on_completer_activated(self, text: str) -> None:
        """User picked a suggestion from the autocomplete popup.

        Suggestions are full tokens like ``eco:insurance`` so we
        promote the whole match to a chip directly.
        """
        m = _TOKEN_RE.match(text)
        if m:
            self._clear_search_input()
            self._add_chip(m.group("tok"), m.group("val"))

    # -- notification pill ----------------------------------------------

    def _on_invalid_pill_clicked(self) -> None:
        """Toggle the ``status:invalid`` chip in/out of the rail.
        When the chip is present the pill renders as the active
        "back" affordance; when absent it renders as the notification.
        """
        if self._showing_invalid_only:
            self._remove_chip("status", "invalid")
        else:
            self._add_chip("status", "invalid")

    def _update_invalid_pill(self, invalid_count: int) -> None:
        """Show / hide / morph the amber notification pill.

        ``invalid_count == 0``     → hidden entirely (clean right edge).
        ``invalid_count > 0`` and  → ``⚠ N invalid`` amber-tint pill.
            chip not active
        ``status:invalid`` active  → ``← Showing N invalid · back``
                                     solid-amber pill.
        """
        if invalid_count == 0:
            self._invalid_pill.set_pill_color(None)
            self._invalid_pill.hide()
            return
        if self._showing_invalid_only:
            self._invalid_pill.setText(
                f"← Showing {invalid_count} invalid · back"
            )
            self._invalid_pill.set_pill_color("#F59E0B")
            self._invalid_pill.setStyleSheet(
                "color:#fff;padding:6px 14px;font-size:11px;"
                "font-weight:600;background:transparent;"
            )
        else:
            self._invalid_pill.setText(f"⚠ {invalid_count} invalid")
            self._invalid_pill.set_pill_color("#FEF3C7")
            self._invalid_pill.setStyleSheet(
                "color:#92400E;padding:6px 14px;font-size:11px;"
                "font-weight:600;background:transparent;"
            )
        # Re-lock the width to the new text so layout doesn't squeeze.
        self._invalid_pill.adjustSize()
        self._invalid_pill.setFixedWidth(
            self._invalid_pill.sizeHint().width()
        )
        self._invalid_pill.show()

    # -- card chip clicks -----------------------------------------------

    def _on_card_chip_clicked(self, token: str, value: str) -> None:
        """A chip on a card was clicked → add it to the filter rail."""
        self._add_chip(token, value)

    # -- refresh --------------------------------------------------------

    def refresh(self) -> None:
        # Tear down the existing grid.
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 0)

        # Reload data from the store. Cheap with a small set; if we
        # ever need to avoid the round-trip on every chip click we can
        # cache and invalidate on store events.
        refs = self._store.list_templates()
        self._loaded = [
            (ref, *self._store.load(ref)) for ref in refs
        ]
        all_n = len(self._loaded)
        invalid_n = sum(
            1 for _r, _d, m in self._loaded
            if not m.get("schema_validated", True)
        )
        plural = "micro-apps" if all_n != 1 else "micro-app"
        self.summary_label.setText(f"{all_n} {plural}")

        # Update completer suggestions: full tokens so the dropdown
        # also doubles as token discovery. Includes template SAIDs as
        # `aid:` suggestions — for Phase B that's the wallet's known-
        # AID source; Phase C will fold in contacts/KEL AIDs.
        suggestions: list[str] = []
        for ref, doc, meta in self._loaded:
            kind = doc.get("role", {}).get("kind", "")
            if kind:
                suggestions.append(f"kind:{kind}")
            for tag in meta.get("ecosystem_tags", []):
                suggestions.append(f"eco:{tag}")
            if ref.said:
                suggestions.append(f"aid:{ref.said}")
        # Deduplicate but preserve insertion order so the autocomplete
        # popup reads coherently.
        seen: set[str] = set()
        deduped: list[str] = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                deduped.append(s)
        self._completer_model.setStringList(deduped)

        # Notification pill — its render depends on chip state.
        self._update_invalid_pill(invalid_n)

        # Chip rail — rebuild from self._chips.
        while self._chip_rail.count():
            old = self._chip_rail.takeAt(0)
            w = old.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for token, value in self._chips:
            if token == "rel":
                ch = _RelChip(value)
                # When the user edits hop/kind via the popover,
                # rewrite that chip's entry in self._chips in place
                # so the value round-trips.
                ch.changed.connect(self._on_rel_chip_changed)
                ch.removed.connect(self._remove_chip)
            else:
                ch = _FilterChip(token, value)
                ch.removed.connect(self._remove_chip)
            self._chip_rail.addWidget(ch)
        if self._chips:
            clear = QPushButton("Clear")
            clear.setCursor(Qt.PointingHandCursor)
            clear.setFlat(True)
            clear.setStyleSheet(
                "QPushButton{background:transparent;color:#0ABFB0;"
                "font-size:11px;font-weight:600;border:0;"
                "padding:4px 8px;}"
                "QPushButton:hover{color:#09A89B;}"
            )
            clear.clicked.connect(
                lambda _checked=False: self._on_clear_filters()
            )
            self._chip_rail.addWidget(clear)
        self._chip_rail.addStretch(1)
        self._chip_rail_container.setVisible(bool(self._chips))

        # Render filtered cards.
        visible = [t for t in self._loaded if self._passes_filters(t)]
        self._is_empty = all_n == 0
        self._empty_label.setVisible(self._is_empty)
        max_row = 0
        for i, (ref, doc, meta) in enumerate(visible):
            card = _TemplateCard(ref=ref, doc=doc, meta=meta)
            card.clicked.connect(
                lambda r=ref: self.template_open_requested.emit(r)
            )
            card.filter_requested.connect(self._on_card_chip_clicked)
            # When showing only-invalid, draw the amber accent stripe
            # on every visible card; otherwise leave it neutral.
            if self._showing_invalid_only:
                card.set_alerted(True)
            row, col = divmod(i, 2)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)
            max_row = max(max_row, row)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        for r in range(max_row + 1):
            self._grid.setRowStretch(r, 1)
        self._grid.setRowStretch(max_row + 1, 10)

    # -- misc helpers ---------------------------------------------------

    def _on_clear_filters(self) -> None:
        self._chips = []
        self._clear_search_input()
        self.refresh()

    def _on_rel_chip_changed(self, old_value: str, new_value: str) -> None:
        """Replace a rel chip's entry in self._chips when its
        popover commits new hop/kind values. Position-preserving
        so the chip rail order is stable."""
        for i, (t, v) in enumerate(self._chips):
            if t == "rel" and v == old_value:
                self._chips[i] = ("rel", new_value)
                break
        self.refresh()

    # -- token prefix dropdown ------------------------------------------

    # Token-prefix dropdown options. Empty token = "Auto" (no fixed
    # facet; the bar autodetects token prefixes the user types and
    # CESR identifiers pasted in, otherwise treats the input as
    # free-text). Picking a specific facet wraps the next bare value
    # in that token at commit time.
    _PREFIX_OPTIONS: tuple[tuple[str, str, str], ...] = (
        ("",       "Auto",         "Search micro-apps. Type kind:foo, "
                                   "eco:foo, or paste an AID — autodetected"),
        ("kind",   "Kind",         "Enter a role kind (e.g. government, organization)"),
        ("eco",    "Ecosystem",    "Enter an ecosystem tag (e.g. insurance)"),
        ("aid",    "AID",          "Paste or type a 44-char CESR identifier"),
        ("rel",    "Relationship", "Enter <hop>:<kind>:<aid> (graph index pending)"),
        ("status", "Status",       "Enter valid or invalid"),
    )

    def _show_token_prefix_menu(self) -> None:
        from PySide6.QtWidgets import QWidgetAction
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#fff;border:1px solid #d8dbe1;padding:6px;}"
        )
        for token, label, _hint in self._PREFIX_OPTIONS:
            row = QLabel(label)
            row.setStyleSheet(
                "font-size:12px;color:#1A1C20;background:transparent;"
                "padding:6px 14px;"
            )
            row.setCursor(Qt.PointingHandCursor)
            act = QWidgetAction(menu)
            act.setDefaultWidget(row)
            row.mousePressEvent = (
                lambda _ev, t=token, m=menu:
                (self._select_token_prefix(t), m.close())
            )
            menu.addAction(act)
        menu.exec(
            self._token_prefix_btn.mapToGlobal(
                self._token_prefix_btn.rect().bottomLeft()
            )
        )

    def _select_token_prefix(self, token: str) -> None:
        """Update which token the bare-value submission will be
        wrapped in. ``token == ""`` means "All" (free-text + autodetect)."""
        self._selected_token = token
        label = next(
            l for t, l, _ in self._PREFIX_OPTIONS if t == token
        )
        hint = next(
            h for t, _, h in self._PREFIX_OPTIONS if t == token
        )
        self._token_prefix_btn.setText(f"{label} ▾")
        self._search_input.setPlaceholderText(hint)
        self._search_input.setFocus()

    # Test/introspection hooks. ``filter_chips_text`` returns the
    # chip-rail labels concatenated; the old pill-strip equivalent.
    def filter_chips_text(self) -> str:
        parts: list[str] = []
        for i in range(self._chip_rail.count()):
            item = self._chip_rail.itemAt(i)
            w = item.widget() if item is not None else None
            if isinstance(w, _FilterChip):
                parts.append(f"{w._token}: {w._value}")
            elif isinstance(w, QPushButton):
                parts.append(w.text())
        return " ".join(parts)

    def card_count(self) -> int:
        return len(self._cards)

    def card_titles(self) -> list[str]:
        return [c.title for c in self._cards]

    def empty_state_visible(self) -> bool:
        return self._is_empty

    def click_first_card(self) -> None:
        if self._cards:
            self._cards[0].clicked.emit()
