from PySide6.QtWidgets import QApplication

from locksmith.ui.toolkit.widgets.buttons import LocksmithCopyButton

COPY_ICON = ":/assets/material-icons/content_copy.svg"
CHECK_ICON = ":/assets/material-icons/check.svg"


def test_copy_sets_clipboard_and_emits(qapp):
    btn = LocksmithCopyButton(copy_content="invalid literal for int()")
    seen = []
    btn.copied.connect(lambda: seen.append(True))

    btn.click()

    assert QApplication.clipboard().text() == "invalid literal for int()"
    assert seen == [True]


def test_copy_swaps_to_checkmark_then_reverts(qapp):
    btn = LocksmithCopyButton(copy_content="boom")

    btn.click()
    assert btn.icon_path == CHECK_ICON

    btn._revert_icon()
    assert btn.icon_path == COPY_ICON


def test_empty_content_is_a_noop(qapp):
    btn = LocksmithCopyButton(copy_content="")
    seen = []
    btn.copied.connect(lambda: seen.append(True))

    btn.click()

    assert seen == []
    assert btn.icon_path == COPY_ICON


def test_icon_color_kwarg_reverts_to_tint_not_raw(qapp):
    # A tinted copy button reverts to its base tint, not the raw icon.
    btn = LocksmithCopyButton(copy_content="x", icon_color="#DC2626")
    btn.click()
    assert btn.icon_path == CHECK_ICON
    btn._revert_icon()
    assert btn.icon_path == COPY_ICON  # base icon path restored
