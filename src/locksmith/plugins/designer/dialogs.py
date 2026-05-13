# -*- encoding: utf-8 -*-
"""Designer plugin modal dialogs.

CreateTemplateDialog collects the user input needed to stamp out a
canonical-schema-shaped draft template. The controller fills in the
rest (description, version defaults, expression_language, all-false
keri_infrastructure) when saving the draft.

EditHeaderDialog and EditRoleDialog edit the corresponding sections of
an open template, seeding from the current values.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QLineEdit, QPlainTextEdit, QVBoxLayout,
)


_ROLE_KINDS = (
    "individual", "organization", "government", "system", "device", "agent",
)


class CreateTemplateDialog(QDialog):
    create_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("New Template")
        form = QFormLayout(self)
        self._template_display_name = QLineEdit()
        self._template_id = QLineEdit()
        self._template_id.setPlaceholderText("kebab-case id, e.g. carrier-license")
        self._role_display_name = QLineEdit()
        self._role_id = QLineEdit()
        self._role_id.setPlaceholderText("snake_case id, e.g. carrier")
        self._role_kind = QComboBox()
        for k in _ROLE_KINDS:
            self._role_kind.addItem(k)
        form.addRow("Template display name", self._template_display_name)
        form.addRow("Template ID", self._template_id)
        form.addRow("Role display name", self._role_display_name)
        form.addRow("Role ID", self._role_id)
        form.addRow("Role kind", self._role_kind)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Ok,
        )
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _submit(self) -> None:
        self.create_requested.emit({
            "template_display_name": self._template_display_name.text().strip(),
            "template_id": self._template_id.text().strip(),
            "role_display_name": self._role_display_name.text().strip(),
            "role_id": self._role_id.text().strip(),
            "role_kind": self._role_kind.currentText(),
        })
        self.accept()


class EditHeaderDialog(QDialog):
    save_requested = Signal(dict)

    def __init__(self, *, seed: dict[str, Any], parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("Edit header")
        form = QFormLayout(self)
        self._display_name = QLineEdit(seed.get("display_name", ""))
        self._description = QPlainTextEdit(seed.get("description", ""))
        self._description.setFixedHeight(80)
        self._version = QLineEdit(seed.get("version", "1.0"))
        self._expression_language = QLineEdit(seed.get("expression_language", "UEL/1.0"))
        form.addRow("Display name", self._display_name)
        form.addRow("Description", self._description)
        form.addRow("Version", self._version)
        form.addRow("Expression language", self._expression_language)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _submit(self) -> None:
        self.save_requested.emit({
            "display_name": self._display_name.text().strip(),
            "description": self._description.toPlainText().strip(),
            "version": self._version.text().strip(),
            "expression_language": self._expression_language.text().strip(),
        })
        self.accept()


class EditRoleDialog(QDialog):
    save_requested = Signal(dict)

    def __init__(self, *, seed: dict[str, Any], parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle("Edit role")
        outer = QVBoxLayout(self)

        form = QFormLayout()
        self._id = QLineEdit(seed.get("id", ""))
        self._id.setReadOnly(True)
        self._display_name = QLineEdit(seed.get("display_name", ""))
        self._description = QPlainTextEdit(seed.get("description", ""))
        self._description.setFixedHeight(60)
        self._kind = QComboBox()
        for k in _ROLE_KINDS:
            self._kind.addItem(k)
        kind = seed.get("kind", "individual")
        idx = self._kind.findText(kind)
        if idx != -1:
            self._kind.setCurrentIndex(idx)
        form.addRow("ID", self._id)
        form.addRow("Display name", self._display_name)
        form.addRow("Description", self._description)
        form.addRow("Kind", self._kind)
        outer.addLayout(form)

        infra_group = QGroupBox("KERI infrastructure")
        infra_lay = QFormLayout(infra_group)
        infra = seed.get("keri_infrastructure", {})
        self._infra_witness_pool = QCheckBox()
        self._infra_witness_pool.setChecked(bool(infra.get("witness_pool", False)))
        self._infra_watcher_network = QCheckBox()
        self._infra_watcher_network.setChecked(bool(infra.get("watcher_network", False)))
        self._infra_mailbox = QCheckBox()
        self._infra_mailbox.setChecked(bool(infra.get("mailbox", False)))
        self._infra_acdc_registry = QCheckBox()
        self._infra_acdc_registry.setChecked(bool(infra.get("acdc_registry", False)))
        infra_lay.addRow("Witness pool", self._infra_witness_pool)
        infra_lay.addRow("Watcher network", self._infra_watcher_network)
        infra_lay.addRow("Mailbox", self._infra_mailbox)
        infra_lay.addRow("ACDC registry", self._infra_acdc_registry)
        outer.addWidget(infra_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _submit(self) -> None:
        self.save_requested.emit({
            "id": self._id.text(),
            "display_name": self._display_name.text().strip(),
            "description": self._description.toPlainText().strip(),
            "kind": self._kind.currentText(),
            "keri_infrastructure": {
                "witness_pool": self._infra_witness_pool.isChecked(),
                "watcher_network": self._infra_watcher_network.isChecked(),
                "mailbox": self._infra_mailbox.isChecked(),
                "acdc_registry": self._infra_acdc_registry.isChecked(),
            },
        })
        self.accept()
