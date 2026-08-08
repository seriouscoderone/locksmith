# -*- encoding: utf-8 -*-
"""A nullable date control: MM/DD/YYYY on screen, ISO in the payload.

Two problems Qt does not solve on its own:

1. `QDateEdit` always holds a date, so there is no natural "unset". Without an
   explicit empty state the form would submit whatever date the widget opened on
   and the user would never have chosen it. The empty state is Qt's
   `specialValueText` on `minimumDate` -- the documented idiom -- with the minimum
   set to the earliest date Qt can represent, so nothing a user could legitimately
   enter can collide with it (see `_EMPTY` below for why that has to be exact).
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
#: The empty sentinel. Year 1 -- Qt's earliest representable date -- NOT a merely
#: "implausibly old" year. `setMinimumDate` CLAMPS: any `setDate` earlier than the
#: minimum is silently pulled up to it. A sentinel at 1900-01-01 therefore turned
#: 1752-09-14 into 1900-01-01, which then compared equal to the sentinel, so a
#: legitimately early date read back as EMPTY and `iso_value()` returned "".
#: Measured against real PySide6. Anything above year 1 reintroduces that class of
#: bug for some date below it.
_EMPTY = QDate(1, 1, 1)
_MAX = QDate(9999, 12, 31)  # QDateEdit's own default ceiling; kept explicit below.


class MandateDateField(QWidget):
    """A date input that can be empty. `iso_value()` is "" until one is chosen."""

    changed = Signal()

    def __init__(self, placeholder: str = _DISPLAY_FORMAT, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._edit = QDateEdit(self)
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
