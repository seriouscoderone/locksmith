# -*- encoding: utf-8 -*-
"""
locksmith.plugins.designer.plugin module

DesignerPlugin — Locksmith plugin that registers the Micro App: Designer
sidebar entry and its 10 pages (Templates browser, Overview, 8 per-
primitive editors). See README.md for design.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget
from keri import help

from locksmith.plugins.base import PluginBase
from locksmith.plugins.designer.keys import (
    PAGE_KEY_TEMPLATES_BROWSER,
    PAGE_KEY_OVERVIEW,
    PAGE_KEY_COMMANDS,
    PAGE_KEY_AGGREGATES,
    PAGE_KEY_REACTIONS,
    PAGE_KEY_WORKFLOWS,
    PAGE_KEY_PROJECTIONS,
    PAGE_KEY_RULES,
    PAGE_KEY_IMPORTS,
    PAGE_KEY_EXPORTS,
)
from locksmith.ui.toolkit.widgets.buttons import BackButton
from locksmith.ui.vault.menu import MenuButton, MenuSpacer

logger = help.ogler.getLogger(__name__)


class DesignerPlugin(PluginBase):
    """Direct-manipulation authoring plugin for micro-app templates."""

    @property
    def plugin_id(self) -> str:
        return "designer"

    def initialize(self, app: Any) -> None:
        self._app = app
        self._db = None
        self._pages: dict[str, QWidget] = {}
        # Page widgets created lazily in subsequent tasks. For task 1
        # we register stub QWidgets so get_pages() returns the full key
        # set and downstream wiring tests can run.
        for key in (
            PAGE_KEY_TEMPLATES_BROWSER,
            PAGE_KEY_OVERVIEW,
            PAGE_KEY_COMMANDS,
            PAGE_KEY_AGGREGATES,
            PAGE_KEY_REACTIONS,
            PAGE_KEY_WORKFLOWS,
            PAGE_KEY_PROJECTIONS,
            PAGE_KEY_RULES,
            PAGE_KEY_IMPORTS,
            PAGE_KEY_EXPORTS,
        ):
            self._pages[key] = QWidget()
        logger.info("DesignerPlugin initialized (skeleton)")

    def on_vault_opened(self, vault: Any) -> None:
        # DB + page wiring filled in by subsequent tasks.
        pass

    def on_vault_closed(self, vault: Any, *, clear: bool = False) -> None:
        pass

    def get_menu_entry(self) -> MenuButton:
        return MenuButton(
            icon=QIcon(":/assets/material-icons/draft.svg"),
            label="Micro App Designer",
        )

    def get_menu_section(self) -> list[QWidget]:
        items: list[QWidget] = [BackButton(dark_mode=False), MenuSpacer(15)]
        items.append(MenuButton(
            icon=QIcon(":/assets/material-icons/draft.svg"),
            label="Templates",
        ))
        return items

    def get_pages(self) -> dict[str, QWidget]:
        return dict(self._pages)
