"""The read-back. Its whole job is showing what will be SIGNED, not what was typed.

`_build_payload` rewrites input -- lowercases the line, upper-cases coverages,
prefixes US- -- so the canonical values are the only honest thing to display. This
is also the only place a US-TU transposition can be caught: the jurisdiction is a
pattern, the EGF enumerates no subdivisions, so no validation can reject it.
"""
from PySide6.QtWidgets import QPushButton

from locksmith.plugins.cuo import mandate_copy as copy
from locksmith.plugins.cuo.review_dialog import MandateReviewDialog

_PAYLOAD = {
    "line_of_business": "auto",
    "jurisdiction": "US-UT",
    "coverages": ["BI", "PD"],
    "window_opens": "2027-01-01",
    "window_closes": "2027-12-31",
    "thesis": "Grow teen-driver share in Utah.",
}


def _text(dialog) -> str:
    from PySide6.QtWidgets import QLabel
    return "\n".join(w.text() for w in dialog.findChildren(QLabel) if w.text())


def test_every_canonical_value_is_shown(qtbot):
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    shown = _text(dialog)
    for value in ("auto", "US-UT", "BI", "PD", "Grow teen-driver share in Utah."):
        assert value in shown, value


def test_dates_are_shown_in_iso_not_month_day_year(qtbot):
    """The form displays MM/DD/YYYY; the read-back shows ISO on purpose, so it is
    byte-for-byte what goes into the credential."""
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    shown = _text(dialog)
    assert "2027-01-01" in shown and "2027-12-31" in shown
    assert "01/01/2027" not in shown


def test_the_signer_is_named(qtbot):
    """Nothing on the form today shows who is signing."""
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    assert "Dana Cole" in _text(dialog)


def test_the_caution_is_present_verbatim(qtbot):
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    assert copy.REVIEW_CAUTION in _text(dialog)


def test_it_starts_unconfirmed_and_confirms_on_the_primary(qtbot):
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    assert dialog.confirmed() is False
    button = dialog.findChild(QPushButton, "mandateReviewDialog.confirm")
    assert button is not None
    with qtbot.waitSignal(dialog.confirm, timeout=1000):
        button.click()
    assert dialog.confirmed() is True


def test_the_back_button_does_not_confirm(qtbot):
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    dialog.findChild(QPushButton, "mandateReviewDialog.back").click()
    assert dialog.confirmed() is False


def test_the_devctl_object_names_are_present(qtbot):
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    assert dialog.objectName() == "mandateReviewDialog"
    for name in ("mandateReviewDialog.summary", "mandateReviewDialog.caution"):
        assert dialog.findChild(object, name) is not None, name
