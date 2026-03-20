# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.credentials.issued.delete module

Dialog for confirming and deleting an issued credential.
"""
from keri import help
from typing import TYPE_CHECKING

from locksmith.core import credentialing
from locksmith.ui.toolkit.widgets.dialogs import LocksmithResourceDeletionDialog

if TYPE_CHECKING:
    from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)


class DeleteIssuedCredentialDialog(LocksmithResourceDeletionDialog):
    """Dialog for confirming and deleting an issued credential."""

    def __init__(self, schema_name: str, said: str, icon_path: str, app, parent: "VaultPage" = None):
        """
        Initialize the DeleteIssuedCredentialDialog.

        Args:
            schema_name: Name/title of the credential schema (for confirmation)
            said: SAID of the credential to delete
            icon_path: Path to the icon for the dialog title
            app: Application instance
            parent: Parent widget (VaultPage container)
        """
        self.app = app
        self.schema_name = schema_name
        self.said = said

        # Initialize parent with resource details
        super().__init__(
            parent=parent,
            resource_type="issued credential",
            resource_name=schema_name if schema_name else said,
            title_icon=icon_path
        )

        # Override the delete button click to handle credential deletion
        self.delete_button.clicked.disconnect(self.accept)
        self.delete_button.clicked.connect(self._delete_credential)

        logger.info(f"DeleteIssuedCredentialDialog initialized for '{schema_name}' ({said})")

    def _delete_credential(self):
        """Handle the delete button click and perform credential deletion."""
        logger.info(f"Attempting to delete issued credential '{self.schema_name}' ({self.said})")

        try:
            # Delete the credential from the registry
            credentialing.delete_credential(self.app.vault.rgy.reger, self.said)

            # Emit deletion event for UI updates
            if hasattr(self.app.vault, 'signals') and self.app.vault.signals:
                self.app.vault.signals.emit_doer_event(
                    doer_name="DeleteIssuedCredential",
                    event_type="credential_deleted",
                    data={
                        'schema': self.schema_name,
                        'said': self.said,
                        'success': True
                    }
                )

            logger.info(f"Issued credential '{self.schema_name}' deleted successfully")
            self.accept()

        except Exception as e:
            error_msg = f"Failed to delete credential: {str(e)}"
            logger.exception(error_msg)
            self.show_error(error_msg)
