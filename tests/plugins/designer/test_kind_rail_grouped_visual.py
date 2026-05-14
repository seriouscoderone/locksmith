from PySide6.QtCore import Qt

from locksmith.plugins.designer.widgets.kind_rail import KindRail, RailItem


def test_railitem_group_header_field_optional(qapp):
    rail = KindRail()
    rail.populate([
        RailItem(id="a", label="A", kind_color="#888", has_errors=False),
    ])
    item = rail.item(0)
    assert item.text() == "A"


def test_group_header_renders_as_non_selectable_separator(qapp):
    rail = KindRail()
    rail.populate([
        RailItem(id="grp1", label="", kind_color="", has_errors=False,
                 group_header="LEGAL PROSE"),
        RailItem(id="a", label="A", kind_color="#A36AE6", has_errors=False),
    ])
    header_item = rail.item(0)
    assert header_item.text() == "LEGAL PROSE"
    flags = header_item.flags()
    assert not (flags & Qt.ItemIsSelectable)
    a_item = rail.item(1)
    assert a_item.flags() & Qt.ItemIsSelectable
    assert rail.currentRow() == 1
