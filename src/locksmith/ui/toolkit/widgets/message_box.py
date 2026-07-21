# -*- encoding: utf-8 -*-
"""Shared QMessageBox builders for Locksmith.

``build_selectable_message_box`` produces a warning box whose text can be
selected with the mouse, so cryptic error detail (e.g. KERI serialization
failures surfaced as ``InstallError``) can be copied out to relay. Callers
own the ``.exec()`` — the builder never blocks, which keeps it unit-testable.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget


def build_selectable_message_box(
    parent: QWidget | None,
    title: str,
    message: str,
    icon: QMessageBox.Icon = QMessageBox.Icon.Warning,
) -> QMessageBox:
    """Build a warning ``QMessageBox`` with selectable/copyable text.

    Args:
        parent: Parent widget (or ``None``).
        title: Window title.
        message: Body text (kept fully selectable).
        icon: Message-box icon (default Warning).

    Returns:
        The configured box. The caller is responsible for ``.exec()``.
    """
    box = QMessageBox(parent)
    box.setIcon(icon)
    # NOTE: QMessageBox.setWindowTitle() is a documented no-op on macOS (Qt
    # follows the platform HIG, which omits alert titles), so the title is
    # applied via the underlying Qt property instead. This does not change
    # what is visible on macOS (the native alert never showed a title there
    # either) — it only keeps ``windowTitle()`` introspectable everywhere,
    # matching behavior on Linux/Windows where the plain setter already works.
    box.setProperty("windowTitle", title)
    box.setText(message)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return box
