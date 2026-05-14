from locksmith.plugins.designer.widgets.view_type_chip_picker import (
    ViewTypeChipPicker,
)


_ALL = ["table", "list", "cards", "kanban", "timeline", "summary"]


def test_renders_six_view_types(qapp):
    picker = ViewTypeChipPicker(active="table")
    assert picker.view_types() == _ALL


def test_active_chip_defaults(qapp):
    picker = ViewTypeChipPicker(active="cards")
    assert picker.active_view_type() == "cards"


def test_set_active_changes_state(qapp):
    picker = ViewTypeChipPicker(active="table")
    picker.set_active("kanban")
    assert picker.active_view_type() == "kanban"


def test_clicking_chip_emits_signal(qapp):
    picker = ViewTypeChipPicker(active="table")
    received: list[str] = []
    picker.view_type_changed.connect(lambda name: received.append(name))
    picker._buttons["list"].click()
    assert received == ["list"]
    assert picker.active_view_type() == "list"


def test_active_chip_uses_orange_color(qapp):
    picker = ViewTypeChipPicker(active="table")
    style = picker._buttons["table"].styleSheet()
    assert "#D97757" in style
