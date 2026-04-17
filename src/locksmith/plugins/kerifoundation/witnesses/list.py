# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.witnesses.list module

Boot-backed witness list for the single onboarded KF account.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget, QLabel
from keri import help

from locksmith.plugins.kerifoundation.db.basing import ACCOUNT_STATUS_ONBOARDED
from locksmith.ui import colors
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


class WitnessOverviewPage(QWidget):
    """Shows hosted witness rows for the permanent KF account AID."""

    add_witnesses_requested = Signal(str)

    def __init__(self, app=None, parent=None):
        super().__init__(parent)
        self._app = app
        self._db = None
        self._boot_client = None
        self._current_rows = []
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
            columns=["Name", "Witness AID", "Region", "Auth", "Endpoint"],
            title="KERI Foundation Witnesses",
            icon_path=":/assets/material-icons/witness1.svg",
            show_search=True,
            show_add_button=False,
            items_per_page=10,
            row_actions=[],
            row_actions_callback=self._get_row_actions,
            monospace_columns=["Witness AID"],
        )
        _shrink_empty_state_title(self._table)
        self._table.row_action_triggered.connect(self._on_row_action)
        layout.addWidget(self._table)

    def on_show(self):
        if not self._app or not self._db or not self._boot_client:
            self._table.set_static_data([])
            return
        self._refresh_table()

    def _refresh_table(self):
        try:
            self._current_rows = self._build_rows()
            self._table.set_static_data(self._current_rows)
        except Exception as exc:
            logger.exception("Failed loading boot-backed KF witness rows")
            self._current_rows = []
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
        for witness in self._boot_client.list_account_witnesses(
            hab,
            account_aid=record.account_aid,
            destination=record.boot_server_aid,
        ):
            local_state = self._db.witnesses.get(keys=(record.account_aid, witness.eid))
            if local_state is None:
                auth = "Pending local auth"
                auth_color = colors.WARNING_TEXT
            elif local_state.batch_mode:
                auth = "Batch TOTP configured"
                auth_color = colors.SUCCESS_TEXT
            else:
                auth = "TOTP configured"
                auth_color = colors.SUCCESS_TEXT

            rows.append(
                {
                    "Name": witness.name or f"KF Witness {witness.eid[:12]}",
                    "Witness AID": witness.eid,
                    "Region": witness.region_name or witness.region_id or "—",
                    "Auth": auth,
                    "Endpoint": witness.url or "—",
                    "_Auth_color": auth_color,
                }
            )

        return rows

    @staticmethod
    def _get_row_actions(_row_data):
        return [], {}

    @staticmethod
    def _on_row_action(_data, _action):
        return
