# -*- encoding: utf-8 -*-
"""Schema list page for credential workflows inside an open vault.

This module renders the schema table used by the credentials submenu and owns
the refresh path for schema add, edit, and delete operations.
"""
import logging
from typing import Dict, Any, TYPE_CHECKING

from PySide6.QtWidgets import QVBoxLayout, QSizePolicy

from locksmith.ui.toolkit.tables import PaginatedTableWidget
from locksmith.ui.vault.shared.base_list_page import BaseListPage
from locksmith.ui.vault.credentials.schema.add import AddSchemaDialog
from locksmith.ui.vault.credentials.schema.delete import DeleteSchemaDialog
from locksmith.ui.vault.credentials.schema.view import ViewSchemaDialog

if TYPE_CHECKING:
    from locksmith.ui.vault.page import VaultPage

logger = logging.getLogger(__name__)


class SchemaListPage(BaseListPage):
    """
    Content page that lists credential schemas available to the active vault.

    ``VaultPage`` handles navigation to this page. This module is responsible
    for flattening schema and registry state into table rows and opening the
    dialogs that inspect or remove an individual schema.
    """

    def __init__(self, parent: "VaultPage" = None):
        """
        Initialize the SchemaListPage.

        Args:
            parent: Parent widget (VaultPage container)
        """
        super().__init__(parent)

        self.vault_name = None
        self.parent = parent
        self.app = self.parent.app

        # Ensure widget fills parent
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Create main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Set background using palette instead of stylesheet for better control
        from PySide6.QtGui import QPalette, QColor
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#F8F9FF"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Create table widget
        self.icon_path = ":/assets/material-icons/schema.svg"
        self.table = PaginatedTableWidget(
            columns=["Schema Name", "Version", "Issuable", "Issuer", "Description", "Actions"],
            column_widths={"Version": 80, "Issuable": 80, "Issuer": 150, "Description": 250, "Actions": 50},
            title="Credential Schemas",
            icon_path=self.icon_path,
            items_per_page=10,
            show_search=True,
            show_add_button=True,
            add_button_text="Add Schema",
            row_actions=["View","Delete"],
            row_action_icons={
                "View": ":/assets/material-icons/view.svg",
                "Delete": ":/assets/material-icons/delete.svg"
            }
        )

        # Connect signals
        self.table.search_changed.connect(self._on_search)
        self.table.page_changed.connect(self._on_page_changed)
        self.table.sort_changed.connect(self._on_sort_changed)
        self.table.add_clicked.connect(self._on_add_schema)
        self.table.row_action_triggered.connect(self._on_row_action)
        self.table.row_clicked.connect(self._on_row_clicked)

        main_layout.addWidget(self.table)

        logger.info("SchemaListPage initialized with table widget")

    def _load_schema_data(self):
        """
        Load actual schema data from the opened vault.

        This method is called after a vault is opened and ``hby`` is available.
        It walks the schema store and annotates each row with registry-derived
        issuer information when present.
        """
        try:
            schema_data = []
            for (said,), schemer in self.app.vault.hby.db.schema.getItemIter():
                sed = schemer.sed

                # Determine issuer name
                issuer_name = "N/A"
                registry = self.app.vault.rgy.registryByName(said)
                if registry:
                    try:
                        # Get the issuer prefix from the registry
                        issuer_pre = registry.hab.pre
                        # Get the hab for this issuer
                        hab = self.app.vault.hby.habs.get(issuer_pre)
                        if hab:
                            issuer_name = hab.name
                    except Exception as e:
                        logger.warning(f"Error getting issuer for schema {said}: {e}")
                        issuer_name = "N/A"

                schema_dict = {
                    "Schema Name": sed.get("title", ""),
                    "Version": sed.get("version", ""),
                    "Issuable": "Yes" if registry else "No",
                    "Issuer": issuer_name,
                    "Description": sed.get("description", ""),
                    "SAID": said  # Store SAID for delete operation
                }
                schema_data.append(schema_dict)

            self.table.set_static_data(schema_data)
            logger.info(f"Loaded {len(schema_data)} schemas")
        except Exception as e:
            logger.exception(f"Error loading schema data: {e}")
            # Fallback to empty table
            self.table.set_static_data([])

    def _on_add_schema(self):
        """Handle add schema button click."""
        logger.info("Add schema clicked")

        dialog = AddSchemaDialog(app=self.app, parent=self.parent)
        dialog.open()

    def _on_row_action(self, row_data: Dict[str, Any], action: str):
        """Handle a row action selected from the schema actions menu."""
        schema_name = row_data.get('Schema Name', 'Unknown')
        schema_version = row_data.get('Version', 'Unknown')
        schema_said = row_data.get('SAID', '')
        logger.info(f"Row action '{action}' triggered for: {schema_name} v{schema_version}")

        if action == "View":
            # Open view schema dialog
            try:
                dialog = ViewSchemaDialog(
                    icon_path=self.icon_path,
                    app=self.app,
                    schema_said=schema_said,
                    parent=self.parent
                )
                dialog.open()
            except Exception as e:
                logger.exception(f"Error opening view dialog: {e}")
        elif action == "Delete":
            # Open delete confirmation dialog
            dialog = DeleteSchemaDialog(
                schema_name=schema_name,
                said=schema_said,
                icon_path=self.icon_path,
                app=self.app,
                parent=self.parent
            )
            dialog.open()
        else:
            logger.info(f"Action '{action}' not yet implemented")

    def set_vault_name(self, vault_name: str):
        """
        Set the vault name for this page and load schema data.

        ``VaultPage.on_show()`` calls this after a vault is opened so the page
        can read schema data and subscribe to vault-local refresh events.

        Args:
            vault_name: Name of the open vault
        """
        self.vault_name = vault_name

        # Now that the vault is open and hby is available, load the data
        if self.app.vault and self.app.vault.hby:
            self._load_schema_data()

            # Connect to vault signal bridge for automatic list updates
            if hasattr(self.app.vault, 'signals'):
                self.app.vault.signals.doer_event.connect(self._on_doer_event)
                logger.info("SchemaListPage: Connected to vault signal bridge")
        else:
            logger.warning(f"Cannot load schema data - vault or hby not available")

    def _on_doer_event(self, doer_name: str, event_type: str, data: dict):
        """
        Handle doer events from the signal bridge.

        Args:
            doer_name: Name of the doer that emitted the event
            event_type: Type of event
            data: Event data dictionary

        Only schema mutations that change the visible table trigger a reload.
        """
        logger.debug(f"SchemaListPage received doer_event: {doer_name} - {event_type}")

        # Refresh list when a schema is loaded
        if doer_name == "LoadSchemaDoer" and event_type == "schema_loaded":
            logger.info(f"Schema loaded: {data.get('title')}, refreshing list")
            self._load_schema_data()

        # Refresh list when a schema is updated
        elif doer_name == "EditSchemaDoer" and event_type == "schema_updated":
            logger.info(f"Schema updated: {data.get('name')}, refreshing list")
            self._load_schema_data()

        # Refresh list when a schema is deleted
        elif doer_name == "DeleteSchema" and event_type == "schema_deleted":
            logger.info(f"Schema deleted: {data.get('name')}, refreshing list")
            self._load_schema_data()
