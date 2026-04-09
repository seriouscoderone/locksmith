# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.witnesses.list module

Displays local identifiers with their KERI Foundation witness counts.
The user clicks "Add Witnesses" on an identifier row to navigate to
the server-selection / provisioning / registration page.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget, QLabel
from keri import help

from locksmith.plugins.kerifoundation.core.identifiers import iter_local_identifier_choices
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
    """Lists local identifiers with their registered and pending witness counts."""

    add_witnesses_requested = Signal(str)  # hab_pre

    def __init__(self, app=None, parent=None):
        super().__init__(parent)
        self._app = app
        self._db = None
        self._current_rows = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def set_app(self, app):
        self._app = app

    def set_db(self, db):
        self._db = db

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = PaginatedTableWidget(
            columns=["Alias", "Prefix", "Witnesses", "Status"],
            title="KERI Foundation Witnesses",
            icon_path=":/assets/material-icons/witness1.svg",
            show_search=True,
            show_add_button=False,
            items_per_page=10,
            row_actions=["Add Witnesses"],
            row_actions_callback=self._get_row_actions,
            monospace_columns=["Prefix"],
        )
        _shrink_empty_state_title(self._table)
        self._table.row_action_triggered.connect(self._on_row_action)

        layout.addWidget(self._table)

    def on_show(self):
        if not self._app:
            return
        self._refresh_table()

    def _refresh_table(self):
        self._current_rows = self._build_rows()
        self._table.set_static_data(self._current_rows)

    def _build_rows(self):
        items = []

        for alias, prefix in iter_local_identifier_choices(self._app):
            registered = self._count_registered(prefix)
            pending = self._count_pending(prefix)

            # Build display string
            if registered and pending:
                witnesses_text = f"{registered} registered, {pending} pending"
            elif registered:
                witnesses_text = f"{registered} registered"
            elif pending:
                witnesses_text = f"{pending} pending"
            else:
                witnesses_text = "—"

            # Status
            if registered:
                status = "Ready"
                status_color = colors.SUCCESS_TEXT
            elif pending:
                status = "Pending"
                status_color = colors.WARNING_TEXT
            else:
                status = "No witnesses"
                status_color = colors.TEXT_SECONDARY

            items.append({
                "Alias": alias,
                "Prefix": prefix,
                "Witnesses": witnesses_text,
                "Status": status,
                "_hab_pre": prefix,
                "_Status_color": status_color,
            })

        return items

    def _count_registered(self, hab_pre):
        if not self._db:
            return 0
        count = 0
        try:
            for _ in self._db.witnesses.getItemIter(keys=(hab_pre,)):
                count += 1
        except Exception:
            pass
        return count

    def _count_pending(self, hab_pre):
        """Count provisioned-but-not-registered witnesses for an identifier."""
        if not self._db:
            return 0

        # Collect registered EIDs for this identifier
        registered_eids = set()
        try:
            for (_keys, record) in self._db.witnesses.getItemIter(keys=(hab_pre,)):
                registered_eids.add(record.eid)
        except Exception:
            pass

        # Count provisioned records whose EID is not yet registered
        count = 0
        try:
            for (_keys, record) in self._db.provisionedWitnesses.getItemIter(keys=(hab_pre,)):
                if record.eid and record.eid not in registered_eids:
                    count += 1
        except Exception:
            pass

        return count

    def _get_row_actions(self, row_data):
        return ["Add Witnesses"], {}

    def _on_row_action(self, data, action):
        if action == "Add Witnesses":
            hab_pre = data.get("_hab_pre", "")
            if hab_pre:
                self.add_witnesses_requested.emit(hab_pre)
