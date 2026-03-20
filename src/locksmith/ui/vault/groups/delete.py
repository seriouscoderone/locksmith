# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.groups.delete module

Dialog for deleting group identifiers with confirmation
"""
from typing import TYPE_CHECKING

from keri import help

from locksmith.core import habbing
from locksmith.ui.toolkit.widgets.dialogs import LocksmithResourceDeletionDialog

if TYPE_CHECKING:
    from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)


class DeleteGroupIdentifierDialog(LocksmithResourceDeletionDialog):
    """Dialog for confirming and deleting an identifier."""

    def __init__(self, identifier_alias: str, icon_path: str, app, parent: "VaultPage" = None):
        """
        Initialize the DeleteGroupIdentifierDialog.

        Args:
            identifier_alias: The alias of the identifier to delete
            icon_path: Path to the icon for the dialog title
            app: Application instance
            parent: Parent widget (VaultPage container)
        """
        self.app = app
        self.identifier_alias = identifier_alias

        # Initialize parent dialog with resource deletion
        super().__init__(
            parent=parent,
            resource_type="identifier",
            resource_name=identifier_alias,
            title_icon=icon_path
        )

        # Override the delete button click to handle identifier deletion
        self.delete_button.clicked.disconnect(self.accept)
        self.delete_button.clicked.connect(self._delete_identifier)

        logger.info(f"DeleteGroupIdentifierDialog initialized for '{identifier_alias}'")

    def _delete_identifier(self):
        """Handle the delete button click and perform identifier deletion."""
        logger.info(f"Attempting to delete identifier '{self.identifier_alias}'")

        try:
            # Call the delete function
            result = habbing.delete_identifier(
                app=self.app,
                alias=self.identifier_alias
            )

        except Exception as e:
            result = {'success': False, 'message': str(e)}

        # Handle result
        if result['success']:
            logger.info(f"Identifier '{self.identifier_alias}' deleted successfully")
            self.accept()
        else:
            logger.error(f"Failed to delete identifier: {result['message']}")
            self.show_error(result['message'])