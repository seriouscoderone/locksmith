# -*- encoding: utf-8 -*-
"""
locksmith.plugins.carrier.plugin module

The bundled ``carrier`` role-plugin — a demo Higher-Order Application
surface that stays dormant until the vault holds a valid, active,
chain-verified ``carrier_license`` ACDC issued by the trusted DOI AID.

``required_credential`` is the declarative gate (Task 6,
``locksmith.plugins.credential_gate.RequiredCredential``). Because it is
set, ``PluginManager.discover_and_initialize_vault_ui`` (Task 7) does NOT
auto-register this plugin's pages/menu at vault-UI init — only
``PluginManager.reevaluate_role_gates`` (Task 8, via the
``RevealBundledSurface`` activation strategy) reveals its surface once the
gate is satisfied. This module adds no auto-registration of its own.

Real persona UX for the Carrier HOA is out of scope here; ``get_pages()``
exposes a single placeholder page proving the gate reveals a real widget.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from locksmith.plugins.base import VaultPlugin
from locksmith.plugins.carrier.page import CarrierPlaceholderPage
from locksmith.plugins.credential_gate import RequiredCredential
from locksmith.ui.vault.menu import MenuButton

# Verified trust values for the carrier_license gate (see task brief /
# Global Constraints) — the schema SAID of the carrier_license ACDC and the
# AID of the trusted DOI (Department of Insurance) issuer.
CARRIER_LICENSE_SCHEMA_SAID = "EOBjUL6H9FQdr_PlXVU_cv_iaXdK5Pg8L3M2YQrnHivI"
DOI_ISSUER_AID = "EOtKW1M3PReijqHMu92uX5FG0fCPwIfH7plPQSifb34-"


class CarrierPlugin(VaultPlugin):
    """Bundled demo carrier role-plugin, gated on an active carrier_license."""

    plugin_id = "carrier"
    required_credential = RequiredCredential(
        schema_said=CARRIER_LICENSE_SCHEMA_SAID,
        issuer_aids=[DOI_ISSUER_AID],
        required_state="active",
    )

    def initialize(self, app: Any) -> None:
        self._app = app
        self._page = CarrierPlaceholderPage()

    def on_vault_opened(self, vault: Any) -> None:
        # No plugin-local state to open; gate evaluation/reveal is driven
        # entirely by PluginManager.reevaluate_role_gates.
        pass

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        pass

    def get_pages(self) -> dict[str, QWidget]:
        return {"carrier": self._page}

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(icon=QIcon(), label="Carrier")

    def get_menu_section(self) -> list[QWidget]:
        return []
