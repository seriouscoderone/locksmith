# -*- encoding: utf-8 -*-
"""Shared plugin-test doubles.

`DestroyingSurfaceHost` mirrors the REAL VaultPage: unregister_page destroys the
widget (setParent(None) + deleteLater). Tests that fake the surface host must use
this rather than inventing a forgiving one — a MagicMock host and a double whose
get_pages() returns a fresh widget each call BOTH make the destroyed-widget path
unreachable, which is exactly how revoke -> re-grant shipped broken.

Two details earn their keep here, both because a weaker double measurably fails to
reach the real crash (verified by hand before writing this):

1. Pages are backed by a real ``QStackedWidget``, exactly like
   ``ui/vault/page.py``'s ``content_stack`` (register_page -> addWidget,
   unregister_page -> removeWidget). A bare ``{}`` (as it might look tempting to
   write) never touches the widget's C++ side, so handing back an
   already-destroyed widget doesn't raise anything by itself -- it takes a real
   Qt call (addWidget reparenting it) to reproduce
   ``RuntimeError: Internal C++ object (...) already deleted.`` uncaught, the way
   it actually happens in the running app.
2. ``unregister_page`` forces the pending ``deleteLater()`` to actually run via
   ``QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)``. In the
   real app this is implicit -- revoke and re-grant are separate user actions
   with the Qt event loop idling (and so delivering DeferredDelete) many times in
   between. In a synchronous headless test there is no idle event loop: measured
   here, even 20x ``qapp.processEvents()`` left the widget's C++ side alive
   (``isVisible()`` -> ``False``, no raise) -- only targeting the
   ``DeferredDelete`` event directly collapses it, which is what makes the
   destroyed-widget path reachable at all in this harness.

NOTE: the session-scoped `qapp` fixture already lives in tests/conftest.py:53 —
do NOT add a second one here. A duplicate at this narrower scope would silently
shadow the shared one for every test under tests/plugins/.
"""
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QStackedWidget


class DestroyingSurfaceHost:
    def __init__(self):
        self.pages = {}
        self.entries = {}
        self._stack = QStackedWidget()   # touches widgets' C++ side like the real content_stack

    def register_page(self, key, widget):
        if key in self.pages:
            self._stack.removeWidget(self.pages[key])
        self.pages[key] = widget
        self._stack.addWidget(widget)   # reparents; raises if widget's C++ side is already gone

    def unregister_page(self, key):
        widget = self.pages.pop(key, None)
        if widget is not None:
            self._stack.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
            QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)

    def add_menu_entry(self, plugin_id, entry, section):
        self.entries[plugin_id] = entry

    def remove_menu_entry(self, plugin_id):
        self.entries.pop(plugin_id, None)


def widget_is_live(widget) -> bool:
    """Touch the C++ side; a destroyed QWidget raises RuntimeError.

    DELIBERATELY NOT `locksmith.plugins.base._is_alive`, even though the bodies match:
    that function is the behaviour under test, and a test that measures with the same
    implementation it is validating passes when both are wrong together. Four lines is
    a cheap price for an independent oracle.
    """
    try:
        widget.isVisible()
    except RuntimeError:
        return False
    return True
