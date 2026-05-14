from locksmith.plugins.designer.widgets.first_person_card import (
    FacetEntry, FirstPersonCard,
)


def test_facet_label_is_uppercase_dominant_title(qapp):
    card = FirstPersonCard(
        framing="I ISSUE",
        kind_label="Issued credentials",
        count=1,
        entries=[FacetEntry(label="Carrier License",
                            qualifier="to carrier · 4 states · 1 schema")],
    )
    assert card.framing_label.text() == "I ISSUE"


def test_entries_include_qualifier_subline(qapp):
    card = FirstPersonCard(
        framing="I ISSUE",
        kind_label="Issued credentials",
        count=1,
        entries=[FacetEntry(label="Carrier License",
                            qualifier="to carrier · 4 states · 1 schema")],
    )
    text = card.entries_text()
    assert "Carrier License" in text
    assert "to carrier · 4 states · 1 schema" in text


def test_rule_type_chip_variant_replaces_entries(qapp):
    card = FirstPersonCard(
        framing="I'M BOUND BY",
        kind_label="Rules",
        count=7,
        entries=[],
        rule_type_counts={"prose": 2, "predicate": 3, "validation": 1,
                          "binding_link": 1},
    )
    chips_text = card.chips_text()
    assert "2 prose" in chips_text
    assert "3 predicates" in chips_text
    assert "1 validation" in chips_text
    assert "1 link" in chips_text


def test_empty_state_message(qapp):
    card = FirstPersonCard(
        framing="I HOLD",
        kind_label="Imported credentials",
        count=0,
        entries=[],
        empty_message="No imports — this role is the root authority for licenses",
    )
    assert "root authority" in card.entries_text()
