# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.plugin module

EcosystemViewerPlugin — registers a sidebar entry that opens a viewer
into the wallet's known schemas, AIDs, and (planned) ecosystem
groupings. See README.md for design rationale and roadmap.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget
from keri import help

from locksmith.plugins.base import PluginBase
from locksmith.plugins.ecosystem_viewer.pages import EcosystemViewerPage
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer

logger = help.ogler.getLogger(__name__)

PAGE_KEY = "ecosystem_viewer"


class EcosystemViewerPlugin(PluginBase):
    """Stage 1: domain-classified list of schemas + issuer AIDs in the wallet."""

    @property
    def plugin_id(self) -> str:
        return "ecosystem_viewer"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._page: EcosystemViewerPage | None = EcosystemViewerPage(app=app)
        self._nav_button: MenuButton | None = None
        logger.info("EcosystemViewerPlugin initialized")

    def on_vault_opened(self, vault: Any) -> None:
        # Stage 1 has no vault-specific setup. The page reads live from the
        # vault's stores when shown. EcosystemBaser will hook in here.
        if self._page is not None:
            self._page.on_show()

    def on_vault_closed(self, vault: Any) -> None:
        # No tear-down needed for stage 1.
        pass

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(
            icon=QIcon(":/assets/material-icons/schema.svg"),
            label="Ecosystem Viewer",
        )

    def get_menu_section(self) -> list[QWidget]:
        items: list[QWidget] = []

        items.append(BackButton(dark_mode=False))
        items.append(MenuSpacer(15))

        self._nav_button = MenuButton(
            icon=QIcon(":/assets/material-icons/schema.svg"),
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
            logger.warning("EcosystemViewerPlugin: vault_page not available")
            return
        vault_page._show_page(PAGE_KEY)
        if self._page is not None:
            self._page.on_show()
