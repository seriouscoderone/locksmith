from locksmith.plugins.designer.widgets.rail_filter_chip_bar import (
    RailFilterChipBar,
)


def test_renders_chips_with_counts(qapp):
    bar = RailFilterChipBar(
        chips=[("all", 7), ("prose", 2), ("predicate", 3)],
        active="all",
    )
    assert bar.chip_text("all") == "all (7)"
    assert bar.chip_text("prose") == "prose (2)"


def test_active_chip_dark_filled(qapp):
    bar = RailFilterChipBar(chips=[("all", 7), ("prose", 2)], active="all")
    style = bar._buttons["all"].styleSheet()
    assert "#1A1C20" in style


def test_clicking_chip_emits_filter_changed(qapp):
    bar = RailFilterChipBar(chips=[("all", 7), ("prose", 2)], active="all")
    received: list[str] = []
    bar.filter_changed.connect(lambda name: received.append(name))
    bar._buttons["prose"].click()
    assert received == ["prose"]
    assert bar.active_filter() == "prose"


def test_zero_count_chips_still_render(qapp):
    bar = RailFilterChipBar(chips=[("all", 0), ("validation", 0)], active="all")
    assert bar.chip_text("all") == "all (0)"
    assert bar.chip_text("validation") == "validation (0)"
