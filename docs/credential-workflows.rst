Credential Workflows
====================

This slice documents the dialog-level workflows behind the credential areas of
an open vault.

Covered dialogs:

- ``locksmith.ui.vault.credentials.issued.issue``
- ``locksmith.ui.vault.credentials.issued.view``
- ``locksmith.ui.vault.credentials.issued.grant``
- ``locksmith.ui.vault.credentials.issued.delete``
- ``locksmith.ui.vault.credentials.received.accept``
- ``locksmith.ui.vault.credentials.received.accept_grant``
- ``locksmith.ui.vault.credentials.received.delete``
- ``locksmith.ui.vault.credentials.schema.add``
- ``locksmith.ui.vault.credentials.schema.view``
- ``locksmith.ui.vault.credentials.schema.delete``

Issue And Inspect Credentials
-----------------------------

``IssueCredentialDialog`` is the main issuance workflow. It selects a schema,
chooses a local or remote recipient, generates any schema-driven input fields,
and starts the issuance doer.

``ViewIssuedCredentialDialog`` is the read-heavy details view for an issued
credential. It shows the SAID, schema, issuer, recipient, status, issuance
time, and the raw credential JSON.

Grant Or Delete Issued Credentials
----------------------------------

``GrantCredentialDialog`` supports the two outbound sharing flows for an issued
credential:

#. send a grant to a remote identifier over IPEX
#. save the generated grant message to disk in CESR form

``DeleteIssuedCredentialDialog`` wraps the shared resource-deletion dialog and
removes an issued credential from the local registry.

Receive And Admit Credentials
-----------------------------

``AcceptCredentialDialog`` is the intake step for a received credential. It
loads a grant message file from disk, parses it into the local stores, and then
opens the full admit dialog.

``AcceptGrantDialog`` is the read-heavy admit step. It displays the grant
metadata, any optional note from the grantor, and the parsed credential
attributes before the user commits the admit action.

``DeleteReceivedCredentialDialog`` removes a received credential from the local
registry.

Load, Inspect, And Delete Schemas
---------------------------------

``AddSchemaDialog`` loads a schema into the wallet either by OOBI or file
import. It can also start the additional setup needed to use that schema for
credential issuance.

``ViewSchemaDialog`` shows schema metadata, issuance readiness, and the raw
schema JSON.

``DeleteSchemaDialog`` removes a loaded schema and emits the refresh event used
by the schema list page.