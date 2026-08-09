"""A date control that can be EMPTY, displays MM/DD/YYYY, and yields ISO.

QDateEdit always holds some date, so "the user has not chosen yet" needs an
explicit sentinel -- otherwise the form silently submits whatever date the widget
happened to open on, which is the class of defect the whole plan is closing.

Two formats is deliberate: MM/DD/YYYY in the form per the suite's date standard,
ISO in the payload and in the read-back, so the read-back shows byte-for-byte what
is signed.
"""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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


def test_an_up_arrow_on_an_empty_field_does_not_invent_a_date(qtbot):
    """Regression test: with the field EMPTY and focused, one Up-arrow silently
    produced 0001-02-01 -- a date the user never chose. Drives real key input
    rather than calling `stepBy` directly, because the defect arrived through the
    event system, not through the method in isolation."""
    field = MandateDateField()
    qtbot.addWidget(field)
    field.show()
    qtbot.waitExposed(field)
    QTest.keyClick(field._edit, Qt.Key_Up)
    assert field.is_empty() is True
    assert field.iso_value() == ""


def test_a_wheel_scroll_on_an_empty_field_does_not_invent_a_date(qtbot):
    """Same defect, the wheel path: `QAbstractSpinBox.wheelEvent` dispatches
    through `stepBy`, so a real `QWheelEvent` must be equally inert while empty."""
    field = MandateDateField()
    qtbot.addWidget(field)
    field.show()
    qtbot.waitExposed(field)
    event = QWheelEvent(
        QPointF(10, 10), QPointF(10, 10),
        QPoint(0, 0), QPoint(0, 120),
        Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
    )
    QApplication.sendEvent(field._edit, event)
    assert field.is_empty() is True
    assert field.iso_value() == ""


def test_stepping_still_works_once_a_date_is_chosen(qtbot):
    """The guard must not turn this into a read-only field."""
    field = MandateDateField()
    qtbot.addWidget(field)
    field.show()
    qtbot.waitExposed(field)
    field.set_iso("2027-06-15")
    QTest.keyClick(field._edit, Qt.Key_Up)
    assert field.iso_value() != "2027-06-15" and field.is_empty() is False


def test_setting_the_same_iso_value_does_not_emit_changed(qtbot):
    """A spurious emit would drive the form to validate before the user has acted,
    breaking the project's "no errors before the first submit" rule."""
    field = MandateDateField()
    qtbot.addWidget(field)
    field.set_iso("2027-06-15")
    with qtbot.assertNotEmitted(field.changed):
        field.set_iso("2027-06-15")


def test_clearing_an_already_empty_field_does_not_emit_changed(qtbot):
    field = MandateDateField()
    qtbot.addWidget(field)
    assert field.is_empty() is True
    with qtbot.assertNotEmitted(field.changed):
        field.clear()


# --- The keyboard. Every test above drives the field with set_iso/setText, which
# --- is exactly why a field nobody could TYPE into passed all of them.


def _typed(qtbot, seed_iso=None):
    """A shown, focused field after keying `03152028` the way a user does.

    Keys go to the QDateEdit, not to its line edit: the line edit's focus PROXY
    is the spinbox (measured), so real keystrokes arrive there. Sending them to
    the line edit instead only exercises QLineEdit's own insertion, which
    QDateTimeEdit's validator rejects -- a test that does that reports nothing
    about what a user experiences.
    """
    field = MandateDateField(placeholder="MM/DD/YYYY")
    qtbot.addWidget(field)
    field.show()
    qtbot.waitExposed(field)
    if seed_iso:
        field.set_iso(seed_iso)
        field._edit.setSelectedSection(field._edit.sectionAt(0))
    field._edit.setFocus()
    QTest.keyClicks(field._edit, "03152028")
    return field


def test_a_date_can_be_TYPED_into_an_empty_field(qtbot):
    """The state every declaration starts in.

    `specialValueText` leaves the placeholder in the line edit for real, and
    QDateTimeEdit's validator rejects a digit inserted into it -- so the CUO typed
    both required dates, watched the text revert, and was told the fields are
    required. Measured before the fix: `iso_value()` "" with the line edit reading
    `MM/DD/YYYY3152028`.
    """
    field = _typed(qtbot)
    assert field.iso_value() == "2028-03-15"
    assert field.is_empty() is False


def test_typing_into_an_empty_field_matches_typing_into_a_filled_one(qtbot):
    """The A/B that says the empty state is no longer special to the keyboard."""
    assert _typed(qtbot).iso_value() == _typed(qtbot, seed_iso="2027-05-05").iso_value()


def test_typing_a_date_emits_changed_so_the_form_hears_it(qtbot):
    field = MandateDateField(placeholder="MM/DD/YYYY")
    qtbot.addWidget(field)
    field.show()
    qtbot.waitExposed(field)
    seen = []
    field.changed.connect(lambda: seen.append(field.iso_value()))
    field._edit.setFocus()
    QTest.keyClicks(field._edit, "03152028")
    assert seen and seen[-1] == "2028-03-15"


def test_a_non_digit_key_does_not_drag_an_empty_field_out_of_the_empty_state(qtbot):
    """Only a digit is a deliberate act. Tab, backspace and letters are not."""
    for keys in ("\t", "\b", "abc"):
        field = MandateDateField(placeholder="MM/DD/YYYY")
        qtbot.addWidget(field)
        field.show()
        qtbot.waitExposed(field)
        field._edit.setFocus()
        QTest.keyClicks(field._edit, keys)
        assert field.iso_value() == "", keys


# --- the calendar POPUP, which inherits nothing from the field's stylesheet -----


def _open_popup(field, qtbot):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    field.resize(240, 46)
    field.show()
    qtbot.waitExposed(field)
    QTest.mouseClick(field._edit, Qt.MouseButton.LeftButton,
                     pos=QPoint(field._edit.width() - 10, field._edit.height() // 2))
    qtbot.waitUntil(lambda: field._edit.calendarWidget().isVisible(), timeout=2000)
    return field._edit.calendarWidget()


def test_an_empty_fields_picker_opens_on_today_not_on_the_sentinel(qtbot):
    """The popup syncs to `date()`, which is the year-1 empty sentinel -- so it
    opened on January of YEAR 1 and asked the CUO to page back two millennia.
    Measured on the built field: `yearShown()` was 1."""
    from PySide6.QtCore import QDate

    field = MandateDateField()
    qtbot.addWidget(field)
    cal = _open_popup(field, qtbot)
    today = QDate.currentDate()
    assert (cal.yearShown(), cal.monthShown()) == (today.year(), today.month())


def test_opening_the_picker_chooses_nothing_for_the_user(qtbot):
    """Navigating to today must not SELECT today. This form mints a permanent,
    publicly-readable credential; a date nobody picked must never become one."""
    field = MandateDateField()
    qtbot.addWidget(field)
    _open_popup(field, qtbot)
    assert field.is_empty() is True
    assert field.iso_value() == ""


def test_a_filled_fields_picker_still_opens_on_its_own_date(qtbot):
    """The today-page must not fight a date already chosen."""
    field = MandateDateField()
    qtbot.addWidget(field)
    field.set_iso("2027-06-15")
    cal = _open_popup(field, qtbot)
    assert (cal.yearShown(), cal.monthShown()) == (2027, 6)


def test_today_is_highlighted_even_though_it_is_not_selected(qtbot):
    """ux-patterns.md §19: "Always highlight today's date in the calendar, even
    when it is not the selected date." Weight and colour, never a filled cell --
    a fill is how the SELECTED day reads and the two must not be confusable."""
    from PySide6.QtCore import QDate
    from PySide6.QtGui import QFont

    from locksmith.ui import colors

    field = MandateDateField()
    qtbot.addWidget(field)
    cal = _open_popup(field, qtbot)
    fmt = cal.dateTextFormat(QDate.currentDate())
    assert fmt.fontWeight() >= QFont.Weight.Bold
    assert fmt.foreground().color().name().lower() == colors.PRIMARY.lower()


def test_no_day_of_the_week_is_coloured_like_an_error(qtbot):
    """Qt sets Saturday and Sunday to a literal #ff0000 QTextCharFormat
    foreground. That is a CHAR FORMAT, not a style rule, so no stylesheet touches
    it -- and in this system red is semantic (Error / Red #E74C3C: "Error states,
    validation failures"). A Saturday is neither an error nor destructive."""
    from PySide6.QtCore import Qt

    from locksmith.ui import colors

    field = MandateDateField()
    qtbot.addWidget(field)
    cal = _open_popup(field, qtbot)
    for day in Qt.DayOfWeek:
        shown = cal.weekdayTextFormat(day).foreground().color().name().lower()
        assert shown == colors.TEXT_PRIMARY.lower(), (
            f"{day.name} renders {shown}; all seven days must read the same")
        assert shown not in ("#ff0000", colors.DANGER.lower())
