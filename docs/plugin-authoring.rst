Plugin Authoring
================

This guide turns the abstract ``PluginBase`` contract into a minimal working
shape that matches the current Locksmith startup and vault lifecycle.

What Locksmith Expects
----------------------

At startup, ``PluginManager.discover_and_initialize(...)`` loads entry points
from the ``locksmith.plugins`` group, instantiates each plugin with no
constructor arguments, calls ``initialize(app)``, then asks the plugin for:

#. one sidebar entry button via ``get_menu_entry()``
#. one submenu section via ``get_menu_section()``
#. a ``page_key -> widget`` mapping via ``get_pages()``

Later, when a vault opens, the application calls ``on_vault_opened(vault)`` and
adds any doers returned by ``get_doers()`` to ``vault.doers``. When a vault
closes, ``on_vault_closed(vault)`` is the teardown point.

Minimal Skeleton
----------------

The following example is intentionally small. It shows the integration points
that matter without inventing extra infrastructure.

.. code-block:: python

   from __future__ import annotations

   from typing import Any

   from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

   from locksmith.plugins.base import PluginBase
   from locksmith.ui.toolkit.widgets.buttons import MenuButton


   class ExamplePluginPage(QWidget):
       def __init__(self, parent: QWidget | None = None):
           super().__init__(parent)
           layout = QVBoxLayout(self)
           layout.addWidget(QLabel("Example plugin page"))


   class ExamplePlugin(PluginBase):
       def __init__(self) -> None:
           self.app: Any | None = None
           self.page = ExamplePluginPage()
           self.entry_button = MenuButton("Example")
           self.section_button = MenuButton("Overview")

       @property
       def plugin_id(self) -> str:
           return "example"

       def initialize(self, app: Any) -> None:
           self.app = app

       def on_vault_opened(self, vault: Any) -> None:
           return None

       def on_vault_closed(self, vault: Any) -> None:
           return None

       def get_menu_entry(self) -> MenuButton:
           return self.entry_button

       def get_menu_section(self) -> list[QWidget]:
           return [self.section_button]

       def get_pages(self) -> dict[str, QWidget]:
           return {"example.overview": self.page}

Page And Menu Wiring
--------------------

The page keys returned by ``get_pages()`` are registered into ``VaultPage``.
The widgets returned by ``get_menu_section()`` become the plugin submenu shown
after ``VaultNavMenu.push_plugin_menu(plugin_id)`` runs.

In practice, a plugin section button should navigate to one of the page keys the
plugin registered. Locksmith's built-in plugin manager handles the outer menu
registration, but the plugin is still responsible for wiring its submenu buttons
to the corresponding page widgets.

Account-Provider Setup Flow
---------------------------

Plugins that also subclass ``AccountProviderPlugin`` can interrupt normal menu
navigation until setup is complete.

That flow works like this:

#. The user clicks the plugin entry in the main vault sidebar.
#. ``VaultPage._on_plugin_entry_clicked()`` checks ``is_setup_complete(vault)``.
#. If setup is incomplete, Locksmith calls ``get_setup_page(vault)``.
#. The returned tuple ``(page_key, should_push_menu)`` decides whether the
   plugin submenu is shown before navigating to the setup page.

This lets a plugin keep account creation or team bootstrap inside its own page
set without changing the host wallet shell.

Entry Point Registration
------------------------

Register the plugin in ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points."locksmith.plugins"]
   example = "my_package.example_plugin:ExamplePlugin"

Once the package is installed in the same environment as Locksmith, the plugin
manager will discover it on startup.