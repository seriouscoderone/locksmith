# -*- encoding: utf-8 -*-
"""Usurance Actuarial role-plugin (HOA #4).

Bundled with the usurance brand ([plugins] bundled); its surface is revealed
by the credential gate when the vault holds a valid, active, chain-verified
actuary_role credential issued by usurance-admin. Placeholder surface —
this proves multi-role coexistence, not actuarial function. Domain content
lives here (a brand-bundled role plugin), never in framework code.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from locksmith.plugins.base import VaultPlugin
from locksmith.plugins.credential_gate import RequiredCredential
from locksmith.plugins.actuary.page import ActuaryPlaceholderPage
from locksmith.ui.vault.menu import MenuButton

# Pins verified against the bundled usurance-internal EGF by
# tests/plugins/roles/test_pin_regression.py (Task 13).
ACTUARY_ROLE_SCHEMA_SAID = "EIGJb6GFT8bLi2nDuS4ekp6gSr8JqIcpPE9AKjiCClLY"
USURANCE_ADMIN_AID = "EGjm-X1JMz-yKFeumEZ9meSVNvnV8VTXmjJMlyBVMMTO"


class ActuaryPlugin(VaultPlugin):
    """Bundled Usurance Actuarial role-plugin, gated on an active actuary_role."""

    plugin_id = "actuary"
    required_credential = RequiredCredential(
        schema_said=ACTUARY_ROLE_SCHEMA_SAID,
        issuer_aids=[USURANCE_ADMIN_AID],
        required_state="active",
    )

    def initialize(self, app: Any) -> None:
        self._app = app
        self._page = ActuaryPlaceholderPage()

    def on_vault_opened(self, vault: Any) -> None:
        # No plugin-local state to open; gate evaluation/reveal is driven
        # entirely by PluginManager.reevaluate_role_gates.
        pass

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        pass

    def get_pages(self) -> dict[str, QWidget]:
        return {"actuary": self._page}   # page key == plugin_id == EGF role id

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(icon=QIcon(), label="Actuarial")

    def get_menu_section(self) -> list[QWidget]:
        return []
