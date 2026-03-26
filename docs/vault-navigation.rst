Vault Navigation
================

This slice documents the two modules that control the in-vault user flow:

- ``locksmith.ui.vault.page`` owns the content stack and page registry.
- ``locksmith.ui.vault.menu`` owns the left-hand navigation, credentials submenu,
  and plugin submenu transitions.

VaultPage
---------

``VaultPage`` is the container shown after a vault is opened. It creates a
``VaultNavMenu`` on the left and a ``QStackedWidget`` on the right.

Core pages are registered during initialization, while plugin pages are registered later
through ``register_page(key, widget)`` when ``PluginManager.discover_and_initialize(...)``
asks each plugin for its page mapping.

Important behaviors:

- ``register_page()`` accepts both built-in and plugin-provided pages.
- ``_show_page()`` switches the active page and emits a doer event for menu-driven loads.
- ``_on_plugin_entry_clicked()`` handles the distinction between account-provider plugins
  that may require setup first and other plugins that can open their submenu immediately.

VaultNavMenu
------------

``VaultNavMenu`` is the left sidebar for an open vault. It supports:

- the base wallet navigation buttons
- a credentials submenu
- dynamically registered plugin entry points and plugin submenus
- a collapsible and lockable expanded state

Important behaviors:

- ``register_plugin_section()`` inserts a plugin entry button into the vault menu and stores
  that plugin's submenu widgets for later activation.
- ``push_plugin_menu()`` hides the base vault menu and reveals a plugin submenu.
- ``pop_to_vault_menu()`` returns from plugin or credentials submenus to the base vault menu.

Plugin Navigation Flow
----------------------

#. ``PluginManager`` loads plugins and calls ``VaultNavMenu.register_plugin_section(...)``.
#. A user clicks a plugin entry in the vault menu.
#. ``VaultPage._on_plugin_entry_clicked()`` asks whether the plugin is an account provider
   with incomplete setup.
#. If setup is complete, the plugin submenu is pushed and the first plugin nav button is
   activated.
#. If setup is incomplete, ``VaultPage`` shows the plugin's setup page instead.