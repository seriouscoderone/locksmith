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
