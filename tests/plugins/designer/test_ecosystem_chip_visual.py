from locksmith.plugins.designer.widgets.ecosystem_chip import (
    CrossTemplateChip, EcosystemChip,
)


def test_ecosystem_chip_renders_tag_text(qapp):
    c = EcosystemChip("insurance")
    assert c.text() == "insurance"
    # Matches the rule-type chip family: light-grey pill, teal accent
    # text, bold font weight — so "ECOSYSTEM AFFINITY" and "I'M BOUND
    # BY" read as siblings rather than two different chip systems.
    ss = c.styleSheet()
    assert "#f6f7f9" in ss
    assert "#0e9488" in ss
    assert "font-weight:600" in ss


def test_cross_template_pairs_with(qapp):
    c = CrossTemplateChip(kind="pairs_with", target="state-doi")
    assert c.text() == "↔ pairs with state-doi"


def test_cross_template_forked_from(qapp):
    c = CrossTemplateChip(kind="forked_from", target="EKWa…HYxkLN")
    assert c.text() == "↪ forked from EKWa…HYxkLN"


def test_cross_template_unknown_kind_falls_back_to_target(qapp):
    c = CrossTemplateChip(kind="unknown", target="x")
    assert c.text() == "· x"
