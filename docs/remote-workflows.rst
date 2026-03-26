Remote Workflows
================

This slice documents the dialog-level workflows behind the remote identifier
section of an open vault.

Covered dialogs:

- ``locksmith.ui.vault.remotes.add``
- ``locksmith.ui.vault.remotes.view``
- ``locksmith.ui.vault.remotes.filter``
- ``locksmith.ui.vault.remotes.challenge``
- ``locksmith.ui.vault.remotes.delete``

Connect A Remote Identifier
---------------------------

``AddRemoteIdentifierDialog`` supports two intake paths:

#. resolve an OOBI URL
#. import a KERI event file from disk

The dialog validates alias and source fields, derives the remote prefix when it
can, then starts either ``ResolveOobiDoer`` or ``ImportDoer``. Completion and
failure are reported back through the vault signal bridge.

Inspect And Manage A Remote Identifier
--------------------------------------

``ViewRemoteIdentifierDialog`` is the read-heavy details view for a remote
identifier. It shows:

- the identifier AID
- key-state metadata
- key event log content
- OOBI and mailbox details
- prior challenge verifications
- current roles and role-management actions

The same dialog also provides a key-state refresh action that re-runs OOBI
resolution for the current remote identifier.

Filter The Remote List
----------------------

``FilterRemoteIdentifiersDialog`` is intentionally narrow. It only filters the
visible list by transferability and emits a small payload back to
``RemoteIdentifierListPage``.

Challenge-Response Verification
-------------------------------

``ChallengeRemoteIdentifierDialog`` splits verification into two tabs:

#. generate a 12-word challenge phrase to send outward
#. respond to a received challenge using one of the local identifiers

When the user submits a response, the dialog creates a
``ChallengeVerificationDoer`` and listens for completion events from the vault
signal bridge.

Delete A Remote Identifier
--------------------------

``DeleteRemoteIdDialog`` wraps the shared resource-deletion dialog and calls the
remoting helper that removes the organizer-backed remote identifier entry.