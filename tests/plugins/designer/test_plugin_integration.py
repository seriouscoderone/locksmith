# -*- encoding: utf-8 -*-
"""DesignerPlugin: full integration smoke test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.plugin import DesignerPlugin
from locksmith.plugins.designer.keys import (
    PAGE_KEY_TEMPLATES_BROWSER, PAGE_KEY_OVERVIEW,
)
from locksmith.plugins.designer.editors.templates_browser import (
    TemplatesBrowserPage,
)
from locksmith.plugins.designer.editors.overview import TemplateOverviewPage


class _Hby:
    def __init__(self, name: str):
        self.name = name


class _Vault:
    def __init__(self, name: str, tmp_path: Path):
        self.hby = _Hby(name=name)
        self.plugin_state: dict = {}
        self.plugin_state["designer.root_override"] = tmp_path


class _App:
    pass


FIXTURES = Path(__file__).parent / "fixtures"


def test_plugin_opens_vault_and_lists_templates(qapp, tmp_path):
    plugin = DesignerPlugin()
    plugin.initialize(_App())
    vault = _Vault(name="testvault", tmp_path=tmp_path)
    plugin.on_vault_opened(vault)

    pages = plugin.get_pages()
    browser = pages[PAGE_KEY_TEMPLATES_BROWSER]
    assert isinstance(browser, TemplatesBrowserPage)

    store = plugin._store
    doc = json.loads((FIXTURES / "regulator-grants-carrier-license.json").read_text())
    store.save_registered(said=doc["d"], doc=doc, metadata={})

    browser.refresh()
    qapp.processEvents()
    QTest.qWait(100)
    assert browser.card_count() == 1

    plugin.on_vault_closed(vault)


def test_plugin_navigation_browser_to_overview(qapp, tmp_path):
    plugin = DesignerPlugin()
    plugin.initialize(_App())
    vault = _Vault(name="navvault", tmp_path=tmp_path)
    plugin.on_vault_opened(vault)
    doc = json.loads((FIXTURES / "regulator-grants-carrier-license.json").read_text())
    plugin._store.save_registered(said=doc["d"], doc=doc, metadata={})
    plugin._refresh_browser()
    qapp.processEvents()

    browser = plugin.get_pages()[PAGE_KEY_TEMPLATES_BROWSER]
    browser.click_first_card()
    qapp.processEvents()

    overview = plugin.get_pages()[PAGE_KEY_OVERVIEW]
    assert isinstance(overview, TemplateOverviewPage)
    assert overview.header_label_text() == "Regulator Grants Carrier License"

    plugin.on_vault_closed(vault)
