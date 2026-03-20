# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.credentials.schema.delete module

Dialog for deleting credential schemas with confirmation
"""
import logging
from typing import TYPE_CHECKING

from locksmith.ui.toolkit.widgets.dialogs import LocksmithResourceDeletionDialog

if TYPE_CHECKING:
    from locksmith.ui.vault.page import VaultPage

logger = logging.getLogger(__name__)


class DeleteSchemaDialog(LocksmithResourceDeletionDialog):
    """Dialog for confirming and deleting a credential schema."""

    def __init__(self, schema_name: str, said: str, icon_path: str, app, parent: "VaultPage" = None):
        """
        Initialize the DeleteSchemaDialog.

        Args:
            schema_name: The name/title of the schema to delete
            said: The SAID of the schema
            icon_path: Path to the icon for the dialog title
            app: Application instance
            parent: Parent widget (VaultPage container)
        """
        self.app = app
        self.schema_name = schema_name
        self.said = said

        # Initialize parent dialog with resource deletion
        super().__init__(
            parent=parent,
            resource_type="schema",
            resource_name=schema_name if schema_name else said,
            title_icon=icon_path
        )

        # Override the delete button click to handle schema deletion
        self.delete_button.clicked.disconnect(self.accept)
        self.delete_button.clicked.connect(self._delete_schema)

        logger.info(f"DeleteSchemaDialog initialized for '{schema_name}' ({said})")

    def _delete_schema(self):
        """Handle the delete button click and perform schema deletion."""
        logger.info(f"Attempting to delete schema '{self.schema_name}' ({self.said})")

        try:
            # Delete the schema from the database
            self.app.vault.rgy.reger.registries.discard(self.said)
            self.app.vault.rgy.reger.regs.rem(self.said)
            self.app.vault.hby.db.schema.rem(keys=(self.said,))

            # Emit deletion event for UI updates
            if hasattr(self.app.vault, 'signals') and self.app.vault.signals:
                self.app.vault.signals.emit_doer_event(
                    doer_name="DeleteSchema",
                    event_type="schema_deleted",
                    data={
                        'name': self.schema_name,
                        'said': self.said,
                        'success': True
                    }
                )

            logger.info(f"Schema '{self.schema_name}' deleted successfully")
            self.accept()

        except Exception as e:
            error_msg = f"Failed to delete schema: {str(e)}"
            logger.error(error_msg)
            self.show_error(error_msg)
