"""The form's behaviour, especially the parts that are easy to get backwards.

Timing is from ux-patterns.md:190-192 and is counter-intuitive: required errors
appear on SUBMIT, format errors on blur but only AFTER a first submit. That is why
the primary must stay ENABLED while the form is invalid -- a disabled button makes
the submit that reveals the errors unreachable.
"""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from locksmith.plugins.cuo import mandate_copy as copy
from locksmith.plugins.cuo.page import CuoMandatePage
from locksmith.ui import colors


@pytest.fixture
def page(qtbot):
    """A page under a parent that OUTLIVES the test.

    `yield`, not `return`: the fixture's frame is what holds the only reference
    to `parent`, and a collected parent takes its child page's C++ object with
    it -- every test then errored in pytest-qt's teardown with "Internal C++
    object (CuoMandatePage) already deleted". Measured; keep the yield.
    """
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


# --- Found by hand-driving the built page, not by the tests above -------------
# Each of these covers something a green run of the suite above could not see:
# a defect that shipped past it, a Qt behaviour it never exercises, or a
# contract another task depends on.


def _coverages_input(page):
    return page.findChild(QWidget, "cuoMandatePage.coverages").line_edit


def test_a_comma_commits_a_coverage_token(page):
    """`LocksmithTextListWidget` commits on Enter or the add button and knows
    nothing about commas -- measured. Task 8's integration helper fills this
    field by typing "BI,PD" in ONE write, so both halves must land."""
    _coverages_input(page).setText("BI,PD")
    listing = page._controls["coverages"].widget
    # The comma itself committed BI, live, leaving PD being typed.
    assert listing.get_items() == ["BI"]
    assert _coverages_input(page).text() == "PD"
    # ...and the token still being typed is not lost from the payload.
    assert page.build_payload()["coverages"] == ["BI", "PD"]
    page.submit()          # commits the pending token so the screen agrees
    assert listing.get_items() == ["BI", "PD"]
    assert _coverages_input(page).text() == ""


def test_setting_the_coverages_replaces_them_rather_than_merging(page):
    """The regression. `set_field` appended, so a second call merged into the
    first and `reset_form` cleared nothing at all."""
    page.set_field("coverages", ["BI"])
    page.set_field("coverages", ["PD"])
    assert page.build_payload()["coverages"] == ["PD"]
    page.reset_form()
    assert page.build_payload()["coverages"] == []


def test_an_invalid_border_survives_the_next_focus_change(page):
    """`LocksmithLineEdit` and friends REBUILD their whole stylesheet on focus
    in and out, so a red border painted with `setStyleSheet` is erased by the
    next click -- the error message would remain with no control marked."""
    page.submit()
    edit = page._controls["jurisdiction"].widget
    assert page.field_error("jurisdiction") != ""
    assert colors.DANGER.lower() in edit.styleSheet().lower()
    edit.focusInEvent(QFocusEvent(QEvent.Type.FocusIn))
    edit.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
    assert colors.DANGER.lower() in edit.styleSheet().lower()


def test_a_focus_out_is_what_actually_triggers_the_blur_check(page):
    """`blur_field` is public, but the CUO never calls it -- a focus change
    does. This pins the event filter that connects the two."""
    page.submit()
    page.set_field("jurisdiction", "UTAH")
    assert page.field_error("jurisdiction") == ""
    control = page._controls["jurisdiction"]
    QApplication.sendEvent(control.focus_widget,
                           QFocusEvent(QEvent.Type.FocusOut))
    assert copy.JURISDICTION_PATTERN in page.field_error("jurisdiction")


def test_the_declared_banner_is_hidden_until_a_mandate_exists(page, qtbot):
    """`wait_for cuoMandatePage.declaredBanner condition=visible` is how the
    integration arc knows the issuance finished. `LocksmithFormPage`'s own
    success banner collapses to zero height WITHOUT hiding, so `isVisible()`
    would stay true and that wait would return before anything was signed."""
    window = page.window()
    qtbot.addWidget(window)
    window.resize(900, 900)
    window.show()
    qtbot.waitExposed(window)
    banner = page.findChild(QLabel, "cuoMandatePage.declaredBanner")
    assert banner.isVisible() is False
    page.show_declared("E" + "A" * 43)
    assert banner.isVisible() is True
    page.set_field("thesis", "Editing resumes.")
    assert banner.isVisible() is False
    window.hide()


def test_the_overlap_gate_reads_this_vault_s_own_mandates(qtbot):
    """`existing_mandates` is only useful if it reaches the validator. Nothing
    above proves the page passes it, because the fixture has no vault."""
    held = {"line_of_business": "auto", "jurisdiction": "US-UT",
            "window_opens": "2027-06-01", "window_closes": "2027-12-31"}
    reger = SimpleNamespace(
        schms=SimpleNamespace(get=lambda keys=None: [SimpleNamespace(qb64="E1")]),
        creds=SimpleNamespace(get=lambda keys=None: SimpleNamespace(sad={"a": held})),
    )
    app = SimpleNamespace(vault=SimpleNamespace(rgy=SimpleNamespace(reger=reger)))
    parent = QWidget()
    qtbot.addWidget(parent)
    page = CuoMandatePage(app=app, parent=parent)
    assert page.existing_mandates() == [held]

    page.set_field("line_of_business", "auto")
    page.set_field("jurisdiction", "US-UT")
    page.set_field("coverages", ["BI"])
    page.set_field("window_opens", "2027-01-01")
    page.set_field("window_closes", "2027-12-31")
    page.set_field("thesis", "Overlapping on purpose.")
    page.submit()
    assert page.review_dialog is None, (
        "an overlapping window must not reach the read-back")
    assert "2027-06-01" in page.field_error("window_opens")


def test_an_unreadable_registry_is_advisory_not_fatal(qtbot):
    """The ledger enforces the real invariant; a local read that fails must not
    stop the CUO from declaring anything at all."""
    def boom(keys=None):
        raise RuntimeError("lmdb is gone")

    reger = SimpleNamespace(schms=SimpleNamespace(get=boom),
                            creds=SimpleNamespace(get=boom))
    app = SimpleNamespace(vault=SimpleNamespace(rgy=SimpleNamespace(reger=reger)))
    parent = QWidget()
    qtbot.addWidget(parent)
    page = CuoMandatePage(app=app, parent=parent)
    assert page.existing_mandates() == []


def _fill(page):
    page.set_field("line_of_business", "auto")
    page.set_field("jurisdiction", "ut")
    page.set_field("coverages", ["bi"])
    page.set_field("window_opens", "2027-01-01")
    page.set_field("window_closes", "2027-12-31")
    page.set_field("thesis", "One sentence of intent.")


def test_the_primary_disables_for_exactly_one_reason_an_anchor_in_flight(page):
    _fill(page)
    page._anchor = lambda payload: None
    page.submit()
    assert page.findChild(QWidget, "cuoMandatePage.submit").isEnabled() is True
    page.review_dialog._on_confirm()
    submit = page.findChild(QWidget, "cuoMandatePage.submit")
    assert submit.isEnabled() is False and submit.text() == copy.IN_FLIGHT


def test_a_failed_anchor_leaves_the_form_editable_and_says_why(page):
    """Design §4.3's Failed row: the modal closes, the typed values survive,
    and a retry is possible -- a one-shot guard that never re-armed would trap
    the CUO behind a permanently in-flight button."""
    _fill(page)
    page._anchor = lambda payload: None
    page.submit()
    page.review_dialog._on_confirm()
    page._fail_anchor("the mint refused")
    submit = page.findChild(QWidget, "cuoMandatePage.submit")
    assert page.review_dialog is None
    assert submit.isEnabled() is True and submit.text() == copy.FORM_PRIMARY
    assert page.error_label.text() == "the mint refused"
    assert page.build_payload()["thesis"] == "One sentence of intent."
    page.submit()
    assert page.review_dialog is not None, "the CUO must be able to retry"


def test_no_help_text_is_painted_over_its_own_control(qtbot):
    """Found by LOOKING at the rendered page; every assertion above passed while
    the help text sat on top of the control above it.

    A word-wrapped QLabel reports a one-line MINIMUM height however many lines it
    will paint, so the layout squeezed each field group ~40px below what it
    needed -- and Qt still honoured each control's own `setMinimumHeight(50)`, so
    the control painted over the help text beneath it. Measured at 1280x700 and
    1280x1024, with and without errors: a persistent 43px squeeze, 14px of
    overlap on the jurisdiction help and 37px on the thesis.

    Builds its own shell rather than using the `page` fixture, because that
    fixture's parent has NO layout: the page is never given a real geometry
    there, so any assertion about position or size would be vacuous.
    """
    shell = QWidget()
    qtbot.addWidget(shell)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    page = CuoMandatePage(app=None, parent=shell)
    layout.addWidget(page)
    shell.resize(1280, 700)           # the window's own minimum height
    shell.show()
    qtbot.waitExposed(shell)
    page.submit()                     # errors visible: the tallest state
    qtbot.wait(50)                    # let the relayout the errors trigger run

    for name, control in page._controls.items():
        group = control.widget.parentWidget()
        control_bottom = control.widget.y() + control.widget.height()
        for label in group.children():
            if not isinstance(label, QLabel) or not label.isVisible():
                continue
            if label.y() <= control.widget.y():
                continue              # the field label, above the control
            assert label.y() >= control_bottom, (
                f"{name}: {label.text()[:32]!r} starts at y={label.y()} but the "
                f"control runs to y={control_bottom}")
        assert group.height() >= group.sizeHint().height(), (
            f"{name} was squeezed: {group.height()} < {group.sizeHint().height()}")

    # "One bounded column, 640px" (design §3.1). Left to a maximum width and an
    # alignment flag the column takes its sizeHint instead -- measured at 546,
    # varying with the longest label.
    from locksmith.plugins.cuo import page as page_module

    column = page._controls["thesis"].widget.parentWidget().parentWidget()
    assert column.width() == page_module._COLUMN_WIDTH
    assert page._controls["thesis"].widget.parentWidget().width() == (
        page_module._COLUMN_WIDTH)
    paired = page._controls["window_opens"].widget.parentWidget().width()
    assert paired < page_module._COLUMN_WIDTH // 2 + page_module._ROW_SPACING, (
        "the window's two ends share one row")
    shell.hide()


def test_a_schema_field_the_form_cannot_render_fails_loudly(page, monkeypatch):
    """A new required field with no control would be dropped from every payload
    and rejected by the mint with nothing the CUO could act on."""
    from locksmith.plugins.cuo import page as page_module

    monkeypatch.setattr(page_module.copy, "FIELD_ORDER", ("jurisdiction",))
    with pytest.raises(RuntimeError, match="FIELD_ORDER does not render"):
        CuoMandatePage(app=None)
