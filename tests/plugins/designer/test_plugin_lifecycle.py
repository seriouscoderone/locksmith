# -*- encoding: utf-8 -*-
"""Lifecycle smoke tests for DesignerPlugin."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from locksmith.plugins.designer.plugin import DesignerPlugin
from locksmith.plugins.designer.keys import ALL_PAGE_KEYS


def test_plugin_id_is_designer(qapp):
    plugin = DesignerPlugin()
    assert plugin.plugin_id == "designer"


def test_get_pages_returns_all_page_keys(qapp):
    # initialize requires an app-like object; pass a stub
    class _App:
        pass

    plugin = DesignerPlugin()
    plugin.initialize(_App())
    pages = plugin.get_pages()
    for key in ALL_PAGE_KEYS:
        assert key in pages, f"Page {key} not registered"
