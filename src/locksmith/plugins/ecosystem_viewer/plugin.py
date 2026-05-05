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
from locksmith.plugins.ecosystem_viewer.db import EcosystemBaser, EcosystemRecord
from locksmith.plugins.ecosystem_viewer.dialogs import (
    CreateEcosystemDialog,
    AddMemberDialog,
)
from locksmith.plugins.ecosystem_viewer.pages import (
    EcosystemViewerPage,
    SchemaDetailPage,
    EcosystemDetailPage,
    PAGE_KEY_OVERVIEW,
    PAGE_KEY_SCHEMA_DETAIL,
    PAGE_KEY_ECOSYSTEM_DETAIL,
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
        self._ecosystem_detail_page: EcosystemDetailPage | None = EcosystemDetailPage(app=app)
        self._nav_button: MenuButton | None = None

        # Wire intra-plugin navigation
        self._overview_page.show_schema_detail_requested.connect(self._show_schema_detail)
        self._overview_page.create_ecosystem_clicked.connect(self._open_create_ecosystem_dialog)
        self._schema_detail_page.back_requested.connect(self._show_overview)
        self._schema_detail_page.show_schema_detail_requested.connect(self._show_schema_detail)

        # Ecosystem detail page wiring
        self._overview_page.show_ecosystem_detail_requested.connect(self._show_ecosystem_detail)
        self._ecosystem_detail_page.back_requested.connect(self._show_overview)
        self._ecosystem_detail_page.show_schema_detail_requested.connect(self._show_schema_detail)
        self._ecosystem_detail_page.add_schema_clicked.connect(self._open_add_schema_dialog)
        self._ecosystem_detail_page.add_aid_clicked.connect(self._open_add_aid_dialog)
        self._ecosystem_detail_page.remove_schema_clicked.connect(self._remove_schema_member)
        self._ecosystem_detail_page.remove_aid_clicked.connect(self._remove_aid_member)
        self._ecosystem_detail_page.delete_ecosystem_clicked.connect(self._delete_ecosystem)

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
        if self._ecosystem_detail_page is not None:
            self._ecosystem_detail_page.set_db(self._db)

    def on_vault_closed(self, vault: Any) -> None:
        # Close per-vault DB on vault close
        if self._db is not None:
            self._db.close()
            self._db = None
        if self._overview_page is not None:
            self._overview_page.set_db(None)
        if self._schema_detail_page is not None:
            self._schema_detail_page.set_db(None)
        if self._ecosystem_detail_page is not None:
            self._ecosystem_detail_page.set_db(None)

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
        if self._ecosystem_detail_page is not None:
            pages[PAGE_KEY_ECOSYSTEM_DETAIL] = self._ecosystem_detail_page
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

    def _open_create_ecosystem_dialog(self) -> None:
        dialog = CreateEcosystemDialog(app=self._app, parent=self._overview_page)
        dialog.ecosystem_create_requested.connect(self._on_create_ecosystem)
        dialog.open()

    def _on_create_ecosystem(self, name: str, description: str) -> None:
        if self._db is None:
            logger.warning("EcosystemViewerPlugin: no DB open; cannot create ecosystem")
            return
        try:
            self._db.put_ecosystem(EcosystemRecord(name=name, description=description))
            logger.info(f"Ecosystem '{name}' created")
        except Exception:
            logger.exception("Failed to create ecosystem")
            return
        if self._overview_page is not None:
            self._overview_page.on_show()

    def _show_ecosystem_detail(self, name: str) -> None:
        vault_page = getattr(self._app, "_vault_page", None)
        if vault_page is None:
            logger.warning(f"EcosystemViewerPlugin: vault_page not available; cannot show ecosystem {name}")
            return
        vault_page._show_page(PAGE_KEY_ECOSYSTEM_DETAIL)
        if self._ecosystem_detail_page is not None:
            self._ecosystem_detail_page.show_ecosystem(name)

    def _open_add_schema_dialog(self, ecosystem_name: str) -> None:
        if self._db is None:
            return
        vault = getattr(self._app, "vault", None)
        if vault is None:
            return
        eco = self._db.get_ecosystem(ecosystem_name)
        if eco is None:
            return
        # Candidate schemas: every schema in the wallet not already in this ecosystem
        candidates: list[tuple[str, str]] = []
        try:
            for (said,), schemer in vault.hby.db.schema.getItemIter():
                if said in eco.schema_saids:
                    continue
                title = schemer.sed.get("title", "(untitled)")
                candidates.append((f"{title}  —  {said}", said))
        except Exception:
            logger.exception("Failed to enumerate schemas for member-add")

        dialog = AddMemberDialog(
            kind="schema",
            candidates=candidates,
            parent=self._ecosystem_detail_page,
        )
        dialog.member_picked.connect(
            lambda said, n=ecosystem_name: self._add_schema_member(n, said)
        )
        dialog.open()

    def _open_add_aid_dialog(self, ecosystem_name: str) -> None:
        if self._db is None:
            return
        vault = getattr(self._app, "vault", None)
        if vault is None:
            return
        eco = self._db.get_ecosystem(ecosystem_name)
        if eco is None:
            return
        candidates: list[tuple[str, str]] = []
        try:
            for c in vault.org.list():
                aid = c.get("id", "")
                if not aid or aid in eco.issuer_aids:
                    continue
                alias = c.get("alias") or "(no alias)"
                candidates.append((f"{alias}  —  {aid}", aid))
        except Exception:
            logger.exception("Failed to enumerate contacts for member-add")

        dialog = AddMemberDialog(
            kind="aid",
            candidates=candidates,
            parent=self._ecosystem_detail_page,
        )
        dialog.member_picked.connect(
            lambda aid, n=ecosystem_name: self._add_aid_member(n, aid)
        )
        dialog.open()

    def _add_schema_member(self, ecosystem_name: str, schema_said: str) -> None:
        if self._db is None:
            return
        try:
            self._db.add_schema_to_ecosystem(ecosystem_name, schema_said)
        except Exception:
            logger.exception("Failed to add schema to ecosystem")
            return
        self._refresh_ecosystem_detail()

    def _add_aid_member(self, ecosystem_name: str, aid: str) -> None:
        if self._db is None:
            return
        try:
            self._db.add_aid_to_ecosystem(ecosystem_name, aid)
        except Exception:
            logger.exception("Failed to add AID to ecosystem")
            return
        self._refresh_ecosystem_detail()

    def _remove_schema_member(self, ecosystem_name: str, schema_said: str) -> None:
        if self._db is None:
            return
        try:
            self._db.remove_schema_from_ecosystem(ecosystem_name, schema_said)
        except Exception:
            logger.exception("Failed to remove schema from ecosystem")
            return
        self._refresh_ecosystem_detail()

    def _remove_aid_member(self, ecosystem_name: str, aid: str) -> None:
        if self._db is None:
            return
        try:
            self._db.remove_aid_from_ecosystem(ecosystem_name, aid)
        except Exception:
            logger.exception("Failed to remove AID from ecosystem")
            return
        self._refresh_ecosystem_detail()

    def _delete_ecosystem(self, ecosystem_name: str) -> None:
        if self._db is None:
            return
        try:
            self._db.delete_ecosystem(ecosystem_name)
        except Exception:
            logger.exception("Failed to delete ecosystem")
            return
        self._show_overview()

    def _refresh_ecosystem_detail(self) -> None:
        if self._ecosystem_detail_page is not None and self._ecosystem_detail_page._current_name:
            self._ecosystem_detail_page.show_ecosystem(self._ecosystem_detail_page._current_name)
