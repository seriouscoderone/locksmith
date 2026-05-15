# -*- encoding: utf-8 -*-
"""KindRail: left-rail list with kind-color dots and validation badges."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem


@dataclass(frozen=True)
class RailItem:
    id: str
    label: str
    kind_color: str  # CSS hex, e.g. "#0ABFB0"
    has_errors: bool
    subtitle: str | None = None
    group_header: str | None = None


def _dot_icon(color_hex: str, size: int = 12) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return pix


class KindRail(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setStyleSheet(
            "QListWidget{background:#fff;border:0;}"
            "QListWidget::item{padding:10px 12px;border-bottom:1px solid #f0f2f5;}"
            "QListWidget::item:selected{background:#f6f7f9;color:#1A1C20;}"
            "QListWidget::item:disabled{"
            "color:#888;background:transparent;font-size:9px;"
            "font-weight:600;letter-spacing:0.5px;padding:6px 12px;}"
        )

    def populate(self, items: list[RailItem]) -> None:
        self.clear()
        first_selectable = -1
        for r in items:
            if r.group_header:
                hdr = QListWidgetItem(r.group_header)
                hdr.setFlags(Qt.NoItemFlags)
                hdr.setData(Qt.UserRole, None)
                self.addItem(hdr)
                continue
            main = r.label + ("  ⛔" if r.has_errors else "")
            text = f"{main}\n{r.subtitle}" if r.subtitle else main
            item = QListWidgetItem(text)
            item.setIcon(_dot_icon(r.kind_color))
            item.setData(Qt.UserRole, r.id)
            self.addItem(item)
            if first_selectable == -1:
                first_selectable = self.count() - 1
        if first_selectable >= 0:
            self.setCurrentRow(first_selectable)

    def selected_id(self) -> str | None:
        item = self.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)
