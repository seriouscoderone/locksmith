# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.dialogs module

Modal dialogs used by the ecosystem viewer pages.
"""
from __future__ import annotations

import html
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
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
        content.setObjectName("createEcosystemContent")
        content.setStyleSheet(
            f"#createEcosystemContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#createEcosystemContent QLabel { background: transparent; }"
        )
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
        content.setObjectName("addMemberContent")
        content.setStyleSheet(
            f"#addMemberContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#addMemberContent QLabel { background: transparent; }"
        )
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
        content.setObjectName("editAnnotationContent")
        content.setStyleSheet(
            f"#editAnnotationContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#editAnnotationContent QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(12)

        target = QLabel(f"<b>Annotating:</b> {html.escape(target_label)}")
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


class ConfirmDeleteEcosystemDialog(LocksmithDialog):
    """'Are you sure?' confirmation before deleting an ecosystem record.

    The schemas and AIDs themselves stay in the wallet — only the user's
    grouping (name, description, member lists, permitted-issuer
    mapping, annotations) is removed. The dialog spells this out so a
    confirmation isn't ambiguous about what's destroyed.
    """

    confirmed = Signal()

    def __init__(self, ecosystem_name: str, n_schemas: int, n_aids: int,
                 parent: QWidget | None = None):
        content = QWidget()
        content.setObjectName("confirmDeleteEcoContent")
        content.setStyleSheet(
            f"#confirmDeleteEcoContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#confirmDeleteEcoContent QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(10)

        prompt = QLabel(
            f"Delete the ecosystem <b>{html.escape(ecosystem_name)}</b>?"
        )
        prompt.setStyleSheet(f"font-size: 14px; color: {colors.TEXT_DARK};")
        prompt.setWordWrap(True)
        layout.addWidget(prompt)

        member_summary = []
        if n_schemas:
            member_summary.append(f"{n_schemas} schema{'s' if n_schemas != 1 else ''}")
        if n_aids:
            member_summary.append(f"{n_aids} issuer{'s' if n_aids != 1 else ''}")
        member_text = " and ".join(member_summary) if member_summary else "no members"

        detail = QLabel(
            f"This ecosystem currently groups {member_text}. The schemas and "
            "AIDs themselves stay in your wallet — only the grouping, its "
            "annotations, and any permitted-issuer assignments are removed."
        )
        detail.setStyleSheet(f"font-size: 12px; color: {colors.TEXT_SECONDARY};")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        cancel_btn = LocksmithInvertedButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        delete_btn = LocksmithButton("Delete ecosystem")
        delete_btn.clicked.connect(self._on_confirm)
        button_row.addStretch()
        button_row.addWidget(cancel_btn)
        button_row.addWidget(delete_btn)

        super().__init__(
            parent=parent,
            title="Delete ecosystem?",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_confirm(self) -> None:
        self.confirmed.emit()
        self.close()


class CreateRoleDialog(LocksmithDialog):
    """Modal for defining a new role in an ecosystem.

    A role is a credential-qualified class of AID. The user picks:
    - A name for the role (free text)
    - The qualification schema (a member schema of the ecosystem whose
      holders qualify for this role)
    - Either an issuer role (chained role — qualification must come from
      a member of that role) OR a list of root issuer AIDs (root role —
      enumerated trust roots)
    """

    role_create_requested = Signal(str, str, str, str, str, list)
    """(ecosystem_name, role_name, description, qualification_schema_said,
    issuer_role_name, root_issuer_aids). issuer_role_name is "" when the
    role is a root role."""

    def __init__(
        self,
        ecosystem_name: str,
        schemas: list[tuple[str, str]],
        existing_roles: list[str],
        issuer_aids: list[tuple[str, str]],
        parent: QWidget | None = None,
    ):
        self.ecosystem_name = ecosystem_name
        self._schema_options = schemas
        self._issuer_aids = issuer_aids

        content = QWidget()
        content.setObjectName("createRoleContent")
        content.setStyleSheet(
            f"#createRoleContent {{ background-color: {colors.BACKGROUND_CONTENT}; }}"
            "#createRoleContent QLabel { background: transparent; }"
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addSpacing(8)
        intro = QLabel(
            "A role is a credential-qualified class of AID. Pick a "
            "qualification credential and define how role members are "
            "issued credentials of that schema (root: enumerated AIDs, "
            "or chained: from members of another role)."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(intro)

        layout.addSpacing(8)

        # Name
        self._name_field = FloatingLabelLineEdit("Role name (e.g., 'state-doi')")
        self._name_field.setFixedWidth(420)
        layout.addWidget(self._name_field)

        layout.addSpacing(8)

        self._desc_field = FloatingLabelLineEdit("Description (optional)")
        self._desc_field.setFixedWidth(420)
        layout.addWidget(self._desc_field)

        layout.addSpacing(12)

        # Qualification schema picker
        layout.addWidget(QLabel("Qualification credential schema:"))
        self._schema_combo = QComboBox()
        self._schema_combo.setFixedWidth(420)
        if not schemas:
            self._schema_combo.addItem("(no schemas in this ecosystem)", "")
            self._schema_combo.setEnabled(False)
        else:
            for label, said in schemas:
                self._schema_combo.addItem(label, said)
        layout.addWidget(self._schema_combo)

        layout.addSpacing(12)

        # Issuer role picker
        layout.addWidget(QLabel("Issuer role:"))
        self._issuer_role_combo = QComboBox()
        self._issuer_role_combo.setFixedWidth(420)
        self._issuer_role_combo.addItem("(root role — pick AIDs below)", "")
        for r in existing_roles:
            self._issuer_role_combo.addItem(r, r)
        layout.addWidget(self._issuer_role_combo)

        layout.addSpacing(8)

        # Root issuer AIDs picker (only relevant for root role)
        self._root_aids_label = QLabel("Trust-root AIDs (only for root role):")
        layout.addWidget(self._root_aids_label)
        self._root_aids_list = QListWidget()
        self._root_aids_list.setFixedWidth(420)
        self._root_aids_list.setFixedHeight(100)
        self._root_aids_list.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection
        )
        for label, aid in issuer_aids:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, aid)
            self._root_aids_list.addItem(item)
        layout.addWidget(self._root_aids_list)

        # Toggle the AIDs list enabled-state based on issuer role choice.
        def _on_issuer_role_changed(idx: int) -> None:
            is_root = self._issuer_role_combo.itemData(idx) == ""
            self._root_aids_label.setVisible(is_root)
            self._root_aids_list.setVisible(is_root)
        self._issuer_role_combo.currentIndexChanged.connect(_on_issuer_role_changed)
        _on_issuer_role_changed(0)

        layout.addSpacing(8)

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
            title=f"Add role to '{ecosystem_name}'",
            content=content,
            buttons=button_row,
            show_close_button=True,
        )

    def _on_create(self) -> None:
        name = self._name_field.text().strip()
        if not name:
            self.show_error("Role name is required.")
            return
        desc = self._desc_field.text().strip()
        schema_said = self._schema_combo.currentData() or ""
        if not schema_said:
            self.show_error("A qualification schema is required.")
            return
        issuer_role = self._issuer_role_combo.currentData() or ""
        root_aids: list[str] = []
        if not issuer_role:
            for item in self._root_aids_list.selectedItems():
                root_aids.append(item.data(Qt.ItemDataRole.UserRole))
            if not root_aids:
                self.show_error(
                    "Root roles require at least one trust-root AID."
                )
                return
        self.role_create_requested.emit(
            self.ecosystem_name, name, desc, schema_said, issuer_role, root_aids,
        )
        self.close()
