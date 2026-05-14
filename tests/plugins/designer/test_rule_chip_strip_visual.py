from locksmith.plugins.designer.widgets.rule_chip_strip import RuleChipStrip


def test_renders_chips_for_each_rule_ref(qapp):
    strip = RuleChipStrip(rule_refs=["solvency_minimum", "fit_and_proper"])
    assert strip.chip_texts() == ["solvency_minimum", "fit_and_proper"]


def test_pick_button_present_with_correct_label(qapp):
    strip = RuleChipStrip(rule_refs=[])
    assert strip.pick_button.text() == "+ Pick rule"


def test_empty_state_shows_only_pick_button(qapp):
    strip = RuleChipStrip(rule_refs=[])
    assert strip.chip_texts() == []
    assert strip.pick_button is not None


def test_chip_has_remove_x(qapp):
    strip = RuleChipStrip(rule_refs=["a_rule"])
    chip = strip._chips[0]
    assert "×" in chip.text()
