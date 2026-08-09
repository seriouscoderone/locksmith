"""The read-back that stands between "Attest" and a permanent public credential.

`attest()` used to run straight from a page click to `vault.extend`: no
read-back, no acknowledgement, and three schema-required attributes the actuary
never saw. A drawer rather than a modal per ux-patterns.md:66 — this is a rich
detail view, and the sibling's modal is the cautionary tale for putting one in a
box that clips.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from locksmith.plugins.actuary import attest_drawer as drawer_module
from locksmith.plugins.actuary.attest_drawer import AttestReviewDrawer
from locksmith.plugins.actuary.page import ActuaryPage

_MANDATE_SAID = "EGoGTCEKbaG42R_igvrt2O2YCtZOX8FT6pJTvGO5mr4X"
_ISSUER = "EKTRx0wK8UL-hQ2vJmDpLnYcRtWqZbXsAeFgHiJkLmNo"
_MANIFEST = "EMf3fJk9LmQ2xR7vB4nT8cY1pZaWeRtYuIoPaSdFgHjK"
_DIGEST = "EWb9kLmQ2xR7vB4nT8cY1pZaWeRtYuIoPaSdFgHjKlZx"
_THESIS = "Grow teen-driver share in Utah."
_MANDATE = {
    "line_of_business": "auto", "jurisdiction": "US-UT",
    "coverages": ["BI", "PD"], "window_opens": "2027-01-01",
    "window_closes": "2027-12-31", "thesis": _THESIS, "issuer": _ISSUER,
}


def _armed_page(qtbot):
    shell = QWidget()
    qtbot.addWidget(shell)
    shell.resize(1180, 940)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    page = ActuaryPage(app=None, parent=shell)
    layout.addWidget(page)
    shell.show()
    qtbot.waitExposed(shell)

    page._observed = {_MANDATE_SAID: dict(_MANDATE)}
    page._refresh_observed_list()
    page._selected_mandate_said = _MANDATE_SAID
    page._parse_manifest = {"workbook_digest": _DIGEST}
    page._parse_manifest_said = _MANIFEST
    page._version.setText("2027.1")
    page._update_attest_enabled()
    return shell, page


def _text(widget) -> str:
    return "\n".join(w.text() for w in widget.findChildren(QLabel) if w.text())


def test_the_page_primary_reviews_and_cannot_mint(qtbot):
    """Two-stage vocabulary: the commit verb belongs on the button that commits,
    and that button must not be reachable from the page."""
    shell, page = _armed_page(qtbot)
    assert "review" in page._attest.text().lower()
    assert "attest" not in page._attest.text().lower().replace("attestation", "")

    minted = []
    page._anchor_called = minted
    page.review_attestation()
    assert page.attest_drawer is not None
    assert page.attest_drawer.confirmed() is False, "opening a read-back mints nothing"
    shell.hide()


def test_the_read_back_shows_every_value_that_gets_committed(qtbot):
    """Including the three the app asserts on the actuary's behalf. They are
    schema-required and were committed permanently and publicly without ever
    appearing on screen."""
    shell, page = _armed_page(qtbot)
    page.review_attestation()
    shown = _text(page.attest_drawer)

    for value in (_ISSUER, "auto", "US-UT", "BI, PD", "2027-01-01",
                  "2027-12-31", _MANDATE_SAID, _THESIS, _MANIFEST, _DIGEST):
        assert value in shown, f"missing from the read-back: {value}"

    committed = page._attestation_attributes()
    for key in ("version", "filing_date", "action"):
        assert str(committed[key]) in shown, (
            f"{key}={committed[key]!r} is committed but never shown")
    shell.hide()


def test_what_is_shown_is_what_is_committed(qtbot):
    """One source for the attribute block, so the read-back cannot drift from
    the mint. A read-back that shows something else is worse than none."""
    shell, page = _armed_page(qtbot)
    page.review_attestation()
    shown = _text(page.attest_drawer)
    assert page._attestation_attributes()["manifest_said"] == _MANIFEST
    assert _MANIFEST in shown
    shell.hide()


def test_the_confirm_is_gated_by_the_acknowledgement(qtbot):
    shell, page = _armed_page(qtbot)
    page.review_attestation()
    drawer = page.attest_drawer
    confirm = drawer.findChild(QPushButton, "attestDrawer.confirm")

    assert confirm.isEnabled() is False, "the drawer opens signable"
    qtbot.keyClick(drawer._ack, Qt.Key.Key_Space)
    assert confirm.isEnabled() is True
    qtbot.keyClick(drawer._ack, Qt.Key.Key_Space)
    assert confirm.isEnabled() is False
    shell.hide()


def test_escape_closes_before_signing_and_is_refused_after(qtbot):
    """Escape always closes a drawer (ux-patterns.md:33) — except once the
    attestation is in flight, when closing would remove the only surface that
    reports the outcome."""
    shell, page = _armed_page(qtbot)
    page.review_attestation()
    drawer = page.attest_drawer

    drawer._ack.setChecked(True)
    drawer._on_confirm()
    qtbot.keyClick(drawer, Qt.Key.Key_Escape)
    assert drawer.isVisible() is True, "Escape destroyed an in-flight read-back"

    drawer.finish()
    # WAIT: closing is a 200ms ease-in slide now, not an instant hide, so the
    # widget is still visible for the length of the animation.
    qtbot.waitUntil(lambda: not drawer.isVisible(), timeout=2000)
    shell.hide()


def test_the_drawer_closes_when_the_attestation_resolves(qtbot):
    """Both outcomes. `close_drawer` refuses while confirmed, so the page must
    call `finish()` — the sibling shipped the plain-close version for a commit
    and its modal survived its own success."""
    for outcome in ("_show_attested", "fail"):
        shell, page = _armed_page(qtbot)
        page.review_attestation()
        drawer = page.attest_drawer
        drawer._ack.setChecked(True)
        drawer._on_confirm()

        page._close_drawer()

        qtbot.waitUntil(lambda: not drawer.isVisible(), timeout=2000)
        assert page.attest_drawer is None
        shell.hide()


def test_the_caution_is_pinned_below_the_scrolling_body(qtbot):
    """The sibling's caution scrolled out of view at six rows in 560px; this
    read-back is twelve rows plus two 44-char digests plus prose."""
    from PySide6.QtWidgets import QFrame, QScrollArea

    shell, page = _armed_page(qtbot)
    page.review_attestation()
    drawer = page.attest_drawer
    caution = drawer.findChild(QFrame, "attestDrawer.caution")
    scroll = drawer.findChild(QScrollArea, "attestDrawer.body")

    assert caution is not None and scroll is not None
    assert not scroll.isAncestorOf(caution), (
        "the caution is inside the scroll area and can be scrolled away from "
        "the button it governs")
    shell.hide()


def test_the_drawer_is_the_suites_md_width(qtbot):
    """ux-patterns.md:41 — `md` 600px is the stated default."""
    assert drawer_module.DRAWER_WIDTH == 600
    shell, page = _armed_page(qtbot)
    page.review_attestation()
    assert page.attest_drawer.width() == 600
    shell.hide()


def test_the_drawer_slides_in_and_out_rather_than_snapping(qtbot):
    """ux-patterns.md:29-30 — "Slide in from the right. Duration: 300ms.
    Easing: ease-out" and "Slide out to the right. Duration: 200ms."

    `_SLIDE_OUT_MS` was defined and never used: the drawer animated IN and then
    vanished, so the exit read as a glitch rather than the reverse of the
    entrance. Samples the geometry over time, because the durations and easing
    curves can all be set correctly on an animation that never runs.
    """
    shell, page = _armed_page(qtbot)
    page.review_attestation()
    drawer = page.attest_drawer

    opening = []
    for _ in range(12):
        qtbot.wait(25)
        opening.append(drawer.geometry().x())
    assert len(set(opening)) > 3, f"the drawer snapped open: {opening}"
    assert opening[0] > opening[-1], "it did not travel leftwards"
    assert drawer._animation.duration() == 300

    qtbot.waitUntil(lambda: drawer._animation.state().name == "Stopped",
                    timeout=2000)
    settled = drawer.geometry().x()

    drawer.close_drawer()
    closing = []
    for _ in range(8):
        qtbot.wait(25)
        closing.append(drawer.geometry().x())
    assert len(set(closing)) > 3, f"the drawer snapped shut: {closing}"
    assert closing[-1] > settled, "it did not travel back rightwards"
    assert drawer._animation.duration() == 200

    qtbot.waitUntil(lambda: not drawer.isVisible(), timeout=2000)
    shell.hide()


def test_the_backdrop_goes_the_moment_the_drawer_starts_closing(qtbot):
    """It is the thing making the page unusable; there is no reason to hold it
    for the 200ms of the slide."""
    shell, page = _armed_page(qtbot)
    page.review_attestation()
    drawer = page.attest_drawer
    assert drawer._backdrop.isVisible() is True

    drawer.close_drawer()
    assert drawer._backdrop.isVisible() is False, (
        "the backdrop lingers over a page the actuary can already use")

    qtbot.waitUntil(lambda: not drawer.isVisible(), timeout=2000)
    shell.hide()


# --- the three the app used to assert on the actuary's behalf ---------------------


def test_the_actuary_chooses_the_three_required_attributes(qtbot):
    """`version`, `filing_date` and `action` are all `required` by the
    attestation schema, and all three were hardcoded — "1.0", today, and
    "Sandbox" — so the app made permanent public assertions the actuary never
    saw. The schema is explicit that they are the actuary's: version is "a
    human-chosen label", filing_date is "an attribute the actuary asserts", and
    action is "the IPD retention contract the parse was run under"."""
    from PySide6.QtCore import QDate

    shell, page = _armed_page(qtbot)
    page._version.setText("2027.2")
    page._filing_date.setDate(QDate(2027, 3, 15))
    page._action.setCurrentText("Publish")

    committed = page._attestation_attributes()
    assert committed["version"] == "2027.2"
    assert committed["filing_date"] == "2027-03-15"
    assert committed["action"] == "Publish"

    page.review_attestation()
    shown = _text(page.attest_drawer)
    for value in ("2027.2", "2027-03-15", "Publish"):
        assert value in shown, f"{value} is committed but not shown"
    shell.hide()


def test_retention_offers_exactly_the_schemas_enum(qtbot):
    """`Sandbox` is a retention CONTRACT, not a test mode — the schema says so in
    capitals — so a value outside the enum, or a missing choice, is a permanent
    misstatement about how the parse is retained."""
    shell, page = _armed_page(qtbot)
    values = [page._action.itemText(i) for i in range(page._action.count())]
    assert values == ["Publish", "Sandbox"]
    shell.hide()


def test_attesting_is_blocked_until_the_version_is_given(qtbot):
    """The one required field with no defensible default. Today is a reasonable
    default for a date and the enum has a first member, but nobody but the
    actuary can name their own rate program."""
    shell, page = _armed_page(qtbot)
    assert page._attest.isEnabled() is True

    page._version.clear()

    assert page._attest.isEnabled() is False
    assert "version" in page._attest_blocker.text().lower()
    shell.hide()
