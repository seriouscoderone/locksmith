from locksmith.plugins.designer.widgets.role_icon_badge import RoleIconBadge


def test_government_badge_uses_landmark_glyph(qapp):
    b = RoleIconBadge(kind="government")
    assert b.glyph_label.text() == "🏛️"
    assert "#0ABFB0" in b.styleSheet()


def test_individual_badge_uses_person_glyph(qapp):
    b = RoleIconBadge(kind="individual")
    assert b.glyph_label.text() == "👤"
    assert "#D97757" in b.styleSheet()


def test_unknown_kind_falls_back_to_question_mark(qapp):
    b = RoleIconBadge(kind="nonsense")
    assert b.glyph_label.text() == "❓"


def test_badge_size_param_overrides_default(qapp):
    big = RoleIconBadge(kind="government", size=64)
    assert big.height() == 64 and big.width() == 64
    small = RoleIconBadge(kind="government", size=32)
    assert small.height() == 32 and small.width() == 32
