from locksmith.plugins.designer.widgets.ecosystem_chip import (
    CrossTemplateChip, EcosystemChip,
)


def test_ecosystem_chip_renders_tag_text(qapp):
    c = EcosystemChip("insurance")
    assert c.text() == "insurance"
    assert "#f0f2f5" in c.styleSheet()


def test_cross_template_pairs_with(qapp):
    c = CrossTemplateChip(kind="pairs_with", target="state-doi")
    assert c.text() == "↔ pairs with state-doi"


def test_cross_template_forked_from(qapp):
    c = CrossTemplateChip(kind="forked_from", target="EKWa…HYxkLN")
    assert c.text() == "↪ forked from EKWa…HYxkLN"


def test_cross_template_unknown_kind_falls_back_to_target(qapp):
    c = CrossTemplateChip(kind="unknown", target="x")
    assert c.text() == "· x"
