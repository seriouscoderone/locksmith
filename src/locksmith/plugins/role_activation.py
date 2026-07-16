# -*- encoding: utf-8 -*-
"""
locksmith.plugins.role_activation module

The activation seam behind the HOA "credential = app access" model. When a
role-plugin's credential gate flips unsatisfied->satisfied, the plugin manager
delegates the actual *reveal* to a ``RoleActivationStrategy``. This keeps the
gate logic (does the holder have the credential?) cleanly separated from the
activation mechanism (what does "unlock" mean for this deployment?).

``RevealBundledSurface`` is the POC strategy: the plugin is already loaded but
dormant (its pages/menu were withheld at vault-UI init), so activation simply
registers its surface into the surface host and deactivation removes it. Future
strategies (InstallFromGatedSource, ProvisionTools, StartAgentHarness) implement
the same protocol without touching the gate.

The surface host is the ``VaultPage``/``HoaVaultPage``; it exposes
``register_page`` / ``unregister_page`` and ``add_menu_entry`` /
``remove_menu_entry`` (all symmetric).
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RoleActivationStrategy(Protocol):
    """How a satisfied credential gate turns into a revealed plugin surface.

    Implementations must be idempotent from the manager's point of view: the
    manager only calls ``activate`` on an unsatisfied->satisfied edge and
    ``deactivate`` on satisfied->unsatisfied, tracking active roles itself.
    """

    def activate(self, plugin: Any, credential: Any, surface_host: Any) -> None: ...

    def deactivate(self, plugin: Any, surface_host: Any) -> None: ...


class RevealBundledSurface:
    """POC strategy: the plugin is already loaded but dormant; activation
    registers its menu entry + pages into the surface host, deactivation
    removes them. Future strategies implement the same protocol without
    touching the gate."""

    def activate(self, plugin: Any, credential: Any, surface_host: Any) -> None:
        for key, widget in plugin.get_pages().items():
            surface_host.register_page(key, widget)
        entry = plugin.get_menu_entry()
        if entry is not None:
            surface_host.add_menu_entry(
                plugin.plugin_id, entry, plugin.get_menu_section(),
            )

    def deactivate(self, plugin: Any, surface_host: Any) -> None:
        for key in plugin.get_pages().keys():
            surface_host.unregister_page(key)
        surface_host.remove_menu_entry(plugin.plugin_id)
