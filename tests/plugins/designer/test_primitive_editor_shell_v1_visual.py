from PySide6.QtWidgets import QLabel

from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


def test_add_button_appears_above_rail_with_kind_label(qapp):
    shell = PrimitiveEditorShell(
        surface_label="Commands",
        template_label="Regulator Grants Carrier License",
        items=[RailItem(id="x", label="x", kind_color="#0ABFB0",
                        has_errors=False)],
        add_label="+ Add command",
    )
    assert shell.add_button.text() == "+ Add command"
    rail_panel_layout = shell.rail_list.parent().layout()
    assert rail_panel_layout.itemAt(0).widget() is shell.add_button
    assert rail_panel_layout.itemAt(1).widget() is shell.rail_list


def test_add_label_defaults_to_plain_add(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T",
        items=[], add_label=None,
    )
    assert shell.add_button.text() == "+ Add"


def test_breadcrumb_count_appears_after_surface_label(qapp):
    shell = PrimitiveEditorShell(
        surface_label="Commands",
        template_label="Regulator Grants Carrier License",
        items=[RailItem(id=f"c{i}", label=f"c{i}",
                        kind_color="#0ABFB0", has_errors=False)
               for i in range(4)],
        add_label="+ Add command",
        item_count=4,
        role_label="state-doi",
        is_valid=True,
    )
    assert shell.count_label.text() == "(4)"
    assert "state-doi" in shell.role_pill.text()
    assert "valid" in shell.valid_pill.text().lower()


def test_invalid_pill_shows_issue_count(qapp):
    shell = PrimitiveEditorShell(
        surface_label="Rules", template_label="X",
        items=[], add_label="+ Add rule",
        item_count=0, role_label="state-doi",
        is_valid=False, issue_count=3,
    )
    assert "3" in shell.valid_pill.text()
