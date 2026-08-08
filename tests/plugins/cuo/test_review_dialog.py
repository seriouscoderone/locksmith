"""The read-back. Its whole job is showing what will be SIGNED, not what was typed.

`_build_payload` rewrites input -- lowercases the line, upper-cases coverages,
prefixes US- -- so the canonical values are the only honest thing to display. This
is also the only place a US-TU transposition can be caught: the jurisdiction is a
pattern, the EGF enumerates no subdivisions, so no validation can reject it.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

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


def test_a_second_click_cannot_emit_confirm_again(qtbot):
    """The hazard is a duplicate IMMUTABLE mandate -- there is no correcting one,
    only declaring another. Fire a real second click, not a second call to the
    private handler."""
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    button = dialog.findChild(QPushButton, "mandateReviewDialog.confirm")
    emitted = []
    dialog.confirm.connect(lambda: emitted.append(1))
    button.click()
    button.click()
    assert emitted == [1]
    assert button.isEnabled() is False
    assert button.text() == copy.IN_FLIGHT


def test_fail_reenables_the_primary_for_a_retry(qtbot):
    """A failed anchor attempt must leave the CUO able to retry, not stuck behind
    a permanently-disabled button that only ever said it was in flight."""
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    button = dialog.findChild(QPushButton, "mandateReviewDialog.confirm")
    button.click()
    assert dialog.confirmed() is True

    dialog.fail("boom")

    assert dialog.confirmed() is False
    assert button.isEnabled() is True
    assert button.text() == copy.REVIEW_CONFIRM


def test_thesis_with_markup_renders_literally_not_as_richtext(qtbot):
    """The thesis is free, unpatterned prose -- the one field most likely to
    contain '<', '>' or '&'. Left at Qt's default AutoText, a thesis that looks
    like markup renders AS markup: tags vanish and the text restyles, so the CUO
    would sign a string they never actually saw. `text()` alone would pass even
    while this is happening, so compare sizeHint against PlainText/RichText twins
    built with the label's OWN stylesheet -- a sizeHint mismatch is what dead-tag
    rendering actually looks like."""
    thesis = "Grow <b>teen-driver</b> share & focus on loss ratio <60% in Utah."
    payload = dict(_PAYLOAD, thesis=thesis)
    dialog = MandateReviewDialog(payload, signer_name="Dana Cole")
    qtbot.addWidget(dialog)

    thesis_label = dialog.findChild(QLabel, "mandateReviewDialog.thesis")
    assert thesis_label is not None
    assert thesis_label.text() == thesis

    plain_twin = QLabel(thesis)
    plain_twin.setWordWrap(True)
    plain_twin.setStyleSheet(thesis_label.styleSheet())
    plain_twin.setTextFormat(Qt.TextFormat.PlainText)

    rich_twin = QLabel(thesis)
    rich_twin.setWordWrap(True)
    rich_twin.setStyleSheet(thesis_label.styleSheet())
    rich_twin.setTextFormat(Qt.TextFormat.RichText)

    # Proves the fix: the dialog's own label matches a forced-plain twin.
    assert thesis_label.sizeHint() == plain_twin.sizeHint()
    # Proves the test can actually catch the regression: for THIS string, plain
    # and rich interpretation really do differ in size, so a label that fell
    # back to AutoText/RichText would fail the assertion above.
    assert plain_twin.sizeHint() != rich_twin.sizeHint()


def test_row_values_render_literally_even_if_upstream_patterns_ever_allow_markup(qtbot):
    """Defensive, not reactive: today's schema patterns for these fields exclude
    '<' and '>', but this module owns no rules and must not depend on another
    layer's patterns holding forever."""
    markup_value = "<b>auto</b>"
    payload = dict(_PAYLOAD, line_of_business=markup_value)
    dialog = MandateReviewDialog(payload, signer_name="Dana Cole")
    qtbot.addWidget(dialog)

    value_label = next(
        w for w in dialog.findChildren(QLabel) if w.text() == markup_value)

    plain_twin = QLabel(markup_value)
    plain_twin.setWordWrap(True)
    plain_twin.setStyleSheet(value_label.styleSheet())
    plain_twin.setTextFormat(Qt.TextFormat.PlainText)

    rich_twin = QLabel(markup_value)
    rich_twin.setWordWrap(True)
    rich_twin.setStyleSheet(value_label.styleSheet())
    rich_twin.setTextFormat(Qt.TextFormat.RichText)

    assert value_label.sizeHint() == plain_twin.sizeHint()
    assert plain_twin.sizeHint() != rich_twin.sizeHint()
