"""Regression tests for the notification toast lifecycle on the main window.

Observed live during the HOA #3 two-app demo (2026-07-20): firing two
``show_notification_toast`` calls back-to-back raised
``AttributeError: 'NoneType' object has no attribute 'deleteLater'``.

Root cause: ``NotificationToast.close_toast`` emits its ``closed`` signal
synchronously, and the window connects that signal to ``_on_toast_closed``,
which sets ``self.current_toast = None``. When ``show_notification_toast``
closed the previous toast it then dereferenced ``self.current_toast`` again --
now ``None`` -- to call ``.deleteLater()``.
"""
from types import SimpleNamespace

from PySide6.QtWidgets import QMainWindow

from locksmith.ui.toolkit.widgets.toast import NotificationToast
from locksmith.ui.window import LocksmithWindow


class _ToastHarnessWindow(LocksmithWindow):
    """A LocksmithWindow that skips the heavy app/plugin init.

    It keeps the real ``show_notification_toast`` / ``_on_toast_closed``
    methods and provides only the attributes those methods touch, so the
    synchronous-signal re-entrancy is exercised faithfully.
    """

    def __init__(self):
        QMainWindow.__init__(self)
        self.current_toast = None
        self.toolbar = SimpleNamespace(height=lambda: 0)


def test_back_to_back_toasts_do_not_crash(qapp):
    window = _ToastHarnessWindow()
    try:
        window.show_notification_toast("t1", "first credential arrived", 1)
        # Second call must not raise even though closing the first toast
        # re-enters _on_toast_closed and nulls current_toast.
        window.show_notification_toast("t2", "second credential arrived", 2)

        qapp.processEvents()

        assert isinstance(window.current_toast, NotificationToast)
        assert window.current_toast.message == "second credential arrived"
    finally:
        window.close()
