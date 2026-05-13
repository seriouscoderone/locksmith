# -*- encoding: utf-8 -*-
"""Structural + visual smoke test for PrimitiveEditorShell."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell, RailItem,
)


SHOTS_DIR = Path(__file__).resolve().parents[2] / "_screenshots" / "designer"


def _grab(widget, name: str) -> Path:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{name}.png"
    pix = widget.grab()
    assert not pix.isNull()
    assert pix.save(str(path))
    return path


def test_shell_renders_rail_items_and_default_pane(qapp):
    items = [
        RailItem(id="a", label="Item A", kind_color="#0ABFB0", has_errors=False),
        RailItem(id="b", label="Item B", kind_color="#0ABFB0", has_errors=True),
        RailItem(id="c", label="Item C", kind_color="#D97757", has_errors=False),
    ]
    shell = PrimitiveEditorShell(
        surface_label="Commands",
        template_label="Carrier License Application",
        items=items,
    )
    shell.resize(960, 720)
    shell.show()
    qapp.processEvents()
    QTest.qWait(200)
    qapp.processEvents()

    assert shell.rail_list.count() == 3
    assert shell.identity_label.text() == "Carrier License Application"
    assert shell.surface_label.text() == "Commands"

    _grab(shell, "shell_renders_rail")


def test_shell_selects_first_item_by_default(qapp):
    items = [RailItem(id="a", label="A", kind_color="#0ABFB0", has_errors=False)]
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T", items=items,
    )
    qapp.processEvents()
    assert shell.selected_item_id == "a"


def test_shell_emits_signal_on_item_click(qapp):
    items = [
        RailItem(id="a", label="A", kind_color="#0ABFB0", has_errors=False),
        RailItem(id="b", label="B", kind_color="#0ABFB0", has_errors=False),
    ]
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T", items=items,
    )
    received: list[str] = []
    shell.item_selected.connect(lambda iid: received.append(iid))
    shell.rail_list.setCurrentRow(1)
    qapp.processEvents()
    assert received == ["b"]
    assert shell.selected_item_id == "b"


def test_shell_set_right_pane_replaces_content(qapp):
    items = [RailItem(id="a", label="A", kind_color="#0ABFB0", has_errors=False)]
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T", items=items,
    )
    pane = QLabel("new content")
    shell.set_right_pane(pane)
    qapp.processEvents()
    assert shell.right_pane_container.layout().count() == 1


def test_cross_ref_strip_does_not_accumulate_stretches(qapp):
    from locksmith.plugins.designer.crossref import CrossRef
    from locksmith.plugins.designer.widgets.cross_ref_chip import CrossRefChipStrip

    strip = CrossRefChipStrip()
    ref = CrossRef(surface="commands", primitive_label="Do", primitive_path="/commands/0")

    # Refresh many times. Layout count should stabilize, not grow with each call.
    for _ in range(5):
        strip.set_refs((ref,))
    qapp.processEvents()
    counts_after_first_round = strip.layout().count()

    for _ in range(5):
        strip.set_refs((ref,))
    qapp.processEvents()
    counts_after_second_round = strip.layout().count()

    assert counts_after_first_round == counts_after_second_round, \
        "Layout item count grew across refresh cycles — stretch is leaking"
