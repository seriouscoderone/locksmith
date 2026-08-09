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
    QLineEdit,
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


_HELD = {"line_of_business": "auto", "jurisdiction": "US-UT",
         "window_opens": "2027-06-01", "window_closes": "2027-12-31"}


def _vault_holding(*mandates, tel="iss"):
    """A reger shaped like the real one, for `existing_mandates`.

    Two details are load-bearing and were both missing from the first version of
    this fake:

    * `schms.get` HONOURS `keys`. Ignoring it made every assertion below pass for
      any value of `PRODUCT_MANDATE_SCHEMA_SAID` -- a mistyped pin would have read
      an empty registry, reported no mandates, and turned the overlap gate off
      with nothing failing.
    * credentials carry `said` and `regid`, so the TEL lookup that decides whether
      a mandate is withdrawn has something to look up.
    """
    from locksmith.plugins.cuo.page import PRODUCT_MANDATE_SCHEMA_SAID

    creds = {f"EMandate{i}": SimpleNamespace(
        sad={"a": attrs}, said=f"EMandate{i}", regid="ERegistry")
        for i, attrs in enumerate(mandates)}

    def schms_get(keys=None):
        wanted = keys[0] if isinstance(keys, (tuple, list)) else keys
        if wanted != PRODUCT_MANDATE_SCHEMA_SAID:
            return []
        return [SimpleNamespace(qb64=said) for said in creds]

    def creds_get(keys=None):
        wanted = keys[0] if isinstance(keys, (tuple, list)) else keys
        return creds.get(wanted)

    tever = SimpleNamespace(vcState=lambda said: SimpleNamespace(et=tel))
    reger = SimpleNamespace(
        schms=SimpleNamespace(get=schms_get),
        creds=SimpleNamespace(get=creds_get),
        tevers=SimpleNamespace(get=lambda regid: tever),
    )
    return SimpleNamespace(vault=SimpleNamespace(rgy=SimpleNamespace(reger=reger)))


def test_the_overlap_gate_reads_this_vault_s_own_mandates(qtbot):
    """`existing_mandates` is only useful if it reaches the validator. Nothing
    above proves the page passes it, because the fixture has no vault."""
    held = dict(_HELD)
    app = _vault_holding(held)
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


def test_the_registry_fake_honours_the_schema_key():
    """A guard on the guard. The first version of this fake was
    `get=lambda keys=None: [...]` -- it ignored `keys`, so every assertion in this
    file passed for ANY value of `PRODUCT_MANDATE_SCHEMA_SAID`. A mistyped pin
    reads an EMPTY registry, reports no mandates, and turns the overlap gate off
    with nothing failing anywhere."""
    from locksmith.plugins.cuo.page import PRODUCT_MANDATE_SCHEMA_SAID

    reger = _vault_holding(dict(_HELD)).vault.rgy.reger
    assert reger.schms.get(keys=(PRODUCT_MANDATE_SCHEMA_SAID,)) != []
    assert reger.schms.get(keys=("E" + "Z" * 43,)) == []


def test_a_withdrawn_mandate_no_longer_blocks_an_overlapping_window(qtbot):
    """`copy.WINDOW_OVERLAP` offers withdrawal as one of two remedies, and the
    spec keeps it deliberately named without a route (design §5.1). Enumerating
    `reger.schms` alone never stops reporting a withdrawn mandate -- a revocation
    is a TEL update event, so the credential itself stays in the registry forever
    (ACDC v1.1: the states of a dynamically-revocable ACDC "are either *issued*
    or *revoked*"). The CUO would withdraw the mandate, be told the same thing
    again, and have no way to tell the remedy had worked."""
    app = _vault_holding(dict(_HELD), tel="rev")
    parent = QWidget()
    qtbot.addWidget(parent)
    page = CuoMandatePage(app=app, parent=parent)
    assert page.existing_mandates() == []

    page.set_field("line_of_business", "auto")
    page.set_field("jurisdiction", "US-UT")
    page.set_field("coverages", ["BI"])
    page.set_field("window_opens", "2027-01-01")
    page.set_field("window_closes", "2027-12-31")
    page.set_field("thesis", "The overlapping mandate was withdrawn.")
    page.submit()
    assert page.review_dialog is not None, (
        "a withdrawn mandate must not block the window it used to occupy")


@pytest.mark.parametrize("ilk,blocks", [("iss", True), ("bis", True),
                                        ("rev", False), ("brv", False)])
def test_each_tel_event_type_keripy_can_report_is_classified(ilk, blocks, qtbot):
    """`iss`/`rev` are what a no-backer registry reports; `bis`/`brv` are the
    with-backers pair. Checking only `rev` would leave `brv` -- the one this
    ecosystem reaches the moment a registry gains a backer -- unclassified, and
    a withdrawn mandate would silently keep blocking."""
    app = _vault_holding(dict(_HELD), tel=ilk)
    parent = QWidget()
    qtbot.addWidget(parent)
    page = CuoMandatePage(app=app, parent=parent)
    assert bool(page.existing_mandates()) is blocks


def test_the_classified_ilks_are_exactly_the_ones_keripy_will_emit():
    """Pin the constant to the protocol rather than to my reading of it: keripy's
    `vdr.eventing.vcstate` REFUSES any other event type, so the four below are
    the complete input domain and "not revoked" is a sound reading of issued.
    Measured against keripy itself, so a keripy change fails here."""
    from keri.vdr.eventing import vcstate

    from locksmith.plugins.cuo.page import CuoMandatePage

    said = "E" + "A" * 43
    accepted = []
    for ilk in ("iss", "bis", "rev", "brv", "vcp", "ixn", ""):
        try:
            vcstate(vcpre=said, said=said, sn=0, ri=said, eilk=ilk,
                    a=dict(s=0, d=said))
        except ValueError:
            continue
        accepted.append(ilk)
    assert accepted == ["iss", "bis", "rev", "brv"], (
        f"keripy now accepts {accepted} as TEL event types; "
        "_REVOKED_TEL_ILKS classifies only a subset of that")
    assert set(CuoMandatePage._REVOKED_TEL_ILKS) <= set(accepted)
    assert set(accepted) - set(CuoMandatePage._REVOKED_TEL_ILKS) == {"iss", "bis"}


def test_an_unreadable_tel_keeps_the_mandate_in_the_gate(qtbot):
    """Fail toward warning, not toward silence. A TEL that cannot be read is not
    evidence of withdrawal, and dropping the mandate would turn the overlap gate
    off for exactly the vault whose registry is broken."""
    def boom(regid):
        raise RuntimeError("tel is gone")

    app = _vault_holding(dict(_HELD))
    app.vault.rgy.reger.tevers = SimpleNamespace(get=boom)
    parent = QWidget()
    qtbot.addWidget(parent)
    page = CuoMandatePage(app=app, parent=parent)
    assert page.existing_mandates() == [_HELD]


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


@pytest.mark.parametrize("measure", [640, 480])
def test_no_help_text_is_painted_over_its_own_control(qtbot, monkeypatch, measure):
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

    Run at a SECOND column measure as well, and not for symmetry: 640 happens to
    equal QWidget's own default width, so a label that is merely capped rather
    than given a width still measures its wrapped height correctly at 640 by
    coincidence. At 480 that coincidence is gone and the measurement has to be
    real.
    """
    from locksmith.plugins.cuo import page as page_module

    monkeypatch.setattr(page_module, "_COLUMN_WIDTH", measure)
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

        # `ux-patterns.md:300`: "Always above the field. Never to the left."
        # Asserted on POSITION, not on the order things were added: the field
        # label must be the first thing in the group and must end above the
        # control's top edge.
        heading = group.layout().itemAt(0).widget()
        assert isinstance(heading, QLabel), f"{name}'s group does not start with a label"
        assert copy.FIELD_LABEL[name] in heading.text(), name
        assert heading.y() + heading.height() <= control.widget.y(), (
            f"{name}'s label is not above its control")
        assert heading.x() <= control.widget.x(), f"{name}'s label sits beside it"

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
    column = page._controls["thesis"].widget.parentWidget().parentWidget()
    assert column.width() == measure
    assert page._controls["thesis"].widget.parentWidget().width() == measure
    paired = page._controls["window_opens"].widget.parentWidget().width()
    assert paired < measure // 2 + page_module._ROW_SPACING, (
        "the window's two ends share one row")
    shell.hide()


def test_a_schema_field_the_form_cannot_render_fails_loudly(page, monkeypatch):
    """A new required field with no control would be dropped from every payload
    and rejected by the mint with nothing the CUO could act on."""
    from locksmith.plugins.cuo import page as page_module

    monkeypatch.setattr(page_module.copy, "FIELD_ORDER", ("jurisdiction",))
    with pytest.raises(RuntimeError, match="FIELD_ORDER does not render"):
        CuoMandatePage(app=None)


# --- Round two: what the review found unpinned. Each of these guards a rule the
# --- plan states, and each was confirmed to go red when its behaviour is reverted.


_ALL_FIELDS = list(copy.FIELD_ORDER)

_SAMPLE = {
    "line_of_business": "auto",
    "jurisdiction": "US-UT",
    "coverages": ["BI"],
    "window_opens": "2027-01-01",
    "window_closes": "2027-12-31",
    "thesis": "One sentence of intent.",
}


def test_the_read_back_shows_the_payload_that_gets_anchored(page, monkeypatch):
    """The read-back's ONE job, and nothing pinned it.

    Design §4.2 makes this modal the only place a transposed jurisdiction can be
    caught -- the pattern accepts US-TU and the EGF enumerates no subdivisions --
    so if the dialog can be shown one payload while `_anchor` receives another,
    the whole defence is decorative. Handing the dialog a dict with the
    jurisdiction truncated left all 98 earlier tests green.
    """
    from locksmith.plugins.cuo import page as page_module

    shown = []
    real_dialog = page_module.MandateReviewDialog

    class Spy(real_dialog):
        def __init__(self, payload, signer_name, parent=None):
            shown.append(payload)
            super().__init__(payload, signer_name, parent=parent)

    monkeypatch.setattr(page_module, "MandateReviewDialog", Spy)

    _fill(page)
    anchored = []
    page._anchor = lambda payload: anchored.append(payload)
    page.submit()
    dialog = page.review_dialog
    dialog._on_confirm()

    assert len(shown) == 1 and len(anchored) == 1
    assert anchored[0] is shown[0], "the dialog and the anchor must share one dict"
    for field in copy.FIELD_ORDER:
        assert anchored[0][field] == shown[0][field], field

    # ...and what the dialog PAINTED is that payload, not something else again.
    painted = "\n".join(w.text() for w in dialog.findChildren(QLabel) if w.text())
    for field, value in anchored[0].items():
        for part in (value if isinstance(value, list) else [value]):
            assert str(part) in painted, f"{field}={part!r} was signed but not shown"


def test_keep_editing_drops_the_dialog_handle(page):
    """`review_dialog` is in the plan's contract, so it must not be a wrapper
    around a destroyed object: `is None` was False while `Shiboken.isValid` was
    False, and touching it raised."""
    from PySide6.QtWidgets import QPushButton

    _fill(page)
    page._anchor = lambda payload: None
    page.submit()
    assert page.review_dialog is not None
    page.review_dialog.findChild(QPushButton, "mandateReviewDialog.back").click()
    assert page.review_dialog is None
    page.submit()
    assert page.review_dialog is not None, "a second read-back must still open"


_DEVCTL_TYPED = [
    ("cuoMandatePage.jurisdiction", "US-UT", "jurisdiction", "US-UT"),
    ("cuoMandatePage.coverages", "BI,PD", "coverages", ["BI", "PD"]),
    ("cuoMandatePage.windowOpens", "01/01/2027", "window_opens", "2027-01-01"),
    ("cuoMandatePage.windowCloses", "12/31/2027", "window_closes", "2027-12-31"),
    ("cuoMandatePage.thesis", "Rate adequacy.", "thesis", "Rate adequacy."),
]


@pytest.mark.parametrize("name,text,field,expected", _DEVCTL_TYPED)
def test_every_driven_name_is_on_a_widget_devctl_can_write_to(
        page, name, text, field, expected):
    """Mirrors `locksmith_ui_tester`'s own `type` resolution, then writes.

    Moving a driven name onto its WRAPPER keeps `findChild(QWidget, name)`
    resolving, so the objectName assertions stay green while Task 8 breaks at
    runtime -- the wrapper exposes neither `setText` nor a public inner edit.
    """
    from PySide6.QtWidgets import QPlainTextEdit, QTextEdit

    widget = page.findChild(QWidget, name)
    assert widget is not None, name
    inner = (getattr(widget, "line_edit", None)
             or getattr(widget, "text_edit", None)
             or getattr(widget, "plain_text_edit", None))
    target = inner if isinstance(inner, (QLineEdit, QTextEdit, QPlainTextEdit)) else widget

    if isinstance(target, QPlainTextEdit):
        target.setPlainText(text)
    else:
        assert hasattr(target, "setText"), (
            f"{name} resolves to {type(target).__name__}, which devctl's `type` "
            f"cannot write to")
        target.setText(text)

    for control in page._controls.values():
        control.flush()
    assert page.build_payload()[field] == expected


def test_the_whole_object_name_contract_is_present_and_unambiguous(page):
    """Every name Task 8 drives, and exactly one widget per name."""
    required = {
        "cuoMandatePage.lineOfBusiness", "cuoMandatePage.jurisdiction",
        "cuoMandatePage.coverages", "cuoMandatePage.thesis",
        "cuoMandatePage.windowOpens", "cuoMandatePage.windowCloses",
        "cuoMandatePage.submit", "cuoMandatePage.errorBanner",
        "cuoMandatePage.declaredBanner",
    }
    found = {w.objectName() for w in page.findChildren(QWidget) if w.objectName()}
    assert required <= found, required - found
    assert "cuoMandatePage.effectiveWindow" not in found
    for name in required:
        hits = [w for w in page.findChildren(QWidget) if w.objectName() == name]
        assert len(hits) == 1, f"{name} resolves to {len(hits)} widgets"
    # The two that are not typed still have to be the KIND devctl expects.
    assert page.findChild(QComboBox, "cuoMandatePage.lineOfBusiness") is not None
    assert page.findChild(QLabel, "cuoMandatePage.errorBanner") is not None
    assert page.findChild(QLabel, "cuoMandatePage.declaredBanner") is not None


def test_the_page_does_not_de_duplicate_coverage_tokens(page, monkeypatch):
    """`uniqueItems` and `COVERAGE_DUPLICATE` are `validation.py`'s. A filter in
    the page was a second copy of that rule, and it swallowed the duplicate the
    CUO typed instead of letting them be told.

    (`LocksmithTextListWidget` keys its items by text, so the duplicate is still
    dropped one layer down -- toolkit code, outside this plan. This pins that the
    PAGE hands every token over, so the day that widget stops de-duplicating,
    validation gets its say.)
    """
    listing = page._controls["coverages"].widget
    handed = []
    real = listing.set_items
    monkeypatch.setattr(
        listing, "set_items",
        lambda items: (handed.append(list(items)), real(items))[1])
    _coverages_input(page).setText("BI,BI,")
    assert handed and handed[-1] == ["BI", "BI"]


def test_blurring_an_emptied_field_does_not_accuse_the_cuo(page):
    """Global Constraint 8: required errors fire on SUBMIT only. `blur_field`
    re-runs the whole validator, which returns required errors too."""
    page.submit()
    page.set_field("jurisdiction", "US-UT")
    page.blur_field("jurisdiction")
    assert page.field_error("jurisdiction") == ""

    page.set_field("jurisdiction", "")
    page.blur_field("jurisdiction")
    assert page.field_error("jurisdiction") == "", (
        "an empty field on blur is not yet an error")

    page.submit()
    assert page.field_error("jurisdiction") == copy.required_error("jurisdiction")


def test_the_error_banner_stops_offering_a_stale_message(page):
    """`LocksmithFormPage.clear_error` animates the banner shut but keeps the
    text, so its hover copy button went on offering "Fix 6 errors before signing."
    after the mandate was signed."""
    page.submit()
    assert page.error_label.text() == copy.error_summary(6)
    page.clear_error()
    assert page.error_label.text() == ""


def test_the_primary_stays_enabled_through_editing_and_a_failed_submit(page):
    """The deadlock guard again, at the moments it can regress: construction is
    the one state that was pinned."""
    submit = page.findChild(QWidget, "cuoMandatePage.submit")
    page.submit()
    assert submit.isEnabled() is True, "errors on screen must not lock the primary"
    page.set_field("jurisdiction", "US-UT")
    assert submit.isEnabled() is True
    page.blur_field("jurisdiction")
    assert submit.isEnabled() is True
    page.reset_form()
    assert submit.isEnabled() is True


def test_submit_is_refused_while_an_anchor_is_in_flight(page):
    _fill(page)
    page._anchor = lambda payload: None
    page.submit()
    first = page.review_dialog
    first._on_confirm()
    page.submit()
    assert page.review_dialog is first, (
        "a submit mid-flight must not open a second read-back")


def test_an_error_label_is_hidden_until_it_has_something_to_say(page):
    for name, control in page._controls.items():
        assert control.error.isHidden() is True, name
    page.submit()
    for name, control in page._controls.items():
        assert control.error.isHidden() is False, name
    page.reset_form()
    for name, control in page._controls.items():
        assert control.error.isHidden() is True, name


@pytest.mark.parametrize("name", _ALL_FIELDS)
def test_editing_any_control_clears_its_error_and_the_stale_said(page, name):
    """One test per field, because each control type wires its own `changed`
    signal -- and an unwired one fails silently."""
    page.submit()
    page.show_declared("E" + "A" * 43)
    banner = page.findChild(QLabel, "cuoMandatePage.declaredBanner")
    assert page.field_error(name) != ""
    page.set_field(name, _SAMPLE[name])
    assert page.field_error(name) == "", f"{name}'s changed signal is not wired"
    assert banner.text() == ""


@pytest.mark.parametrize("name", _ALL_FIELDS)
def test_every_control_is_marked_when_its_field_is_wrong(page, name):
    """Design §3.1: the control gets a red border. Per field, because each type
    paints differently and a no-op `paint` is invisible otherwise."""
    page.submit()
    widget = page._controls[name].widget
    sheets = [widget.styleSheet()] + [
        child.styleSheet() for child in widget.findChildren(QWidget)]
    assert any(colors.DANGER.lower() in sheet.lower() for sheet in sheets), name


def test_cancel_empties_every_control(page):
    _fill(page)
    page.reset_form()
    assert page.build_payload() == {
        "line_of_business": "", "jurisdiction": "", "coverages": [],
        "window_opens": "", "window_closes": "", "thesis": ""}


def test_field_order_not_the_schema_decides_the_sequence(qtbot, monkeypatch):
    """`FIELD_ORDER` is the authority (the schema's own key order is
    alphabetized). Today the two agree, so only a patched order can tell them
    apart -- and the form focuses the FIRST invalid field, so the order is not
    cosmetic."""
    from locksmith.plugins.cuo import page as page_module

    rotated = copy.FIELD_ORDER[3:] + copy.FIELD_ORDER[:3]
    monkeypatch.setattr(page_module.copy, "FIELD_ORDER", rotated)
    parent = QWidget()
    qtbot.addWidget(parent)
    page = CuoMandatePage(app=None, parent=parent)
    assert list(page._controls) == list(rotated)
    assert list(page.build_payload()) == list(rotated)


def test_a_failed_submit_focuses_and_scrolls_to_the_first_invalid_field(qtbot):
    """`ux-patterns.md:192`. The last field is below the fold at the window's own
    minimum height, so the scroll is load-bearing, not decorative."""
    shell = QWidget()
    qtbot.addWidget(shell)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    page = CuoMandatePage(app=None, parent=shell)
    layout.addWidget(page)
    shell.resize(1280, 700)
    shell.show()
    qtbot.waitExposed(shell)
    shell.activateWindow()

    for name, value in _SAMPLE.items():
        if name != "thesis":
            page.set_field(name, value)
    page.submit()
    qtbot.wait(50)

    thesis = page._controls["thesis"]
    assert page.field_error("thesis") != ""
    assert page.window().focusWidget() is thesis.focus_widget
    viewport = page.scroll_area.viewport()
    top = thesis.widget.mapTo(viewport, thesis.widget.rect().topLeft()).y()
    assert 0 <= top <= viewport.height(), (
        f"the first invalid field is off-screen at y={top} in a "
        f"{viewport.height()}px viewport")
    shell.hide()


def test_the_column_keeps_its_measure_in_a_narrow_window(qtbot):
    """"One bounded column, 640px" (design §3.1) -- bounded, not elastic. Capped
    with a maximum instead of fixed, it reflows and the labels rewrap."""
    from locksmith.plugins.cuo import page as page_module

    shell = QWidget()
    qtbot.addWidget(shell)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    page = CuoMandatePage(app=None, parent=shell)
    layout.addWidget(page)
    shell.resize(500, 900)            # narrower than the column itself
    shell.show()
    qtbot.waitExposed(shell)
    column = page._controls["thesis"].widget.parentWidget().parentWidget()
    assert column.width() == page_module._COLUMN_WIDTH
    shell.hide()
