# -*- encoding: utf-8 -*-
"""Usurance Chief Underwriting Officer role-plugin.

Bundled with the usurance brand ([plugins] bundled); its surface is revealed by the
credential gate when the vault holds a valid, active, chain-verified cuo_role
credential issued by usurance-admin. Domain content lives here (a brand-bundled role
plugin), never in framework code.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

from locksmith.plugins.base import VaultPlugin, _is_alive
from locksmith.plugins.credential_gate import RequiredCredential
from locksmith.plugins.cuo.page import CuoMandatePage
from locksmith.plugins.actuary.plugin import USURANCE_ADMIN_AID
from locksmith.ui.vault.menu import MenuButton

# Pins verified against the bundled usurance-internal EGF by
# tests/plugins/roles/test_pin_regression.py.
CUO_ROLE_SCHEMA_SAID = "EIE7Wb01SJeYU4HNbzP2En2XyGZSkRtIElXX7MOLlSTH"


class CuoPlugin(VaultPlugin):
    """Bundled Usurance Underwriting role-plugin, gated on an active cuo_role."""

    plugin_id = "cuo"                     # MUST equal the entry-point name
    required_credential = RequiredCredential(
        schema_said=CUO_ROLE_SCHEMA_SAID,
        issuer_aids=[USURANCE_ADMIN_AID],
        required_state="active",
    )

    def initialize(self, app: Any) -> None:
        self._app = app
        self._page = None            # built lazily; a destroyed page must not be reused

    def on_vault_opened(self, vault: Any) -> None:
        pass                              # reveal is driven by reevaluate_role_gates

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        pass

    def get_pages(self) -> dict[str, QWidget]:
        # RevealBundledSurface.deactivate -> VaultPage.unregister_page DESTROYS this
        # widget (setParent(None) + deleteLater). Handing the same instance back on a
        # later activate re-registers a dead C++ object and raises. Revoke -> re-grant
        # is a real arc, so the page is rebuilt whenever the previous one is gone.
        if self._page is None or not _is_alive(self._page):
            self._page = CuoMandatePage()
        return {"cuo": self._page}        # page key == plugin_id == EGF role id

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(
            icon=QIcon(":/assets/material-icons/balance.svg"), label="Underwriting"
        )

    def get_menu_section(self) -> list[QWidget]:
        return []
