from locksmith.plugins.designer.widgets.validation_pill import ValidationPill


def test_valid_pill(qapp):
    pill = ValidationPill(error_count=0, warning_count=0)
    assert pill.text() == "✓ valid"
    assert "#eafaf0" in pill.styleSheet()


def test_warnings_only(qapp):
    pill = ValidationPill(error_count=0, warning_count=2)
    assert pill.text() == "⚠ 2 warnings"
    assert "#fdf3e7" in pill.styleSheet()


def test_errors_present_dominate_warnings(qapp):
    pill = ValidationPill(error_count=3, warning_count=2)
    assert pill.text() == "⛔ 3 errors"
    assert "#fce8ea" in pill.styleSheet()


def test_singular_count_grammar(qapp):
    p1 = ValidationPill(error_count=1, warning_count=0)
    assert p1.text() == "⛔ 1 error"
    p2 = ValidationPill(error_count=0, warning_count=1)
    assert p2.text() == "⚠ 1 warning"
