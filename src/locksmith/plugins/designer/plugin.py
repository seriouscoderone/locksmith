# -*- encoding: utf-8 -*-
"""
locksmith.plugins.designer.plugin module

DesignerPlugin — Locksmith plugin registering the Micro App: Designer
sidebar entry, its 10 pages, and the navigation among them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget
from keri import help

from locksmith.plugins.base import PluginBase
from locksmith.plugins.designer.crossref import compute_crossrefs
from locksmith.plugins.designer.db import DesignerBaser
from locksmith.plugins.designer.editors.aggregates import AggregatesEditorPage
from locksmith.plugins.designer.editors.commands import CommandsEditorPage
from locksmith.plugins.designer.editors.exports import ExportsEditorPage
from locksmith.plugins.designer.editors.imports import ImportsEditorPage
from locksmith.plugins.designer.editors.overview import TemplateOverviewPage
from locksmith.plugins.designer.editors.projections import ProjectionsEditorPage
from locksmith.plugins.designer.editors.reactions import ReactionsEditorPage
from locksmith.plugins.designer.editors.rules import RulesEditorPage
from locksmith.plugins.designer.editors.templates_browser import (
    TemplatesBrowserPage,
)
from locksmith.plugins.designer.editors.workflows import WorkflowsEditorPage
from locksmith.plugins.designer.keys import (
    PAGE_KEY_AGGREGATES, PAGE_KEY_COMMANDS, PAGE_KEY_EXPORTS, PAGE_KEY_IMPORTS,
    PAGE_KEY_OVERVIEW, PAGE_KEY_PROJECTIONS, PAGE_KEY_REACTIONS, PAGE_KEY_RULES,
    PAGE_KEY_TEMPLATES_BROWSER, PAGE_KEY_WORKFLOWS, PRIMITIVE_PAGE_KEY,
)
from locksmith.plugins.designer.model import TemplateModel
from locksmith.plugins.designer.store import TemplateStore
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer


logger = help.ogler.getLogger(__name__)


class DesignerPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "designer"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._db: DesignerBaser | None = None
        self._store: TemplateStore | None = None
        self._model: TemplateModel | None = None
        self._pages: dict[str, QWidget] = {}

        # Build a placeholder browser at initialize-time (before vault is
        # opened) so get_pages() always returns the full key set, which
        # VaultPage.register_page requires up-front.
        dummy_store = TemplateStore(root=Path("/tmp"))
        self._pages[PAGE_KEY_TEMPLATES_BROWSER] = TemplatesBrowserPage(store=dummy_store)
        for key in (
            PAGE_KEY_OVERVIEW, PAGE_KEY_COMMANDS, PAGE_KEY_AGGREGATES,
            PAGE_KEY_REACTIONS, PAGE_KEY_WORKFLOWS, PAGE_KEY_PROJECTIONS,
            PAGE_KEY_RULES, PAGE_KEY_IMPORTS, PAGE_KEY_EXPORTS,
        ):
            self._pages[key] = QWidget()  # replaced when a template is opened

        logger.info("DesignerPlugin initialized")

    def on_vault_opened(self, vault: Any) -> None:
        self._db = DesignerBaser(
            name=f"designer_{vault.hby.name}", reopen=True,
        )
        # Test-friendly override: callers can set
        # vault.plugin_state["designer.root_override"] to redirect the
        # template store away from the canonical keri base path.
        root = vault.plugin_state.get("designer.root_override")
        if root is None:
            root = Path.home() / "keri" / "dgnr"
            root.mkdir(parents=True, exist_ok=True)
        self._store = TemplateStore(root=Path(root))

        browser = TemplatesBrowserPage(store=self._store)
        browser.template_open_requested.connect(self._open_template)
        self._pages[PAGE_KEY_TEMPLATES_BROWSER] = browser
        browser.refresh()

        vault.plugin_state["designer"] = {
            "open_template_id": None,
            "model": None,
            "dirty": False,
        }

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        self._store = None
        self._model = None
        vault.plugin_state.pop("designer", None)

    def _refresh_browser(self) -> None:
        browser = self._pages[PAGE_KEY_TEMPLATES_BROWSER]
        if hasattr(browser, "refresh"):
            browser.refresh()

    def _open_template(self, ref) -> None:
        if self._store is None:
            return
        doc, _meta = self._store.load(ref)
        self._model = TemplateModel(doc)
        crossrefs = compute_crossrefs(doc)

        overview = TemplateOverviewPage(model=self._model)
        overview.drilldown_requested.connect(self._drilldown)
        self._pages[PAGE_KEY_OVERVIEW] = overview

        for key, cls in (
            (PAGE_KEY_COMMANDS, CommandsEditorPage),
            (PAGE_KEY_AGGREGATES, AggregatesEditorPage),
            (PAGE_KEY_REACTIONS, ReactionsEditorPage),
            (PAGE_KEY_WORKFLOWS, WorkflowsEditorPage),
            (PAGE_KEY_PROJECTIONS, ProjectionsEditorPage),
            (PAGE_KEY_RULES, RulesEditorPage),
            (PAGE_KEY_IMPORTS, ImportsEditorPage),
            (PAGE_KEY_EXPORTS, ExportsEditorPage),
        ):
            self._pages[key] = cls(model=self._model, crossrefs=crossrefs)

    def _drilldown(self, kind: str) -> None:
        page_key = PRIMITIVE_PAGE_KEY.get(kind)
        if page_key is None:
            return
        logger.info("Drilldown requested: %s → %s", kind, page_key)

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(
            icon=QIcon(":/assets/material-icons/drafts.svg"),
            label="Micro App Designer",
        )

    def get_menu_section(self) -> list[QWidget]:
        items: list[QWidget] = [BackButton(dark_mode=False), MenuSpacer(15)]
        items.append(MenuButton(
            icon=QIcon(":/assets/material-icons/drafts.svg"),
            label="Templates",
        ))
        return items

    def get_pages(self) -> dict[str, QWidget]:
        return dict(self._pages)
