Identifier Pages
================

This slice documents the two built-in identifier list pages that sit alongside
the credentials submenu in an open vault:

- ``locksmith.ui.vault.remotes.list`` for organizer-backed remote identifiers
- ``locksmith.ui.vault.groups.list`` for multisig/group identifiers

Shared Lifecycle
----------------

Both pages are registered by ``VaultPage._register_core_pages()`` and delay real
data access until ``set_vault_name(...)`` runs after a vault opens.

The shared pattern is:

#. Build a ``PaginatedTableWidget`` during page initialization.
#. Wait for ``set_vault_name(...)`` so ``app.vault`` state is available.
#. Load row data from wallet-local organizer, habitat, or registry state.
#. Subscribe to the vault signal bridge so doer events can refresh the visible table.

Remote Identifiers
------------------

``RemoteIdentifierListPage`` presents external identifiers known to the wallet,
including aliases, prefixes, sequence numbers, and inferred roles.

Its refresh path listens for remote-identifier creation, OOBI resolution,
import, connection creation, and role-management events.

The dialog-level remote workflows are documented separately in
``remote-workflows``.

Group Identifiers
-----------------

``GroupIdentifierListPage`` presents local multisig identifiers and annotates
each row with pending multisig or witness-authentication state when applicable.

Its refresh path listens for group inception, join, counseling completion,
rotation, interaction, and witness-authentication events.

The dialog-level group workflows are documented separately in
``group-workflows``.