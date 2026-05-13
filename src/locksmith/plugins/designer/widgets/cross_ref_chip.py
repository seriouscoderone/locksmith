# -*- encoding: utf-8 -*-
"""CrossRefChip + CrossRefChipStrip: 'Used by' navigable pills."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from locksmith.plugins.designer.crossref import CrossRef


class CrossRefChip(QPushButton):
    navigated = Signal(str, str)  # surface, path

    def __init__(self, ref: CrossRef, parent=None):
        super().__init__(parent=parent)
        self._ref = ref
        self.setText(f"{ref.surface}: {ref.primitive_label}")
        self.setFlat(True)
        self.setStyleSheet(
            "background:#f6f7f9;color:#444;border:1px solid #e0e3ea;"
            "border-radius:10px;padding:3px 10px;font-size:10px;"
        )
        self.clicked.connect(self._on_click)

    def _on_click(self) -> None:
        self.navigated.emit(self._ref.surface, self._ref.primitive_path)


class CrossRefChipStrip(QWidget):
    navigated = Signal(str, str)  # surface, path

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._empty_label = QLabel("Not referenced elsewhere")
        self._empty_label.setStyleSheet("color:#aaa;font-size:11px;")
        self._layout.addWidget(self._empty_label)
        self._layout.addStretch(1)
        self._chips: list[CrossRefChip] = []

    def set_refs(self, refs):
        for c in self._chips:
            c.setParent(None)
            c.deleteLater()
        self._chips = []
        self._empty_label.setVisible(len(refs) == 0)
        # Insert chips just before the trailing stretch so the stretch
        # always remains the last item.
        for ref in refs:
            chip = CrossRefChip(ref)
            chip.navigated.connect(self.navigated.emit)
            insertion_index = self._layout.count() - 1
            self._layout.insertWidget(insertion_index, chip)
            self._chips.append(chip)
