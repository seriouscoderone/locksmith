# -*- encoding: utf-8 -*-
"""
locksmith.plugins.producer_licensing.plugin module

ProducerLicensingPlugin — registers a sidebar entry, lens page, and
auto-loads the schema + creates the registry on the configured issuer
AID when a vault opens.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget
from keri import help

from locksmith.core.credentialing import LoadSchemaDoer
from locksmith.plugins.base import PluginBase
from locksmith.plugins.producer_licensing.manifest import PRODUCER_LICENSING
from locksmith.plugins.producer_licensing.pages import ProducerLicensingPage
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer

logger = help.ogler.getLogger(__name__)

# The issuer AID alias the plugin looks for in the vault. Hardcoded for slice 1;
# real deployments would resolve this from a published, well-known DOI registry.
#
# Honest naming: until a real Department of Insurance bootstraps an AID on this
# substrate, Usurance operates an explicit proxy authority. The alias makes the
# proxy nature and jurisdiction visible at every read. See docs/usurance-proxy-doi.md
# for the migration path to a real-DOI-issued chain of authority.
ISSUER_ALIAS = "usurance-proxy-doi-ca"

# Page key registered with the VaultPage's content stack.
PAGE_KEY = "producer_licensing"


class ProducerLicensingPlugin(PluginBase):
    """Producer Licensing — slice 1 application plugin."""

    @property
    def plugin_id(self) -> str:
        return "producer_licensing"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._page: ProducerLicensingPage | None = None
        self._nav_button: MenuButton | None = None

        # Build the page once at init time. The vault may not be open yet;
        # the page reads vault state lazily on _refresh().
        self._page = ProducerLicensingPage(
            app=app,
            manifest=PRODUCER_LICENSING,
            issuer_alias=ISSUER_ALIAS,
        )

        logger.info("ProducerLicensingPlugin initialized")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_vault_opened(self, vault: Any) -> None:
        """Ensure the schema is loaded and the registry exists on the issuer AID.

        If the issuer AID isn't present in this vault, the plugin stays inert —
        no error, just no setup. The page will reflect "not configured" status.
        """
        try:
            issuer_hab = self._find_issuer_hab(vault)
            if issuer_hab is None:
                logger.info(
                    f"ProducerLicensingPlugin: no '{ISSUER_ALIAS}' AID in vault "
                    f"'{vault.hby.name}', skipping schema/registry setup"
                )
                self._refresh_page_safe()
                return

            schema_path = self._schema_path()
            schema_bytes = schema_path.read_bytes()
            schema_said = self._schema_said(schema_bytes)

            schema_loaded = vault.hby.db.schema.get(keys=(schema_said,)) is not None
            registry_exists = vault.rgy.registryByName(schema_said) is not None

            if schema_loaded and registry_exists:
                logger.info(
                    f"ProducerLicensingPlugin: schema {schema_said} and registry "
                    f"already present for {issuer_hab.name}"
                )
                self._refresh_page_safe()
                return

            logger.info(
                f"ProducerLicensingPlugin: setting up schema={schema_loaded} "
                f"registry={registry_exists} for issuer {issuer_hab.name} ({issuer_hab.pre})"
            )

            doer = LoadSchemaDoer(
                app=self._app,
                file_path=str(schema_path),
                file_content=schema_bytes,
                create_registry=not registry_exists,
                issuer_aid=issuer_hab.pre if not registry_exists else None,
                signal_bridge=vault.signals if hasattr(vault, "signals") else None,
            )
            vault.extend([doer])

            # Wire a one-shot listener so the page refreshes when setup completes
            if hasattr(vault, "signals"):
                vault.signals.doer_event.connect(self._on_setup_event)

        except Exception:
            logger.exception("ProducerLicensingPlugin: on_vault_opened failed")

    def on_vault_closed(self, vault: Any) -> None:
        """Disconnect signal listeners. Nothing else to clean up for slice 1."""
        try:
            if hasattr(vault, "signals"):
                try:
                    vault.signals.doer_event.disconnect(self._on_setup_event)
                except (RuntimeError, TypeError):
                    pass  # not connected
        except Exception:
            logger.exception("ProducerLicensingPlugin: on_vault_closed failed")

    # ------------------------------------------------------------------
    # Menu / pages
    # ------------------------------------------------------------------

    def get_menu_entry(self) -> MenuButton:
        # Reusing the badge icon for now — slice 1 doesn't ship its own.
        return MenuButton(
            icon=QIcon(":/assets/material-icons/badge.svg"),
            label="Producer Licensing",
        )

    def get_menu_section(self) -> list[QWidget]:
        items: list[QWidget] = []

        items.append(BackButton(dark_mode=False))
        items.append(MenuSpacer(15))

        self._nav_button = MenuButton(
            icon=QIcon(":/assets/material-icons/badge.svg"),
            label="Overview",
        )
        self._nav_button.clicked.connect(self._on_nav_clicked)
        items.append(self._nav_button)

        return items

    def get_pages(self) -> dict[str, QWidget]:
        return {PAGE_KEY: self._page} if self._page is not None else {}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_nav_clicked(self, checked: bool = False) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            logger.warning("ProducerLicensingPlugin: vault_page not available")
            return
        vault_page._show_page(PAGE_KEY)
        if self._page is not None:
            self._page.on_show()

    def _on_setup_event(self, doer_name: str, event_type: str, data: dict) -> None:
        """Refresh the page when schema/registry setup completes."""
        if doer_name == "LoadSchemaDoer" and event_type == "schema_loaded" and data.get("success"):
            logger.info("ProducerLicensingPlugin: schema/registry setup complete")
            self._refresh_page_safe()

    def _refresh_page_safe(self) -> None:
        if self._page is not None:
            try:
                self._page._refresh()
            except Exception:
                logger.exception("ProducerLicensingPlugin: page refresh failed")

    def _find_issuer_hab(self, vault: Any):
        for hab_pre, hab in vault.hby.habs.items():
            if hab.name == ISSUER_ALIAS:
                return hab
        return None

    @staticmethod
    def _schema_path() -> Path:
        credential_def = PRODUCER_LICENSING.credentials[0]
        return Path(__file__).parent / credential_def.schema_path

    @staticmethod
    def _schema_said(schema_bytes: bytes) -> str:
        return json.loads(schema_bytes.decode("utf-8"))["$id"]
