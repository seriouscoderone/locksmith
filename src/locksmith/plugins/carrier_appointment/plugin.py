# -*- encoding: utf-8 -*-
"""
locksmith.plugins.carrier_appointment.plugin module

CarrierAppointmentPlugin — registers a sidebar entry, lens page, and
auto-loads the schema + creates the registry on the configured carrier
AID when a vault opens.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget
from keri import help

from locksmith.core.credentialing import LoadSchemaDoer
from locksmith.plugins.base import PluginBase
from locksmith.plugins.carrier_appointment.manifest import CARRIER_APPOINTMENT
from locksmith.plugins.carrier_appointment.pages import CarrierAppointmentPage
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer

logger = help.ogler.getLogger(__name__)

# Hardcoded for slice 2; a real deployment would resolve the carrier's AID
# via OOBI or via a registry of well-known carriers. Carriers are NOT proxies —
# they are real legal entities, so the alias is direct (no `-proxy-` segment).
ISSUER_ALIAS = "acme-insurance-ca"

PAGE_KEY = "carrier_appointment"


class CarrierAppointmentPlugin(PluginBase):
    """Carrier Appointment — slice 2 application plugin."""

    @property
    def plugin_id(self) -> str:
        return "carrier_appointment"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._page: CarrierAppointmentPage | None = None
        self._nav_button: MenuButton | None = None

        self._page = CarrierAppointmentPage(
            app=app,
            manifest=CARRIER_APPOINTMENT,
            issuer_alias=ISSUER_ALIAS,
        )

        logger.info("CarrierAppointmentPlugin initialized")

    def on_vault_opened(self, vault: Any) -> None:
        try:
            issuer_hab = self._find_issuer_hab(vault)
            if issuer_hab is None:
                logger.info(
                    f"CarrierAppointmentPlugin: no '{ISSUER_ALIAS}' AID in vault "
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
                    f"CarrierAppointmentPlugin: schema {schema_said} and registry "
                    f"already present for {issuer_hab.name}"
                )
                self._refresh_page_safe()
                return

            logger.info(
                f"CarrierAppointmentPlugin: setting up schema={schema_loaded} "
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

            if hasattr(vault, "signals"):
                vault.signals.doer_event.connect(self._on_setup_event)

        except Exception:
            logger.exception("CarrierAppointmentPlugin: on_vault_opened failed")

    def on_vault_closed(self, vault: Any) -> None:
        try:
            if hasattr(vault, "signals"):
                try:
                    vault.signals.doer_event.disconnect(self._on_setup_event)
                except (RuntimeError, TypeError):
                    pass
        except Exception:
            logger.exception("CarrierAppointmentPlugin: on_vault_closed failed")

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(
            icon=QIcon(":/assets/material-icons/badge.svg"),
            label="Carrier Appointment",
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

    def _on_nav_clicked(self, checked: bool = False) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            logger.warning("CarrierAppointmentPlugin: vault_page not available")
            return
        vault_page._show_page(PAGE_KEY)
        if self._page is not None:
            self._page.on_show()

    def _on_setup_event(self, doer_name: str, event_type: str, data: dict) -> None:
        if doer_name == "LoadSchemaDoer" and event_type == "schema_loaded" and data.get("success"):
            logger.info("CarrierAppointmentPlugin: schema/registry setup complete")
            self._refresh_page_safe()

    def _refresh_page_safe(self) -> None:
        if self._page is not None:
            try:
                self._page._refresh()
            except Exception:
                logger.exception("CarrierAppointmentPlugin: page refresh failed")

    def _find_issuer_hab(self, vault: Any):
        for hab_pre, hab in vault.hby.habs.items():
            if hab.name == ISSUER_ALIAS:
                return hab
        return None

    @staticmethod
    def _schema_path() -> Path:
        credential_def = CARRIER_APPOINTMENT.credentials[0]
        return Path(__file__).parent / credential_def.schema_path

    @staticmethod
    def _schema_said(schema_bytes: bytes) -> str:
        return json.loads(schema_bytes.decode("utf-8"))["$id"]
