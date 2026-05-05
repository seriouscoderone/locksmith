# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.dialogs module

Modal dialogs used by the ecosystem viewer pages.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import (
    FloatingLabelLineEdit,
    LocksmithButton,
    LocksmithDialog,
    LocksmithInvertedButton,
)


class CreateEcosystemDialog(LocksmithDialog):
    """Modal for creating a new ecosystem grouping."""

    ecosystem_create_requested = Signal(str, str)  # (name, description)

    def __init__(self, app: Any, parent: QWidget | None = None):
        self.app = app

        content = QWidget()
        content.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(12)

        intro = QLabel(
            "An ecosystem is a user-defined grouping of schemas and issuer "
            "AIDs that work together. Pick a short, recognizable name."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(intro)

        layout.addSpacing(12)

        self._name_field = FloatingLabelLineEdit("Ecosystem name")
        self._name_field.setFixedWidth(360)
        layout.addWidget(self._name_field)

        layout.addSpacing(12)

        self._desc_field = FloatingLabelLineEdit("Description (optional)")
        self._desc_field.setFixedWidth(360)
        layout.addWidget(self._desc_field)

        layout.addSpacing(12)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self._cancel_button = LocksmithInvertedButton("Cancel")
        self._cancel_button.clicked.connect(self.close)
        self._create_button = LocksmithButton("Create")
        self._create_button.clicked.connect(self._on_create)
        button_row.addStretch()
        button_row.addWidget(self._cancel_button)
        button_row.addWidget(self._create_button)

        super().__init__(
            parent=parent,
            title="Create ecosystem",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_create(self) -> None:
        name = self._name_field.text().strip()
        if not name:
            self.show_error("Ecosystem name is required.")
            return
        desc = self._desc_field.text().strip()
        self.ecosystem_create_requested.emit(name, desc)
        self.close()


class AddMemberDialog(LocksmithDialog):
    """Pick a schema (or AID) from the wallet and add it to the ecosystem.

    `kind` is 'schema' or 'aid'. `candidates` is a list of (label, key)
    tuples — label is shown to the user, key is what gets emitted.
    """

    member_picked = Signal(str)  # emits the selected key (SAID or AID)

    def __init__(self, kind: str, candidates: list[tuple[str, str]],
                 parent: QWidget | None = None):
        self.kind = kind
        self._candidates = candidates

        content = QWidget()
        content.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(12)

        intro = QLabel(
            f"Pick a {kind} from this wallet to add to the ecosystem. "
            f"Only items already in the wallet are eligible — resolve OOBIs / "
            f"add schemas via the regular wallet flow first."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(intro)

        layout.addSpacing(8)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #E0E3EA; border-radius: 4px; font-size: 12px; }"
        )
        for label, key in candidates:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._list.addItem(item)
        self._list.setMinimumHeight(200)
        layout.addWidget(self._list)

        layout.addSpacing(12)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        cancel = LocksmithInvertedButton("Cancel")
        cancel.clicked.connect(self.close)
        add = LocksmithButton("Add")
        add.clicked.connect(self._on_add)
        button_row.addStretch()
        button_row.addWidget(cancel)
        button_row.addWidget(add)

        super().__init__(
            parent=parent,
            title=f"Add {kind} to ecosystem",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_add(self) -> None:
        item = self._list.currentItem()
        if item is None:
            self.show_error(f"Select a {self.kind} first.")
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        self.member_picked.emit(key)
        self.close()


class EditAnnotationDialog(LocksmithDialog):
    """Edit a single annotation note. Tags input is comma-separated."""

    annotation_saved = Signal(str, list)  # (note_text, tags)
    annotation_deleted = Signal()

    def __init__(self, target_label: str, current_note: str, current_tags: list[str],
                 parent: QWidget | None = None):
        content = QWidget()
        content.setStyleSheet(f"background-color: {colors.BACKGROUND_CONTENT};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(12)

        target = QLabel(f"<b>Annotating:</b> {target_label}")
        target.setWordWrap(True)
        target.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 12px;")
        layout.addWidget(target)

        layout.addSpacing(8)

        note_label = QLabel("Note")
        note_label.setStyleSheet(f"color: {colors.TEXT_DARK}; font-size: 12px;")
        layout.addWidget(note_label)

        self._note_field = QPlainTextEdit()
        self._note_field.setPlainText(current_note)
        self._note_field.setStyleSheet(
            "QPlainTextEdit { background: white; border: 1px solid #E0E3EA; border-radius: 4px; font-size: 12px; padding: 6px; }"
        )
        self._note_field.setFixedHeight(120)
        layout.addWidget(self._note_field)

        layout.addSpacing(8)

        self._tags_field = FloatingLabelLineEdit("Tags (comma-separated)")
        self._tags_field.setText(", ".join(current_tags))
        self._tags_field.setFixedWidth(360)
        layout.addWidget(self._tags_field)

        layout.addSpacing(12)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        delete_btn = LocksmithInvertedButton("Delete annotation")
        delete_btn.clicked.connect(self._on_delete)
        cancel_btn = LocksmithInvertedButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        save_btn = LocksmithButton("Save")
        save_btn.clicked.connect(self._on_save)
        button_row.addWidget(delete_btn)
        button_row.addStretch()
        button_row.addWidget(cancel_btn)
        button_row.addWidget(save_btn)

        super().__init__(
            parent=parent,
            title="Edit annotation",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_save(self) -> None:
        note = self._note_field.toPlainText().strip()
        tags = [t.strip() for t in self._tags_field.text().split(",") if t.strip()]
        self.annotation_saved.emit(note, tags)
        self.close()

    def _on_delete(self) -> None:
        self.annotation_deleted.emit()
        self.close()
