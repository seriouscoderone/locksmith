from PySide6.QtWidgets import QLabel

from locksmith.plugins.designer.widgets.kind_rail import RailItem
from locksmith.plugins.designer.widgets.primitive_editor_shell import (
    PrimitiveEditorShell,
)


def test_panel_and_json_toggle_buttons_exist(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T",
        items=[RailItem(id="a", label="a", kind_color="#888", has_errors=False)],
    )
    assert shell.panel_toggle is not None
    assert shell.json_toggle is not None
    assert "panel" in shell.panel_toggle.toolTip().lower() \
        or "validation" in shell.panel_toggle.toolTip().lower()
    assert "json" in shell.json_toggle.toolTip().lower()


def test_side_panel_hidden_by_default_then_toggles(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T",
        items=[RailItem(id="a", label="a", kind_color="#888", has_errors=False)],
    )
    side = QLabel("validation issues here")
    shell.set_side_panel(side)
    shell.show()
    qapp.processEvents()
    assert shell.side_panel_container.isVisible() is False
    shell.panel_toggle.click()
    qapp.processEvents()
    assert shell.side_panel_container.isVisible() is True
    shell.panel_toggle.click()
    qapp.processEvents()
    assert shell.side_panel_container.isVisible() is False


def test_bottom_panel_hidden_by_default_then_toggles(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T",
        items=[RailItem(id="a", label="a", kind_color="#888", has_errors=False)],
    )
    bottom = QLabel("json source view here")
    shell.set_bottom_panel(bottom)
    shell.show()
    qapp.processEvents()
    assert shell.bottom_panel_container.isVisible() is False
    shell.json_toggle.click()
    qapp.processEvents()
    assert shell.bottom_panel_container.isVisible() is True
    shell.json_toggle.click()
    qapp.processEvents()
    assert shell.bottom_panel_container.isVisible() is False


def test_set_side_panel_replaces_previous_widget(qapp):
    shell = PrimitiveEditorShell(
        surface_label="X", template_label="T", items=[],
    )
    first = QLabel("first")
    second = QLabel("second")
    shell.set_side_panel(first)
    shell.set_side_panel(second)
    layout = shell.side_panel_container.layout()
    assert layout.count() == 1
    assert layout.itemAt(0).widget() is second
