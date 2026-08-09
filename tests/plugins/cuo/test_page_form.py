"""The form's behaviour, especially the parts that are easy to get backwards.

Timing is from ux-patterns.md:190-192 and is counter-intuitive: required errors
appear on SUBMIT, format errors on blur but only AFTER a first submit. That is why
the primary must stay ENABLED while the form is invalid -- a disabled button makes
the submit that reveals the errors unreachable.
"""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QComboBox, QLabel, QWidget

from locksmith.plugins.cuo import mandate_copy as copy
from locksmith.plugins.cuo.page import CuoMandatePage


@pytest.fixture
def page(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.app = SimpleNamespace(vault=None)
    p = CuoMandatePage(app=parent.app, parent=parent)
    qtbot.addWidget(p)
    yield p


def _labels(page) -> list[str]:
    return [w.text() for w in page.findChildren(QLabel) if w.text()]


def test_the_line_of_business_control_is_a_combo_from_the_schema(page):
    combo = page.findChild(QComboBox, "cuoMandatePage.lineOfBusiness")
    assert combo is not None, "the enum must render as a dropdown, not free text"
    assert combo.count() == 8
    assert combo.currentIndex() == -1, "no line may be pre-selected for the user"


def test_the_window_is_two_controls_not_one(page):
    assert page.findChild(QWidget, "cuoMandatePage.windowOpens") is not None
    assert page.findChild(QWidget, "cuoMandatePage.windowCloses") is not None
    assert page.findChild(QWidget, "cuoMandatePage.effectiveWindow") is None, (
        "one box holding two schema fields is the defect being removed")


def test_the_primary_is_enabled_while_the_form_is_empty(page):
    """The deadlock guard. Errors appear on submit, so submit must be reachable."""
    assert page.findChild(QWidget, "cuoMandatePage.submit").isEnabled() is True


def test_no_error_is_shown_before_the_first_submit(page):
    page.set_field("jurisdiction", "UTAH")
    page.blur_field("jurisdiction")
    assert page.field_error("jurisdiction") == ""


def test_submitting_an_empty_form_reports_every_required_field(page):
    page.submit()
    for field in ("line_of_business", "jurisdiction", "coverages",
                  "window_opens", "window_closes", "thesis"):
        assert page.field_error(field) != "", field
    assert copy.error_summary(6) in _labels(page)


def test_a_format_error_appears_on_blur_after_the_first_submit(page):
    page.submit()
    page.set_field("jurisdiction", "UTAH")
    page.blur_field("jurisdiction")
    assert copy.JURISDICTION_PATTERN in page.field_error("jurisdiction")


def test_the_payload_is_canonical_not_raw(page):
    page.set_field("line_of_business", "auto")
    page.set_field("jurisdiction", "ut")
    page.set_field("coverages", ["bi", "pd"])
    page.set_field("window_opens", "2027-01-01")
    page.set_field("window_closes", "2027-12-31")
    page.set_field("thesis", "Grow share.")
    payload = page.build_payload()
    assert payload["jurisdiction"] == "US-UT"
    assert payload["coverages"] == ["BI", "PD"]
    assert payload["window_opens"] == "2027-01-01"


def test_a_valid_form_opens_the_review_dialog_and_anchors_nothing_yet(page, qtbot):
    page.set_field("line_of_business", "auto")
    page.set_field("jurisdiction", "US-UT")
    page.set_field("coverages", ["BI"])
    page.set_field("window_opens", "2027-01-01")
    page.set_field("window_closes", "2027-12-31")
    page.set_field("thesis", "Grow share.")
    anchored = []
    page._anchor = lambda payload: anchored.append(payload)
    page.submit()
    assert page.review_dialog is not None
    assert anchored == [], "nothing may be signed before the read-back is confirmed"


def test_confirming_the_review_anchors_exactly_once_even_on_two_clicks(page):
    page.set_field("line_of_business", "auto")
    page.set_field("jurisdiction", "US-UT")
    page.set_field("coverages", ["BI"])
    page.set_field("window_opens", "2027-01-01")
    page.set_field("window_closes", "2027-12-31")
    page.set_field("thesis", "Grow share.")
    anchored = []
    page._anchor = lambda payload: anchored.append(payload)
    page.submit()
    dialog = page.review_dialog
    dialog._on_confirm()
    dialog._on_confirm()
    assert len(anchored) == 1, (
        "a second click must not mint a duplicate immutable mandate")


def test_the_success_banner_clears_when_editing_resumes(page):
    page.show_declared("E" + "A" * 43)
    banner = page.findChild(QLabel, "cuoMandatePage.declaredBanner")
    assert banner.isVisible() or banner.text()
    page.set_field("thesis", "A new one.")
    assert page.field_error("thesis") == ""
    assert not banner.text(), (
        "a stale SAID must not sit on screen while the next mandate is typed")


def test_the_full_said_is_shown_not_a_truncation(page):
    said = "E" + "A" * 43
    page.show_declared(said)
    assert said in " ".join(_labels(page))
