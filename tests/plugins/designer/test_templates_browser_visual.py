# -*- encoding: utf-8 -*-
"""Templates browser: structural + visual smoke test."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest

from locksmith.plugins.designer.editors.templates_browser import TemplatesBrowserPage


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def _grab(widget, name: str) -> Path:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pix = widget.grab()
    assert not pix.isNull()
    assert pix.save(str(path))
    return path


def test_browser_shows_seeded_templates(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    page.resize(1100, 800)
    page.show()
    qapp.processEvents()
    QTest.qWait(200)
    qapp.processEvents()

    assert page.card_count() == 4
    titles = page.card_titles()
    assert "Regulator Grants Carrier License" in titles
    assert "Carrier License Application" in titles
    assert "Broken Refs Demo" in titles
    assert "Untitled template" in titles
    _grab(page, "templates_browser_two_seeded")


def test_browser_empty_state(qapp, tmp_path):
    from locksmith.plugins.designer.store import TemplateStore
    empty = TemplateStore(root=tmp_path)
    page = TemplatesBrowserPage(store=empty)
    page.refresh()
    qapp.processEvents()
    assert page.card_count() == 0
    assert page.empty_state_visible() is True


def test_browser_emits_open_on_card_click(qapp, seeded_store):
    page = TemplatesBrowserPage(store=seeded_store)
    page.refresh()
    qapp.processEvents()
    received: list = []
    page.template_open_requested.connect(lambda ref: received.append(ref))
    page.click_first_card()
    qapp.processEvents()
    assert len(received) == 1
