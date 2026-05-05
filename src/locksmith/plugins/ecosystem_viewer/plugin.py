# -*- encoding: utf-8 -*-
"""
locksmith.plugins.ecosystem_viewer.plugin module

EcosystemViewerPlugin — registers a sidebar entry that opens a viewer
into the wallet's known schemas, AIDs, and (planned) ecosystem groupings.
See README.md for design rationale and roadmap.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget
from keri import help

from locksmith.plugins.base import PluginBase
from locksmith.plugins.ecosystem_viewer.db import EcosystemBaser
from locksmith.plugins.ecosystem_viewer.pages import (
    EcosystemViewerPage,
    SchemaDetailPage,
    PAGE_KEY_OVERVIEW,
    PAGE_KEY_SCHEMA_DETAIL,
)
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer

logger = help.ogler.getLogger(__name__)


class EcosystemViewerPlugin(PluginBase):
    """Stages 1-2: domain-classified browsing of the wallet's known schemas + AIDs."""

    @property
    def plugin_id(self) -> str:
        return "ecosystem_viewer"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._db: EcosystemBaser | None = None
        self._overview_page: EcosystemViewerPage | None = EcosystemViewerPage(app=app)
        self._schema_detail_page: SchemaDetailPage | None = SchemaDetailPage(app=app)
        self._nav_button: MenuButton | None = None

        # Wire intra-plugin navigation
        self._overview_page.show_schema_detail_requested.connect(self._show_schema_detail)
        self._schema_detail_page.back_requested.connect(self._show_overview)
        self._schema_detail_page.show_schema_detail_requested.connect(self._show_schema_detail)

        logger.info("EcosystemViewerPlugin initialized (stages 1-3)")

    def on_vault_opened(self, vault: Any) -> None:
        # Open per-vault EcosystemBaser. Same pattern as KFBaser.
        self._db = EcosystemBaser(name=f"ecosystem_{vault.hby.name}", reopen=True)
        # Hand the DB reference to pages that need it
        if self._overview_page is not None:
            self._overview_page.set_db(self._db)
            self._overview_page.on_show()
        if self._schema_detail_page is not None:
            self._schema_detail_page.set_db(self._db)

    def on_vault_closed(self, vault: Any) -> None:
        # Close per-vault DB on vault close
        if self._db is not None:
            self._db.close()
            self._db = None
        if self._overview_page is not None:
            self._overview_page.set_db(None)
        if self._schema_detail_page is not None:
            self._schema_detail_page.set_db(None)

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
        self._nav_button.clicked.connect(self._show_overview)
        items.append(self._nav_button)
        return items

    def get_pages(self) -> dict[str, QWidget]:
        pages: dict[str, QWidget] = {}
        if self._overview_page is not None:
            pages[PAGE_KEY_OVERVIEW] = self._overview_page
        if self._schema_detail_page is not None:
            pages[PAGE_KEY_SCHEMA_DETAIL] = self._schema_detail_page
        return pages

    def _show_overview(self, *_args: Any) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            logger.warning("EcosystemViewerPlugin: vault_page not available; skipping overview navigation")
            return
        vault_page._show_page(PAGE_KEY_OVERVIEW)
        if self._overview_page is not None:
            self._overview_page.on_show()

    def _show_schema_detail(self, schema_said: str) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            logger.warning(f"EcosystemViewerPlugin: vault_page not available; cannot show schema {schema_said}")
            return
        vault_page._show_page(PAGE_KEY_SCHEMA_DETAIL)
        if self._schema_detail_page is not None:
            self._schema_detail_page.show_schema(schema_said)
