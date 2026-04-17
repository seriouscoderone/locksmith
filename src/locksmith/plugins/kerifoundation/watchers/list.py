# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.watchers.list module

Boot-backed watcher list for the single onboarded KF account.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy, QLabel
from keri import help

from locksmith.plugins.kerifoundation.db.basing import ACCOUNT_STATUS_ONBOARDED
from locksmith.ui.toolkit.tables.paginated import PaginatedTableWidget

logger = help.ogler.getLogger(__name__)


def _shrink_empty_state_title(table: PaginatedTableWidget, font_size: int = 20):
    """Reduce the plugin empty-state title size without changing shared table code."""
    target_text = f"NO {table.title.upper()}"
    for label in table.empty_state.findChildren(QLabel):
        if label.text() != target_text:
            continue
        label.setStyleSheet(
            label.styleSheet().replace("font-size: 24px;", f"font-size: {font_size}px;")
        )
        break


class WatcherListPage(QWidget):
    """Shows hosted watcher rows for the permanent KF account AID."""

    def __init__(self, app=None, parent=None):
        super().__init__(parent)
        self._app = app
        self._db = None
        self._boot_client = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def set_app(self, app):
        self._app = app

    def set_db(self, db):
        self._db = db

    def set_boot_client(self, boot_client):
        self._boot_client = boot_client

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = PaginatedTableWidget(
            columns=["Name", "Watcher AID", "Region", "Status", "Endpoint"],
            title="KERI Foundation Watchers",
            icon_path=":/assets/material-icons/watcher.svg",
            show_search=True,
            show_add_button=False,
            items_per_page=10,
            monospace_columns=["Watcher AID"],
        )
        _shrink_empty_state_title(self._table)
        self._table.set_static_data([])
        layout.addWidget(self._table)

    def on_show(self):
        if not self._app or not self._db or not self._boot_client:
            self._table.set_static_data([])
            return

        try:
            rows = self._build_rows()
            self._table.set_static_data(rows)
        except Exception as exc:
            logger.exception("Failed loading boot-backed KF watcher rows")
            self._table.load_error.emit(str(exc))
            self._table._display_error()

    def _build_rows(self):
        record = self._db.get_account() if self._db else None
        if record is None or record.status != ACCOUNT_STATUS_ONBOARDED or not record.account_aid:
            return []

        hab = self._app.vault.hby.habByPre(record.account_aid) if self._app and self._app.vault else None
        if hab is None:
            logger.warning("Permanent KF account AID %s is missing from the local wallet", record.account_aid)
            return []

        rows = []
        for watcher in self._boot_client.list_account_watchers(
            hab,
            account_aid=record.account_aid,
            destination=record.boot_server_aid,
        ):
            rows.append(
                {
                    "Name": watcher.name or f"KF Watcher {watcher.eid[:12]}",
                    "Watcher AID": watcher.eid,
                    "Region": watcher.region_name or watcher.region_id or "—",
                    "Status": watcher.status or "Ready",
                    "Endpoint": watcher.url or "—",
                }
            )

        return rows
