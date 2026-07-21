# tests/test_error_banner_copy.py
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog
from locksmith.ui.toolkit.widgets.page import LocksmithFormPage


def test_dialog_copy_button_carries_full_message(qapp):
    dlg = LocksmithDialog(title="Test")
    dlg.show_error("invalid literal for int() with base 16: b'xyz'")

    assert dlg.error_copy_button.get_copy_content() == (
        "invalid literal for int() with base 16: b'xyz'"
    )


def test_dialog_copy_button_hidden_until_hover(qapp):
    dlg = LocksmithDialog(title="Test")
    dlg.show_error("boom")

    assert dlg._error_copy_opacity.opacity() == 0.0

    dlg.eventFilter(dlg.error_banner, QEvent(QEvent.Type.Enter))
    assert dlg._error_copy_opacity.opacity() == 1.0

    dlg.eventFilter(dlg.error_banner, QEvent(QEvent.Type.Leave))
    assert dlg._error_copy_opacity.opacity() == 0.0


def test_dialog_copy_click_copies_full_message(qapp):
    dlg = LocksmithDialog(title="Test")
    dlg.show_error("cryptic detail")
    dlg.error_copy_button.click()

    assert QApplication.clipboard().text() == "cryptic detail"


def _page():
    return LocksmithFormPage(title="Test", icon_path="")


def test_page_copy_button_carries_full_message(qapp):
    page = _page()
    page.show_error("invalid literal for int() with base 16: b'zz'")
    assert page.error_copy_button.get_copy_content() == (
        "invalid literal for int() with base 16: b'zz'"
    )


def test_page_copy_button_hidden_until_hover(qapp):
    page = _page()
    page.show_error("boom")
    assert page._error_copy_opacity.opacity() == 0.0

    page.eventFilter(page.error_banner, QEvent(QEvent.Type.Enter))
    assert page._error_copy_opacity.opacity() == 1.0

    page.eventFilter(page.error_banner, QEvent(QEvent.Type.Leave))
    assert page._error_copy_opacity.opacity() == 0.0
