"""A date control that can be EMPTY, displays MM/DD/YYYY, and yields ISO.

QDateEdit always holds some date, so "the user has not chosen yet" needs an
explicit sentinel -- otherwise the form silently submits whatever date the widget
happened to open on, which is the class of defect the whole plan is closing.

Two formats is deliberate: MM/DD/YYYY in the form per the suite's date standard,
ISO in the payload and in the read-back, so the read-back shows byte-for-byte what
is signed.
"""
from locksmith.plugins.cuo.date_field import MandateDateField


def test_a_fresh_field_is_empty_and_yields_no_value(qtbot):
    field = MandateDateField()
    qtbot.addWidget(field)
    assert field.is_empty() is True
    assert field.iso_value() == ""


def test_setting_an_iso_value_makes_it_non_empty(qtbot):
    field = MandateDateField()
    qtbot.addWidget(field)
    field.set_iso("2027-01-01")
    assert field.is_empty() is False
    assert field.iso_value() == "2027-01-01"


def test_the_display_format_is_month_day_year(qtbot):
    field = MandateDateField()
    qtbot.addWidget(field)
    assert field.display_format() == "MM/dd/yyyy"


def test_clearing_returns_it_to_empty(qtbot):
    field = MandateDateField()
    qtbot.addWidget(field)
    field.set_iso("2027-01-01")
    field.clear()
    assert field.is_empty() is True
    assert field.iso_value() == ""


def test_an_unparseable_value_leaves_the_field_empty(qtbot):
    field = MandateDateField()
    qtbot.addWidget(field)
    field.set_iso("not-a-date")
    assert field.is_empty() is True


def test_changing_the_value_emits_changed(qtbot):
    field = MandateDateField()
    qtbot.addWidget(field)
    with qtbot.waitSignal(field.changed, timeout=1000):
        field.set_iso("2027-03-04")


def test_the_empty_sentinel_is_not_a_date_a_user_could_pick(qtbot):
    """The sentinel must be unreachable by normal use, or a real date would read
    as empty. Regression test: `QDateEdit.setMinimumDate` CLAMPS rather than
    merely marking, so a sentinel later than this date (e.g. 1900-01-01) would
    silently pull 1752-09-14 up to itself and misread it as empty."""
    field = MandateDateField()
    qtbot.addWidget(field)
    field.set_iso("1752-09-14")
    assert field.iso_value() == "1752-09-14", (
        "an early but legitimate date must not collide with the empty sentinel")


def test_the_sentinel_is_the_minimum_so_no_real_date_can_be_clamped_onto_it(qtbot):
    """`setMinimumDate` clamps, so the sentinel must sit below every representable
    date a user could enter. Asserting the relationship, not one example date."""
    field = MandateDateField()
    qtbot.addWidget(field)
    for iso in ("0001-01-02", "1000-06-15", "1752-09-14", "1900-01-01", "2027-01-01"):
        field.set_iso(iso)
        assert field.iso_value() == iso, f"{iso} was clamped or lost"
        assert field.is_empty() is False, f"{iso} read back as empty"
