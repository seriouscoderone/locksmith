from PySide6.QtCore import Qt

from locksmith.plugins.designer.widgets.kind_rail import KindRail, RailItem


def test_railitem_subtitle_renders_as_two_line_text(qapp):
    rail = KindRail()
    rail.populate([
        RailItem(id="a", label="grant_license",
                 subtitle="→ carrier · 2 emissions",
                 kind_color="#0ABFB0", has_errors=False),
    ])
    item = rail.item(0)
    assert "grant_license" in item.text()
    assert "→ carrier · 2 emissions" in item.text()
    assert "\n" in item.text()


def test_railitem_subtitle_optional(qapp):
    rail = KindRail()
    rail.populate([
        RailItem(id="b", label="solo", subtitle=None,
                 kind_color="#888", has_errors=False),
    ])
    item = rail.item(0)
    assert item.text() == "solo"
    assert "\n" not in item.text()
