from locksmith.plugins.designer.widgets.type_color_badge import TypeColorBadge


def test_predicate_badge_uses_teal(qapp):
    b = TypeColorBadge("predicate")
    assert b.text() == "PREDICATE"
    assert "#0ABFB0" in b.styleSheet()


def test_legal_prose_renders_two_word_uppercase(qapp):
    b = TypeColorBadge("legal_prose")
    assert b.text() == "LEGAL PROSE"
    assert "#A36AE6" in b.styleSheet()


def test_validation_uses_orange(qapp):
    b = TypeColorBadge("validation")
    assert b.text() == "VALIDATION"
    assert "#D97757" in b.styleSheet()


def test_binding_link_uses_grey(qapp):
    b = TypeColorBadge("binding_link")
    assert b.text() == "BINDING LINK"
    assert "#666" in b.styleSheet() or "#666666" in b.styleSheet()


def test_unknown_type_falls_back_to_neutral(qapp):
    b = TypeColorBadge("mystery_kind")
    assert b.text() == "MYSTERY KIND"
    assert "#888" in b.styleSheet() or "#888888" in b.styleSheet()
