"""Pins the Enter-to-add behavior of LocksmithTextListWidget.

Regression: line 69 of text_list.py was previously commented out, so typing
into the witness-prefix field of the Create Identifier dialog never committed
to the list — AIDs got created with empty witnesses. Verifies that Enter on
the inner QLineEdit invokes _add_item.
"""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from locksmith.ui.toolkit.widgets.text_list import LocksmithTextListWidget


def test_enter_key_commits_text(qapp):
    widget = LocksmithTextListWidget(label="Witness AID prefix")
    widget.text_input.setText("BE4B4CjpxNrCv8_HjLYvcwz-sui6AcJdygO-afEoTpmi")
    assert widget.get_items() == []

    QTest.keyClick(widget.text_input.line_edit, Qt.Key.Key_Return)

    assert widget.get_items() == [
        "BE4B4CjpxNrCv8_HjLYvcwz-sui6AcJdygO-afEoTpmi"
    ]
    assert widget.text_input.text() == ""


def test_add_button_still_works(qapp):
    widget = LocksmithTextListWidget(label="Witness AID prefix")
    widget.text_input.setText("AAA")
    widget.add_button.click()
    assert widget.get_items() == ["AAA"]
