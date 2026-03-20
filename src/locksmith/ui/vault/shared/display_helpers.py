# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.shared.display_helpers module

Shared display helper functions for accept dialogs.
"""
from PySide6.QtWidgets import QLabel, QHBoxLayout, QVBoxLayout

from locksmith.ui import colors


def resolve_alias(app, pre: str) -> str | None:
    """
    Resolve a prefix to an alias.

    Args:
        app: Application instance
        pre: Identifier prefix to resolve

    Returns:
        Alias string if found, None otherwise
    """
    # Check local identifiers
    for prefix, hab in app.vault.hby.habs.items():
        if prefix == pre:
            return hab.name

    # Check contacts
    contact = app.vault.org.get(pre)
    if contact:
        return contact.get('alias', '')

    return None


def add_info_row(layout: QVBoxLayout, label_text: str, value_text: str, label_width: int = 130) -> None:
    """
    Add an info row with label and value.

    Args:
        layout: Parent layout to add the row to
        label_text: Label text
        value_text: Value text
        label_width: Fixed width for the label (default 130)
    """
    row_layout = QHBoxLayout()
    row_layout.setContentsMargins(0, 0, 0, 0)

    label = QLabel(label_text)
    label.setStyleSheet("font-weight: 500;")
    label.setFixedWidth(label_width)
    row_layout.addWidget(label)

    value = QLabel(value_text)
    value.setStyleSheet(f"color: {colors.TEXT_DARK};")
    value.setWordWrap(True)
    row_layout.addWidget(value, stretch=1)

    layout.addLayout(row_layout)
