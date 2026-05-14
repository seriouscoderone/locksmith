from locksmith.plugins.designer.widgets.source_event_chip_strip import (
    SourceEventChipStrip,
)


def test_renders_chips_for_each_event(qapp):
    strip = SourceEventChipStrip(events=["license.issued", "license.revoked"])
    assert strip.chip_texts() == ["license.issued", "license.revoked"]


def test_pick_button_present_with_correct_label(qapp):
    strip = SourceEventChipStrip(events=[])
    assert strip.pick_button.text() == "+ Pick event"


def test_chip_has_remove_x(qapp):
    strip = SourceEventChipStrip(events=["license.issued"])
    chip = strip._chips[0]
    assert "×" in chip.text()


def test_chip_uses_purple_for_aggregate_event_semantics(qapp):
    strip = SourceEventChipStrip(events=["application_recorded"])
    chip = strip._chips[0]
    style = chip.styleSheet()
    assert "#A36AE6" in style or "#a36ae6" in style.lower()
