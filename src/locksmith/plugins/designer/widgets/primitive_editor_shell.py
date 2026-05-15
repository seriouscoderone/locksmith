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
        item_count: int = 0,
        role_label: str = "",
        is_valid: bool = True,
        issue_count: int = 0,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._add_label = add_label or "+ Add"
        self._item_count = item_count
        self._role_label = role_label
        self._is_valid = is_valid
        self._issue_count = issue_count
        self._build(surface_label=surface_label, template_label=template_label)
        self.rail_list.populate(items)
        self.rail_list.currentItemChanged.connect(self._on_rail_change)

    def _build(self, *, surface_label: str, template_label: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        strip = QFrame()
        strip.setObjectName("editor-identity-strip")
        # Mock shows the strip flush with the page (no hairline). Drop
        # the border-bottom + use a descendant rule so QLabels inside
        # the strip render transparent on macOS instead of inheriting
        # the system Window palette fill.
        strip.setStyleSheet(
            "#editor-identity-strip{background:#fff;}"
            "#editor-identity-strip QLabel{background:transparent;}"
        )
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

        self.count_label = QLabel(f"({self._item_count})")
        self.count_label.setStyleSheet("color:#888;")
        strip_lay.addWidget(self.count_label)

        strip_lay.addStretch(1)

        role_text = f"Role: {self._role_label}" if self._role_label else ""
        self.role_pill = QLabel(role_text)
        self.role_pill.setStyleSheet(
            "color:#0ABFB0;font-weight:600;padding:3px 8px;"
            "background:#f0fbfa;border-radius:10px;font-size:11px;"
        )
        if not self._role_label:
            self.role_pill.setVisible(False)
        strip_lay.addWidget(self.role_pill)

        if self._is_valid:
            self.valid_pill = QLabel("✓ valid")
            self.valid_pill.setStyleSheet(
                "color:#2a8a4a;background:#eafaf0;border-radius:10px;"
                "padding:3px 8px;font-size:11px;font-weight:600;"
            )
        else:
            self.valid_pill = QLabel(f"⚠ {self._issue_count} issues")
            self.valid_pill.setStyleSheet(
                "color:#a5641a;background:#fdf3e7;border-radius:10px;"
                "padding:3px 8px;font-size:11px;font-weight:600;"
            )
        strip_lay.addWidget(self.valid_pill)

        # Toolbar: validation panel + JSON source toggles.
        sep = QLabel(" ")
        sep.setFixedWidth(8)
        strip_lay.addWidget(sep)
        self.panel_toggle = QPushButton("⚠")
        self.panel_toggle.setCheckable(True)
        self.panel_toggle.setToolTip("Validation panel")
        self.panel_toggle.setFixedSize(28, 28)
        self.panel_toggle.setStyleSheet(
            "QPushButton{color:#666;font-size:13px;border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
            "QPushButton:checked{background:#0ABFB0;color:#fff;}"
        )
        self.panel_toggle.toggled.connect(self._on_panel_toggled)
        strip_lay.addWidget(self.panel_toggle)
        self.json_toggle = QPushButton("{ }")
        self.json_toggle.setCheckable(True)
        self.json_toggle.setToolTip("JSON source view")
        self.json_toggle.setFixedSize(36, 28)
        self.json_toggle.setStyleSheet(
            "QPushButton{color:#666;font-size:11px;font-family:monospace;"
            "border:0;border-radius:4px;}"
            "QPushButton:hover{background:#f6f7f9;color:#1A1C20;}"
            "QPushButton:checked{background:#0ABFB0;color:#fff;}"
        )
        self.json_toggle.toggled.connect(self._on_json_toggled)
        strip_lay.addWidget(self.json_toggle)
        root.addWidget(strip)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        rail_panel = QFrame()
        rail_panel.setFixedWidth(260)
        rail_panel.setObjectName("editor-rail-panel")
        rail_panel.setStyleSheet(
            "#editor-rail-panel{background:#fff;}"
            "#editor-rail-panel QLabel{background:transparent;}"
        )
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

        self.side_panel_container = QFrame()
        self.side_panel_container.setFixedWidth(320)
        self.side_panel_container.setStyleSheet(
            "background:#fff;"
        )
        side_lay = QVBoxLayout(self.side_panel_container)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(0)
        self.side_panel_container.setVisible(False)
        body.addWidget(self.side_panel_container)

        body_holder = QFrame()
        body_holder_lay = QVBoxLayout(body_holder)
        body_holder_lay.setContentsMargins(0, 0, 0, 0)
        body_holder_lay.setSpacing(0)
        body_holder_lay.addLayout(body, 1)
        self.bottom_panel_container = QFrame()
        self.bottom_panel_container.setStyleSheet(
            "background:#fff;"
        )
        self.bottom_panel_container.setFixedHeight(240)
        bottom_lay = QVBoxLayout(self.bottom_panel_container)
        bottom_lay.setContentsMargins(0, 0, 0, 0)
        bottom_lay.setSpacing(0)
        self.bottom_panel_container.setVisible(False)
        body_holder_lay.addWidget(self.bottom_panel_container)
        root.addWidget(body_holder, 1)

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

    def set_side_panel(self, widget: QWidget) -> None:
        layout = self.side_panel_container.layout()
        while layout.count():
            old = layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        layout.addWidget(widget)

    def set_bottom_panel(self, widget: QWidget) -> None:
        layout = self.bottom_panel_container.layout()
        while layout.count():
            old = layout.takeAt(0).widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        layout.addWidget(widget)

    def _on_panel_toggled(self, checked: bool) -> None:
        self.side_panel_container.setVisible(checked)

    def _on_json_toggled(self, checked: bool) -> None:
        self.bottom_panel_container.setVisible(checked)
