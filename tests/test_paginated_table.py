"""Regression test for the PySide6 event-filter crash (v0.1.5 crash report).

The old code did ``self.table.viewport().installEventFilter(self)`` on the
PaginatedTableWidget. If the surrounding widget's Python wrapper was GC'd
while the inner viewport stayed alive, the next event delivered through
``QCoreApplicationPrivate::sendThroughObjectEventFilters`` would call into
a dangling override and segfault inside Shiboken's lookup.

The fix swaps the filter for a ``QTableWidget`` subclass that overrides
``leaveEvent`` directly. This pins the override lifetime to the Qt widget
that owns it (Qt's parent chain), eliminating the filter dispatch path
entirely.
"""
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QEnterEvent

from locksmith.ui.toolkit.tables.paginated import (
    PaginatedTableWidget,
    _HoverClearingTableWidget,
)


def test_inner_table_is_hover_clearing_subclass(qapp):
    w = PaginatedTableWidget(title="t", columns=["a", "b"])
    assert isinstance(w.table, _HoverClearingTableWidget)


def test_leave_event_clears_selection(qapp):
    w = PaginatedTableWidget(title="t", columns=["a", "b"])
    w.table.setRowCount(1)
    w.table.selectRow(0)
    assert w.table.selectionModel().hasSelection()

    leave = QEvent(QEvent.Type.Leave)
    w.table.leaveEvent(leave)

    assert not w.table.selectionModel().hasSelection()


def test_no_event_filter_installed_on_viewport(qapp):
    """Belt-and-suspenders: the install-event-filter line is gone.

    If a future refactor restores the old pattern, this test breaks.
    We assert no Python override is reachable via the filter chain by
    confirming the PaginatedTableWidget does not define eventFilter.
    """
    w = PaginatedTableWidget(title="t", columns=["a", "b"])
    # The override that crashed lived on PaginatedTableWidget; make sure
    # it's not back.
    assert "eventFilter" not in PaginatedTableWidget.__dict__
