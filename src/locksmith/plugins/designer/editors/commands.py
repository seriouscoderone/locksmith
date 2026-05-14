# -*- encoding: utf-8 -*-
"""CommandsEditorPage: 'I do …' surface.

Right-pane sections (canonical schema):
  Identity · Route + counterparty_role · Preconditions counts ·
  Emissions list · Entry JSON · Used-by.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.crossref import CrossRefIndex
from locksmith.plugins.designer.editors._shared import (
    kind_color_for, make_section,
)
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip
from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


def _emission_summary(em: dict[str, Any]) -> str:
    kind = em.get("kind", "?")
    if kind == "exchange":
        ex = em.get("exchange", {})
        ek = ex.get("kind", "?")
        if ek == "credential":
            verb = ex.get("verb", "?")
            imp = ex.get("imported_credential_id")
            exp = ex.get("exported_credential_id")
            target = f"imp:{imp}" if imp else (f"exp:{exp}" if exp else "")
            return f"exchange/credential {verb} {target}".strip()
        if ek == "message":
            return f"exchange/message {ex.get('pattern', '?')} {ex.get('route', '?')}"
        return f"exchange/{ek}"
    if kind == "lifecycle_advance":
        return (f"lifecycle_advance: "
                f"{em.get('exported_credential_id', '?')} → "
                f"{em.get('to_state', '?')}")
    if kind == "aggregate_event":
        return (f"aggregate_event: {em.get('aggregate_id', '?')} ← "
                f"{em.get('event_type', '?')}")
    return f"{kind} (unknown)"


class _CommandSectionPane(QWidget):
    def __init__(self, crossrefs: CrossRefIndex, parent=None):
        super().__init__(parent=parent)
        self._crossrefs = crossrefs
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._identity = make_section("Identity")
        self._name = QLineEdit()
        self._id = QLineEdit()
        self._id.setReadOnly(True)
        self._identity.layout().addWidget(QLabel("Name"))
        self._identity.layout().addWidget(self._name)
        self._identity.layout().addWidget(QLabel("ID"))
        self._identity.layout().addWidget(self._id)
        lay.addWidget(self._identity)

        self._route_section = make_section("Route")
        self._route_label = QLabel("(unset)")
        self._counterparty_label = QLabel("")
        self._counterparty_label.setStyleSheet("color:#666;font-size:11px;")
        self._route_section.layout().addWidget(self._route_label)
        self._route_section.layout().addWidget(self._counterparty_label)
        lay.addWidget(self._route_section)

        self._preconditions = make_section("Preconditions")
        self._pre_label = QLabel("(none)")
        self._pre_label.setStyleSheet("color:#444;")
        self._preconditions.layout().addWidget(self._pre_label)
        lay.addWidget(self._preconditions)

        self._emissions = make_section("Emissions")
        self._emissions_label = QLabel("(none)")
        self._emissions_label.setStyleSheet("color:#444;")
        self._emissions_label.setWordWrap(True)
        self._emissions.layout().addWidget(self._emissions_label)
        lay.addWidget(self._emissions)

        self._json_section = make_section("Entry JSON (read-only)")
        self._json_view = QPlainTextEdit()
        self._json_view.setReadOnly(True)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._json_view.setFont(mono)
        self._json_view.setFixedHeight(120)
        self._json_section.layout().addWidget(self._json_view)
        lay.addWidget(self._json_section)

        self._used_by = make_section("Used by")
        self.chip_strip = CrossRefChipStrip()
        self._used_by.layout().addWidget(self.chip_strip)
        lay.addWidget(self._used_by)
        lay.addStretch(1)

    def set_entry(self, entry: dict[str, Any]) -> None:
        self._name.setText(entry.get("name", ""))
        self._id.setText(entry.get("id", ""))

        route = entry.get("route", "(unset)")
        self._route_label.setText(route)
        cp = entry.get("counterparty_role")
        self._counterparty_label.setText(
            f"Counterparty: {cp}" if cp else ""
        )

        auth = len(entry.get("auth_preconditions", []))
        state = len(entry.get("state_preconditions", []))
        temporal = len(entry.get("temporal_preconditions", []))
        parts = []
        if auth:
            parts.append(f"{auth} auth")
        if state:
            parts.append(f"{state} state")
        if temporal:
            parts.append(f"{temporal} temporal")
        self._pre_label.setText(", ".join(parts) if parts else "(none)")

        emissions = entry.get("emissions", [])
        if emissions:
            self._emissions_label.setText(
                "\n".join(f"• {_emission_summary(e)}" for e in emissions)
            )
        else:
            self._emissions_label.setText("(none)")

        self._json_view.setPlainText(
            json.dumps(entry, indent=2, sort_keys=True)
        )

        key = f"command:{entry.get('id', '')}"
        self.chip_strip.set_refs(self._crossrefs.consumers_of(key))

    def text_summary(self) -> str:
        return " ".join([
            self._name.text(),
            self._route_label.text(),
            self._pre_label.text(),
            self._emissions_label.text(),
        ])


def _command_subtitle(c: dict) -> str:
    parts: list[str] = []
    cp = c.get("counterparty_role")
    if cp:
        parts.append(f"→ {cp}")
    emissions = c.get("emissions") or []
    n = len(emissions)
    if n:
        parts.append(f"{n} emission{'s' if n != 1 else ''}")
    return " · ".join(parts) if parts else ""


class CommandsEditorPage(QWidget):
    navigated = Signal(str, str)

    def __init__(
        self,
        *,
        model: TemplateModel,
        crossrefs: CrossRefIndex,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._model = model
        items = self._rail_items()
        template_label = model.doc.get("header", {}).get("display_name", "(untitled)")
        self.shell = PrimitiveEditorShell(
            surface_label="Commands",
            template_label=template_label,
            items=items,
            add_label="+ Add command",
            item_count=len(items),
            role_label=model.doc.get("role", {}).get("id", ""),
            is_valid=True,
            parent=self,
        )
        self._pane = _CommandSectionPane(crossrefs=crossrefs)
        if items:
            self._pane.set_entry(model.doc.get("commands", [{}])[0])
        self.shell.set_right_pane(self._pane)
        from locksmith.plugins.designer.widgets.validation_panel import (
            ValidationPanel,
        )
        from locksmith.plugins.designer.widgets.json_source_view import (
            JsonSourceView,
        )
        self._validation_panel = ValidationPanel()
        self._json_source_view = JsonSourceView()
        self.shell.set_side_panel(self._validation_panel)
        self.shell.set_bottom_panel(self._json_source_view)
        self.shell.item_selected.connect(self._on_select)
        self._pane.chip_strip.navigated.connect(self.navigated.emit)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.shell)

    def _rail_items(self) -> list[RailItem]:
        color = kind_color_for(self._model.doc.get("role", {}).get("kind", ""))
        items = []
        for c in self._model.doc.get("commands", []):
            items.append(RailItem(
                id=c.get("id", ""),
                label=c.get("name") or c.get("id") or "(unnamed)",
                subtitle=_command_subtitle(c),
                kind_color=color,
                has_errors=False,
            ))
        return items

    def _on_select(self, item_id: str) -> None:
        for c in self._model.doc.get("commands", []):
            if c.get("id") == item_id:
                self._pane.set_entry(c)
                return

    def section_text(self) -> str:
        return self._pane.text_summary()
