from locksmith.plugins.designer.widgets.validation_pill import ValidationPill


def test_valid_pill(qapp):
    pill = ValidationPill(error_count=0, warning_count=0)
    assert pill.text() == "Valid"
    # Background color is painted in paintEvent (not QSS) so check
    # the cached value the painter uses.
    assert pill._bg == "#eafaf0"


def test_warnings_only(qapp):
    pill = ValidationPill(error_count=0, warning_count=2)
    assert pill.text() == "Warning"
    assert pill._bg == "#fdf3e7"


def test_errors_present_dominate_warnings(qapp):
    pill = ValidationPill(error_count=3, warning_count=2)
    assert pill.text() == "Invalid"
    assert pill._bg == "#fce8ea"


def test_status_word_independent_of_count(qapp):
    p1 = ValidationPill(error_count=1, warning_count=0)
    assert p1.text() == "Invalid"
    p2 = ValidationPill(error_count=0, warning_count=1)
    assert p2.text() == "Warning"
