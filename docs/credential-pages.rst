Credential Pages
================

This slice documents the three built-in pages behind the credentials submenu:

- ``locksmith.ui.vault.credentials.issued.list`` for credentials created by the active vault
- ``locksmith.ui.vault.credentials.received.list`` for credentials accepted into the active vault
- ``locksmith.ui.vault.credentials.schema.list`` for schema records used by issuance flows

Shared Lifecycle
----------------

All three pages are registered by ``VaultPage._register_core_pages()`` before a vault opens.
That keeps the page registry stable while delaying actual data access until
``VaultPage.on_show()`` calls ``set_vault_name(...)`` on every mounted page.

The shared pattern is:

#. Build a ``PaginatedTableWidget`` during page initialization.
#. Wait for ``set_vault_name(...)`` so ``app.vault`` and ``app.vault.hby`` are available.
#. Load table rows from wallet-local state.
#. Subscribe to the vault signal bridge so doer events can refresh the table.

Issued Credentials
------------------

``IssuedCredentialsListPage`` reads issued credential SAIDs from the registry, clones the
 full credential payloads, and presents row actions for view, grant, revoke, delete, send,
 and export flows.

Its refresh path listens for events from issuance, revocation, and issued-credential deletion
doers.

Received Credentials
--------------------

``ReceivedCredentialsListPage`` reads subject-linked credentials for the vault's local AIDs
and exposes actions for accept, view, delete, and export workflows.

Its refresh path listens for credential receipt, deletion, and grant-admission completion.

Schema Records
--------------

``SchemaListPage`` walks the schema database directly and annotates each row with issuer
metadata when a registry can be resolved for that schema.

Its refresh path listens for schema load, update, and delete events.

The dialog-level credential workflows are documented separately in
``credential-workflows``.