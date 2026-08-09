# -*- encoding: utf-8 -*-
"""A nullable date control: MM/DD/YYYY on screen, ISO in the payload.

Two problems Qt does not solve on its own:

1. `QDateEdit` always holds a date, so there is no natural "unset". Without an
   explicit empty state the form would submit whatever date the widget opened on
   and the user would never have chosen it. The empty state is Qt's
   `specialValueText` on `minimumDate` -- the documented idiom -- with the minimum
   set below every date a mandate could plausibly carry, so nothing a user could
   legitimately enter can collide with it (see `_EMPTY` below for why that has to
   be exact). `specialValueText` only changes what is painted, though -- Qt still
   treats the minimum as a real, steppable value, so leaving the empty state must
   additionally be guarded against arrow-key/wheel stepping (see
   `_SentinelGuardedDateEdit` below).
2. Display and payload formats differ ON PURPOSE. `MM/dd/yyyy` is what the suite's
   date standard specifies for display; the payload and the review read-back use
   ISO, because `format: date` is ISO and the read-back's job is to show exactly
   what will be signed.
"""
from __future__ import annotations

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import QDateEdit, QHBoxLayout, QWidget

from locksmith.ui import colors

_DISPLAY_FORMAT = "MM/dd/yyyy"
#: The empty sentinel. Year 1 -- NOT merely "an implausibly old year": `QDate`
#: itself can represent dates earlier still (e.g. `QDate(-1, 1, 1)` is valid, for
#: BCE years), so year 1 is not Qt's actual earliest representable date. What
#: matters here is narrower and is what's load-bearing: this sentinel sits below
#: every date a mandate could plausibly carry, and the field's range floor (see
#: `setDateRange` below) makes anything earlier than it unreachable through this
#: widget, so nothing enterable can ever collide with it.
#: `setMinimumDate` CLAMPS: any `setDate` earlier than the minimum is silently
#: pulled up to it. A sentinel at 1900-01-01 therefore turned 1752-09-14 into
#: 1900-01-01, which then compared equal to the sentinel, so a legitimately early
#: date read back as EMPTY and `iso_value()` returned "". Measured against real
#: PySide6. Anything above year 1 reintroduces that class of bug for some date
#: below it.
_EMPTY = QDate(1, 1, 1)
_MAX = QDate(9999, 12, 31)  # QDateEdit's own default ceiling; kept explicit below.


class _SentinelGuardedDateEdit(QDateEdit):
    """A `QDateEdit` that refuses to step away from the empty sentinel.

    `specialValueText` only changes what is painted at the minimum -- Qt still
    treats the minimum as a real, steppable value. Measured against real PySide6:
    with the field EMPTY and focused, one `Qt.Key_Up` (and, separately, one real
    `QWheelEvent`) silently produced `0001-02-01` -- a date the user never chose,
    on a form whose output is a permanent, publicly-readable credential.
    `QAbstractSpinBox.wheelEvent` itself dispatches through `stepBy`, so guarding
    `stepBy` alone (confirmed by direct probe) closes both the arrow-key and the
    wheel path; no separate `wheelEvent` override is needed.
    """

    def keyPressEvent(self, event) -> None:
        """A typed digit LEAVES the empty state deliberately, then types.

        `specialValueText` only changes what is PAINTED -- the line edit really
        holds that placeholder string, and `QDateTimeEdit`'s own validator rejects
        a digit inserted into it. So on a fresh form (the state every declaration
        starts in) the CUO typed the date, watched the text revert, and was then
        told the field is required; the calendar popup worked, which made it a
        dead end rather than a visible block. Measured on the assembled page:
        keying `03152028` into an empty field left `iso_value()` "" with the line
        edit reading `MM/DD/YYYY3152028`.

        Seeding a date and selecting the first section reproduces exactly what
        focus-in does to a field that already holds one, so the same keystrokes
        then produce the same date as the non-empty control (both `2028-03-15`,
        measured). Neither half is sufficient alone: seeding without selecting
        leaves the insertion invalid and the keystrokes are swallowed silently,
        and clearing the line edit instead of selecting behaves the same way.
        Both measured against real PySide6 6.10.3 -- do not "simplify" this to
        one call.

        Only digits do this. Arrow keys and the wheel still route through
        `stepBy`, which stays a no-op while empty.
        """
        if self.date() == _EMPTY and event.text()[:1].isdigit():
            self.setDate(QDate.currentDate())
            self.setSelectedSection(self.sectionAt(0))
        super().keyPressEvent(event)

    def stepBy(self, steps: int) -> None:
        """No-op while empty; normal once a date is chosen.

        `specialValueText` shows a placeholder at the minimum, but Qt still treats
        the minimum as a value: one Up-arrow or wheel-scroll on an empty field
        stepped to 0001-02-01 -- a date the user never chose, on a form whose output
        is a permanent public credential. Leaving the empty state must be a
        deliberate act: type digits, or use the calendar popup.
        """
        if self.date() == _EMPTY:
            return
        super().stepBy(steps)


class MandateDateField(QWidget):
    """A date input that can be empty. `iso_value()` is "" until one is chosen."""

    changed = Signal()

    def __init__(self, placeholder: str = _DISPLAY_FORMAT, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._edit = _SentinelGuardedDateEdit(self)
        self._edit.setDisplayFormat(_DISPLAY_FORMAT)
        self._edit.setCalendarPopup(True)
        # `setMinimumDate()` called on its own is silently re-clamped by Qt to its
        # built-in floor of 1752-09-14 (measured on PySide6 6.10.3) -- the call
        # appears to succeed (no error, no warning) but `minimumDate()` afterwards
        # still reads 1752-09-14, which would make THAT the real sentinel and
        # reintroduce the exact collision this field exists to prevent.
        # `setDateRange(min, max)` does not have that floor and actually honours
        # year 1. Both bounds must be set together this way, not via the
        # single-ended setters.
        self._edit.setDateRange(_EMPTY, _MAX)
        self._edit.setSpecialValueText(placeholder)
        self._edit.setDate(_EMPTY)
        self._paint(invalid=False)
        self._edit.dateChanged.connect(lambda _d: self.changed.emit())
        layout.addWidget(self._edit)

    def _paint(self, invalid: bool) -> None:
        """Match `LocksmithLineEdit` exactly: 6px radius, 12px padding, 14px text,
        and NO background-color -- that widget inherits the parent's via
        `_get_parent_background_color`, so specifying one here would make the two
        controls differ on any surface but the default one."""
        border = colors.DANGER if invalid else colors.BORDER
        self._edit.setStyleSheet(
            f"QDateEdit {{ border: 1px solid {border}; border-radius: 6px;"
            f" padding: 12px; font-size: 14px; color: {colors.TEXT_PRIMARY}; }}")

    def display_format(self) -> str:
        return self._edit.displayFormat()

    def is_empty(self) -> bool:
        return self._edit.date() == _EMPTY

    def iso_value(self) -> str:
        if self.is_empty():
            return ""
        return self._edit.date().toString("yyyy-MM-dd")

    def set_iso(self, value: str) -> None:
        parsed = QDate.fromString(value or "", "yyyy-MM-dd")
        self._edit.setDate(parsed if parsed.isValid() else _EMPTY)

    def clear(self) -> None:
        self._edit.setDate(_EMPTY)

    def set_invalid(self, invalid: bool) -> None:
        self._paint(invalid)
