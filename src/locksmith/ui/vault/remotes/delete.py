# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.remotes.delete module

Dialog for deleting remote remote identifiers with confirmation
"""
from typing import TYPE_CHECKING

from keri import help

from locksmith.core import remoting
from locksmith.ui.toolkit.widgets.dialogs import LocksmithResourceDeletionDialog

if TYPE_CHECKING:
    from locksmith.ui.vault.page import VaultPage

logger = help.ogler.getLogger(__name__)


class DeleteRemoteIdDialog(LocksmithResourceDeletionDialog):
    """Dialog for confirming and deleting a remote identifier."""

    def __init__(self, remote_id_alias: str, prefix: str, icon_path: str, app, parent: "VaultPage" = None):
        """
        Initialize the DeleteRemoteIdDialog.

        Args:
            remote_id_alias: The alias of the remote_id to delete
            icon_path: Path to the icon for the dialog title
            app: Application instance
            parent: Parent widget (VaultPage container)
        """
        self.app = app
        self.remote_id_alias = remote_id_alias
        self.prefix = prefix

        # Initialize parent dialog with resource deletion
        super().__init__(
            parent=parent,
            resource_type="remote identifier",
            resource_name=remote_id_alias,
            title_icon=icon_path
        )

        # Override the delete button click to handle remote identifier deletion
        self.delete_button.clicked.disconnect(self.accept)
        self.delete_button.clicked.connect(self._delete_remote_id)

        logger.info(f"DeleteRemoteIdDialog initialized for '{remote_id_alias}'")

    def _delete_remote_id(self):
        """Handle the delete button click and perform remote identifier deletion."""
        logger.info(f"Attempting to delete remote identifier '{self.remote_id_alias}'")

        # Call the delete function
        result = remoting.delete_remote_id(
            app=self.app,
            alias=self.remote_id_alias,
            rm_id=self.prefix
        )

        # Handle result
        if result['success']:
            logger.info(f"Remote Identifier '{self.remote_id_alias}' deleted successfully")
            self.accept()
        else:
            logger.error(f"Failed to delete remote identifier: {result['message']}")
            self.show_error(result['message'])