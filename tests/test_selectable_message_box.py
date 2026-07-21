from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from locksmith.ui.toolkit.widgets.message_box import build_selectable_message_box


def test_message_box_text_is_selectable(qapp):
    box = build_selectable_message_box(None, "Upgrade failed", "cryptic InstallError text")

    assert box.text() == "cryptic InstallError text"
    assert box.windowTitle() == "Upgrade failed"
    assert box.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    assert box.icon() == QMessageBox.Icon.Warning
