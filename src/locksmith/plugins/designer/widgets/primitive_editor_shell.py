# -*- encoding: utf-8 -*-
"""PrimitiveEditorShell: shared layout for every per-primitive editor.

Layout:
  ┌──────────────────────────────────────────────┐
  │ ← Back · <template label> · <surface label>  │  identity strip
  ├──────────┬───────────────────────────────────┤
  │ rail     │ right pane                        │
  │  • item  │ (sections set by the editor)      │
  │  • item  │                                   │
  │  + Add   │                                   │
  └──────────┴───────────────────────────────────┘
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from locksmith.plugins.designer.widgets.kind_rail import KindRail, RailItem


class PrimitiveEditorShell(QWidget):
    item_selected = Signal(str)   # id of selected rail item
    add_clicked = Signal()
    back_clicked = Signal()

    def __init__(
        self,
        *,
        surface_label: str,
        template_label: str,
        items: list[RailItem],
        add_label: str | None = None,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._add_label = add_label or "+ Add"
        self._build(surface_label=surface_label, template_label=template_label)
        self.rail_list.populate(items)
        self.rail_list.currentItemChanged.connect(self._on_rail_change)

    def _build(self, *, surface_label: str, template_label: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        strip = QFrame()
        strip.setStyleSheet("background:#fff;border-bottom:1px solid #e0e3ea;")
        strip_lay = QHBoxLayout(strip)
        strip_lay.setContentsMargins(16, 10, 16, 10)
        self.back_button = QPushButton("← Back")
        self.back_button.setFlat(True)
        self.back_button.clicked.connect(self.back_clicked.emit)
        strip_lay.addWidget(self.back_button)
        sep1 = QLabel("·")
        sep1.setStyleSheet("color:#ccc;")
        strip_lay.addWidget(sep1)
        self.identity_label = QLabel(template_label)
        self.identity_label.setStyleSheet("font-weight:600;color:#1A1C20;")
        strip_lay.addWidget(self.identity_label)
        sep2 = QLabel("·")
        sep2.setStyleSheet("color:#ccc;")
        strip_lay.addWidget(sep2)
        self.surface_label = QLabel(surface_label)
        self.surface_label.setStyleSheet("color:#666;")
        strip_lay.addWidget(self.surface_label)
        strip_lay.addStretch(1)
        root.addWidget(strip)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        rail_panel = QFrame()
        rail_panel.setFixedWidth(260)
        rail_panel.setStyleSheet("background:#fff;border-right:1px solid #e0e3ea;")
        rail_lay = QVBoxLayout(rail_panel)
        rail_lay.setContentsMargins(0, 0, 0, 0)
        rail_lay.setSpacing(0)
        self.add_button = QPushButton(self._add_label)
        self.add_button.setStyleSheet(
            "QPushButton{background:#fff;border:0;"
            "border-bottom:1px solid #e0e3ea;"
            "padding:10px 12px;text-align:center;color:#0ABFB0;"
            "font-weight:600;}"
            "QPushButton:hover{background:#f0fbfa;}"
        )
        self.add_button.clicked.connect(self.add_clicked.emit)
        rail_lay.addWidget(self.add_button)
        self.rail_list = KindRail()
        rail_lay.addWidget(self.rail_list, 1)
        body.addWidget(rail_panel)

        self.right_pane_container = QFrame()
        self.right_pane_container.setStyleSheet("background:#f6f7f9;")
        QVBoxLayout(self.right_pane_container).setContentsMargins(20, 20, 20, 20)
        body.addWidget(self.right_pane_container, 1)
        root.addLayout(body, 1)

    @property
    def selected_item_id(self) -> str | None:
        return self.rail_list.selected_id()

    def set_right_pane(self, widget: QWidget) -> None:
        layout = self.right_pane_container.layout()
        while layout.count():
            old = layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        layout.addWidget(widget)

    def repopulate_rail(self, items: list[RailItem]) -> None:
        self.rail_list.populate(items)

    def _on_rail_change(self, current, _previous) -> None:
        if current is None:
            return
        item_id = current.data(Qt.UserRole)
        if item_id:
            self.item_selected.emit(item_id)
