"""The read-back. Its whole job is showing what will be SIGNED, not what was typed.

`_build_payload` rewrites input -- lowercases the line, upper-cases coverages,
prefixes US- -- so the canonical values are the only honest thing to display. This
is also the only place a US-TU transposition can be caught: the jurisdiction is a
pattern, the EGF enumerates no subdivisions, so no validation can reject it.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

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


def _ack(dialog):
    """Tick the acknowledgement, which now gates the primary.

    A helper rather than a fixture: several tests below assert on the state
    BEFORE it is given, so the ticking has to be explicit and visible at each
    call site.
    """
    dialog._ack.setChecked(True)
    return dialog


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
    assert button.isEnabled() is False, "the primary must start un-signable"
    _ack(dialog)
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
    _ack(dialog)
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
    _ack(dialog)
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


# --- The friction is the point. A confirmation modal that a stray keystroke can
# --- resolve, or that poisons every later dialog, is worse than none.


def test_the_irreversible_primary_is_neither_the_default_nor_focused(qtbot):
    """`LocksmithDialog._build_button_section` makes the LAST LocksmithButton in
    the row the default and focuses it, and the primary is last -- so a single
    Return keystroke on an UNREAD read-back anchored a permanent, publicly
    readable credential. Measured before the fix."""
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    confirm = dialog.findChild(QPushButton, "mandateReviewDialog.confirm")
    back = dialog.findChild(QPushButton, "mandateReviewDialog.back")
    assert confirm.isDefault() is False and confirm.autoDefault() is False
    assert back.isDefault() is True
    # Opening focus is now the acknowledgement, not "Keep editing":
    # ux-patterns.md:426 puts it on the first interactive element. The property
    # this test exists for is unchanged and asserted above -- the irreversible
    # primary is neither the default nor focused.
    assert dialog.focusWidget() is dialog._ack
    assert dialog.focusWidget() is not confirm


def test_one_return_keystroke_does_not_sign(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    # The dialog is owned by a host that qtbot cleans up, and is NOT registered
    # itself: Return activates "Keep editing", which closes it, and a teardown
    # that closes an already-destroyed dialog reports a RuntimeError against
    # whatever test runs next instead of against the behaviour under test.
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(900, 700)
    host.show()
    qtbot.waitExposed(host)
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole", parent=host)
    dialog.show()
    emitted = []
    dialog.confirm.connect(lambda: emitted.append(1))
    QTest.keyClick(dialog, Qt.Key.Key_Return)
    # Asserted on the SIGNAL only: Return now activates "Keep editing", which
    # closes (and Qt destroys) the dialog, so touching it afterwards would be
    # reporting on a deleted object rather than on the behaviour.
    assert emitted == [], "Return on the read-back must not sign anything"


def test_keep_editing_does_not_poison_every_later_dialog(qtbot, monkeypatch):
    """"Keep editing" used to route to `reject()`, which `WA_DeleteOnClose`
    destroys WITHOUT running `closeEvent` -- and `closeEvent` is the only place
    `LocksmithDialog` clears its CLASS-level `_current_dialog`. The dangling
    pointer then made every later dialog's `showEvent` raise, anywhere in the
    process. Measured: the next `open()` raised
    `RuntimeError: Internal C++ object (MandateReviewDialog) already deleted`.

    `_current_dialog` is class state shared by the whole app, so it is reset here
    on both sides -- otherwise this test either inherits a leak or leaves one, and
    in both cases it reports on the wrong dialog.
    """
    from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog

    monkeypatch.setattr(LocksmithDialog, "_current_dialog", None, raising=False)
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(900, 700)
    host.show()
    qtbot.waitExposed(host)

    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole", parent=host)
    dialog.open()
    assert LocksmithDialog._current_dialog is dialog, (
        "precondition: an open dialog registers itself, or this proves nothing")

    dialog.findChild(QPushButton, "mandateReviewDialog.back").click()
    assert LocksmithDialog._current_dialog is None, (
        "a closed dialog must not stay registered as the current one")

    second = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole", parent=host)
    qtbot.addWidget(second)
    second.open()                      # raised before the fix
    assert second.isVisible()
    second.close()
    host.hide()


def test_keep_editing_is_refused_once_signing_has_started(qtbot):
    """Clicking back mid-flight destroyed the modal while the issuance carried
    on, leaving nothing to report success or failure on."""
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    back = dialog.findChild(QPushButton, "mandateReviewDialog.back")
    assert back.isEnabled() is True
    _ack(dialog)
    dialog.findChild(QPushButton, "mandateReviewDialog.confirm").click()
    assert back.isEnabled() is False
    dialog.fail("boom")
    assert back.isEnabled() is True, "a failed anchor must let the CUO back out"


# --- the two exits no `setEnabled(False)` can reach -------------------------------


def test_the_read_back_has_no_header_close_button(qtbot):
    """A confirmation modal has exactly two answers and both are labelled buttons.
    The header X was a third, unlabelled way off the last screen before an
    irreversible act -- and the only exit `_on_confirm` could not disable.
    Identified the way the base class builds it: a 32x32 icon-only QPushButton."""
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    unlabelled = [b for b in dialog.findChildren(QPushButton)
                  if not b.text() and b.size().width() == 32]
    assert unlabelled == [], (
        f"{len(unlabelled)} icon-only buttons in the read-back; pass "
        "show_close_button=False so the X is never built")
    assert sorted(b.text() for b in dialog.findChildren(QPushButton) if b.text()) \
        == [copy.REVIEW_BACK, copy.REVIEW_CONFIRM]


def test_escape_backs_out_before_signing(qtbot):
    """The guard below must not cost the CUO the ordinary way out."""
    import shiboken6

    from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog
    LocksmithDialog._current_dialog = None
    host = QWidget()
    qtbot.addWidget(host)
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole", parent=host)
    dialog.open()
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not shiboken6.Shiboken.isValid(dialog), timeout=2000)
    assert LocksmithDialog._current_dialog is None


def test_escape_cannot_destroy_the_read_back_mid_signing(qtbot):
    """`_on_confirm` disables both buttons, but Escape reaches `QDialog::reject`
    through Qt's key handling and no `setEnabled(False)` stands in its way. The
    issuance carries on either way, so destroying the dialog would remove the only
    surface that reports the outcome and leave `fail()` with nothing to re-arm."""
    import shiboken6

    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole")
    qtbot.addWidget(dialog)
    dialog.show()
    _ack(dialog)
    dialog.findChild(QPushButton, "mandateReviewDialog.confirm").click()

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert shiboken6.Shiboken.isValid(dialog), "Escape destroyed an in-flight modal"
    assert dialog.isVisible()

    # `close()` is refused too, not just Escape: QDialog::closeEvent calls
    # reject(), and ignores the close event unless the dialog actually hid. One
    # rule, not two. Measured: close() returns False here.
    assert dialog.close() is False
    assert shiboken6.Shiboken.isValid(dialog) and dialog.isVisible()

    dialog.fail("boom")
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: not shiboken6.Shiboken.isValid(dialog), timeout=2000)


# --- the suite's modal standards, pinned where they were measurably violated ---


def _built(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(1280, 900)
    host.show()
    qtbot.waitExposed(host)
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole", parent=host)
    dialog.open()
    qtbot.waitUntil(dialog.isVisible, timeout=2000)
    return host, dialog


def test_the_read_back_is_modal_but_carries_no_extra_scrim(qtbot):
    """Two properties, and the second is an owner decision that overrides the suite.

    MODAL: `show_overlay` defaults False and the plugin never passed it, so
    `setModal(True)` never ran -- measured `isModal() False`. The page calls
    `dialog.open()`, which sets WindowModal on its own, and that is what makes the
    app's one irreversibility confirmation actually block.

    NO SCRIM: ux-patterns.md:80 asks for a `bg-black/50` backdrop and this dialog
    carried one for two commits. Nothing else in the application does --
    `AppSettingsDialog` and the rest take the show_overlay=False default -- and
    the owner, comparing the CUO modal with Settings and the vault drawer, found
    this one visibly darker than every other dialog in the product: the app
    already reads as dimmed behind a modal, and the scrim was a second layer on
    top. The suite's rule assumes it is the only dimming mechanism. Owner
    decision, 2026-08-08.
    """
    host, dialog = _built(qtbot)
    assert dialog.isModal() is True
    assert dialog.overlay is None, (
        "a scrim is back; it double-dims, because the app already dims behind a "
        "modal and no other dialog adds one")
    dialog._finished = True
    dialog.close()
    host.hide()


def test_the_read_back_is_the_suites_md_modal_width(qtbot):
    """ux-patterns.md:82 "Max width: sm: 400px, md: 560px". It set no width at
    all and came out at 368px on sizeHint -- narrower than either token, which
    wrapped the caution to six lines and the in-force dates to two."""
    host, dialog = _built(qtbot)
    assert dialog.width() >= 560
    dialog._finished = True
    dialog.close()
    host.hide()


def test_the_footer_puts_the_secondary_left_and_the_primary_right(qtbot):
    """ux-patterns.md:288-289. The obvious `addStretch(1)` between the two does
    NOT do this: `_build_button_section` wraps the given layout in stretches on
    BOTH sides, which absorb it -- measured, the pair rendered centred and
    TOUCHING, a 0px gap between "Keep editing" and the irreversible primary."""
    host, dialog = _built(qtbot)
    back = dialog.findChild(QPushButton, "mandateReviewDialog.back")
    confirm = dialog.findChild(QPushButton, "mandateReviewDialog.confirm")
    back_x = back.mapTo(dialog, back.rect().topLeft()).x()
    confirm_x = confirm.mapTo(dialog, confirm.rect().topLeft()).x()

    assert back_x < confirm_x, "the primary must be the right-hand button"
    gap = confirm_x - (back_x + back.width())
    assert gap >= 16, f"only {gap}px between Keep editing and the irreversible primary"
    left_margin = back_x
    right_margin = dialog.width() - (confirm_x + confirm.width())
    assert left_margin <= 24 and right_margin <= 24, (
        f"the row is not spanning the footer: {left_margin}px / {right_margin}px")
    dialog._finished = True
    dialog.close()
    host.hide()


def test_the_header_divider_is_not_a_black_rule(qtbot):
    """`setFrameShape(HLine)` makes Qt paint a frame line in the palette's
    WindowText ON TOP of the #E8E8E8 the stylesheet asks for. Measured by pixel
    scan: rows 67/68/69 read #e8e8e8 / #000000 / #e8e8e8 -- a pure black line at
    19.99:1, the highest-contrast element in the dialog."""
    from PySide6.QtWidgets import QFrame

    host, dialog = _built(qtbot)
    divider = dialog.findChild(QFrame, "header-divider")
    assert divider is not None
    assert divider.frameShape() == QFrame.Shape.NoFrame, (
        "an HLine frameShape paints a palette-coloured rule over the stylesheet")

    image = dialog.grab().toImage()
    top = divider.mapTo(dialog, divider.rect().topLeft()).y()
    rows = [image.pixelColor(dialog.width() // 2, y).name()
            for y in range(top - 1, top + divider.height() + 1)]
    assert "#000000" not in rows, f"a black rule survives in the header: {rows}"
    dialog._finished = True
    dialog.close()
    host.hide()


def test_the_caution_is_not_the_same_chip_as_the_thesis(qtbot):
    """Both rendered as the SAME grey #DCDDE5 chip, differing only in text
    colour, so nothing marked the sentence that says "Signing is final." as a
    warning. Its 3.83:1 also failed the AA floor ui-conventions.md:69 sets."""
    from locksmith.ui import colors

    host, dialog = _built(qtbot)
    from PySide6.QtWidgets import QFrame

    # A QFrame now, not a QLabel: the caution is a lede plus a body inside one
    # amber block, and the frame carries the fill so the two read as one.
    caution = dialog.findChild(QFrame, "mandateReviewDialog.caution").styleSheet()
    thesis = dialog.findChild(QLabel, "mandateReviewDialog.thesis").styleSheet()
    assert colors.BACKGROUND_WARNING.lower() in caution.lower()
    assert colors.BACKGROUND_HIGHLIGHT.lower() not in caution.lower(), (
        "the caution still wears the thesis's grey chip")
    assert "border-left" in caution, "no rule marks it as a warning block"
    assert colors.BACKGROUND_WARNING.lower() not in thesis.lower()
    dialog._finished = True
    dialog.close()
    host.hide()


def test_every_font_size_is_on_the_suites_type_scale(qtbot):
    """design-system.md:98 "xs 11 · sm 12 · base 14 · lg 16 · xl 18 · 2xl 20 ·
    3xl 24 · 4xl 30" and :105 "Do not add a separate `md` size." The dialog
    carried 13px and 15px, neither of which is a step.

    Scoped to what THIS module styles. The base class's error/warning/success
    banner labels are also 13px and live in every dialog in the application --
    measured, they are what an unscoped sweep reports. Changing them is an
    app-wide decision, so asserting on them here would either fail forever or
    push a core change through a plugin's test.
    """
    import re

    from PySide6.QtWidgets import QFrame

    host, dialog = _built(qtbot)
    scale = {11, 12, 14, 16, 18, 20, 24, 30}
    base_banners = [dialog.findChild(QFrame, name)
                    for name in ("error-banner", "warning-banner", "success-banner")]
    inherited = {label for banner in base_banners if banner is not None
                 for label in banner.findChildren(QLabel)}

    offenders = []
    for widget in dialog.findChildren(QLabel):
        if widget in inherited:
            continue
        for size in re.findall(r"font-size:\s*(\d+)px", widget.styleSheet()):
            if int(size) not in scale:
                offenders.append((widget.objectName() or widget.text()[:24], size))
    assert not offenders, f"off-scale font sizes: {offenders}"
    dialog._finished = True
    dialog.close()
    host.hide()


def test_the_caution_can_never_scroll_out_of_view(qtbot):
    """Found independently by three UX reviews, and it is a bug rather than a
    style gap: the body sits inside `LocksmithDialog`'s QScrollArea, so with a
    three-line thesis the caution's bottom fell 37px below the fold (content
    397px in a 360px viewport) and the finality sentence was cut mid-word at "To
    correct a mandate, declare a", behind a scrollbar.

    The one block carrying irreversibility must not be scrollable on the screen
    whose entire job is to make irreversibility land before the click.
    """
    from PySide6.QtWidgets import QFrame, QScrollArea

    long_thesis = (
        "Grow teen-driver share in Utah by pricing telematics-verified low-mileage "
        "risk below the market, accepting a thinner margin for two years to build a "
        "book we can defend on loss ratio rather than on price alone.")
    payload = dict(_PAYLOAD, thesis=long_thesis, coverages=["BI", "PD", "COMP"])

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(1280, 900)
    host.show()
    qtbot.waitExposed(host)
    dialog = MandateReviewDialog(payload, signer_name="Dana Reyes", parent=host)
    dialog.open()
    qtbot.waitUntil(dialog.isVisible, timeout=2000)

    caution = dialog.findChild(QFrame, "mandateReviewDialog.caution")
    scroll = dialog.findChild(QScrollArea)
    assert scroll is not None, "retarget this guard — the base class stopped scrolling"
    assert not scroll.isAncestorOf(caution), (
        "the caution is back inside the scroll area, where a long thesis pushes it "
        "below the fold")

    top = caution.mapTo(dialog, caution.rect().topLeft()).y()
    assert top + caution.height() <= dialog.height(), (
        "the caution extends past the bottom of the dialog")
    assert caution.visibleRegion().boundingRect().height() == caution.height(), (
        "part of the caution is not actually painted")

    dialog._finished = True
    dialog.close()
    host.hide()


# --- what the UX panel changed, pinned -------------------------------------------


def test_the_screen_asks_the_reader_to_check_before_showing_the_values(qtbot):
    """The form's own help text delegates the catch to this screen ("the app
    cannot tell US-UT from US-TU, so read your code back before you sign") and
    this screen then said nothing at all. Position matters as much as presence: a
    prompt to check that arrives after the values is a prompt to check nothing."""
    host, dialog = _built(qtbot)
    intro = dialog.findChild(QLabel, "mandateReviewDialog.intro")
    assert intro is not None and intro.text() == copy.REVIEW_INTRO

    summary = dialog.findChild(QWidget, "mandateReviewDialog.summary")
    assert intro.mapTo(dialog, intro.rect().topLeft()).y() < \
        summary.mapTo(dialog, summary.rect().topLeft()).y()
    dialog._finished = True
    dialog.close()
    host.hide()


def test_the_signer_is_a_row_with_its_aid_not_prose(qtbot):
    """As a sentence it read "Signing as default, Chief Underwriting Officer" --
    which parses aloud as "signing, by default", the opposite of what a screen
    about authority is establishing. A label in front of the value stops the alias
    acting as an adverb, and the AID is what actually signs."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(1280, 900)
    host.show()
    qtbot.waitExposed(host)
    aid = "EGjm-X1JMz-yKFeumEZ9meSVNvnV8VTXmjJMlyBVMMTO"
    dialog = MandateReviewDialog(_PAYLOAD, signer_name="Dana Cole",
                                 signer_aid=aid, parent=host)
    dialog.open()
    qtbot.waitUntil(dialog.isVisible, timeout=2000)

    shown = _text(dialog)
    assert copy.REVIEW_SIGNER_LABEL.upper() in shown.upper()
    assert "Dana Cole" in shown
    assert aid in shown, "the identifier that actually signs is not on screen"
    assert not hasattr(copy, "REVIEW_SIGNER"), (
        "the prose signer line is back; it is what let an alias read as an adverb")
    dialog._finished = True
    dialog.close()
    host.hide()


def test_the_machine_shaped_values_are_monospaced(qtbot):
    """`US-AB` vs `US-AU`, `2026-08-19` vs `2026-08-91`: near-identical shapes in
    a proportional face, and a transposition here is exactly the error no
    validation can catch. Prose is NOT monospaced -- the line of business is a
    word, not a code."""
    from locksmith.ui.styles import get_monospace_font_family

    host, dialog = _built(qtbot)
    family = get_monospace_font_family()
    by_text = {w.text(): w for w in dialog.findChildren(QLabel) if w.text()}

    assert family in by_text["US-UT"].styleSheet()
    assert family in by_text["BI, PD"].styleSheet()
    assert family in by_text["2027-01-01 through 2027-12-31, inclusive"].styleSheet()
    assert family not in by_text["auto"].styleSheet(), (
        "the line of business is a word, not a code")
    dialog._finished = True
    dialog.close()
    host.hide()


def test_the_caution_leads_with_the_decision(qtbot):
    """44 words at one size is texture by the fifth mandate of the day. The lede
    carries the decision; the body carries the detail."""
    host, dialog = _built(qtbot)
    head = dialog.findChild(QLabel, "mandateReviewDialog.cautionHead")
    body = dialog.findChild(QLabel, "mandateReviewDialog.cautionBody")
    assert head is not None and body is not None
    assert head.text() == copy.REVIEW_CAUTION_HEAD
    assert len(head.text().split()) <= 8, "a lede nobody can take in at a glance"
    assert "font-weight: 600" in head.styleSheet()
    assert "14px" in head.styleSheet() and "12px" in body.styleSheet(), (
        "the lede must outrank the body")
    dialog._finished = True
    dialog.close()
    host.hide()


def test_signing_requires_an_affirmative_act(qtbot):
    """Signing was two clicks in a straight line from a filled form, the second
    landing on an already-enabled primary -- so what stood between a mandate and
    the world was the ABSENCE of an objection. Honest about what this buys: not
    that anyone reads, but that publishing takes an action taken on purpose."""
    host, dialog = _built(qtbot)
    confirm = dialog.findChild(QPushButton, "mandateReviewDialog.confirm")
    ack = dialog.findChild(QWidget, "mandateReviewDialog.ack")
    assert ack is not None

    assert confirm.isEnabled() is False, "the opening state must be non-signable"
    qtbot.keyClick(ack, Qt.Key.Key_Space)
    assert ack.isChecked() is True
    assert confirm.isEnabled() is True
    qtbot.keyClick(ack, Qt.Key.Key_Space)
    assert confirm.isEnabled() is False, "un-acknowledging must re-lock the primary"

    dialog._finished = True
    dialog.close()
    host.hide()


def test_a_failed_anchor_does_not_re_demand_the_acknowledgement(qtbot):
    """The CUO already gave it, for these exact values, which have not changed.
    Clearing it would read as the app doubting them rather than as a fresh
    decision."""
    host, dialog = _built(qtbot)
    confirm = dialog.findChild(QPushButton, "mandateReviewDialog.confirm")
    _ack(dialog)
    confirm.click()
    dialog.fail("boom")
    assert dialog._ack.isChecked() is True
    assert confirm.isEnabled() is True, "the retry is blocked behind a re-tick"
    dialog._finished = True
    dialog.close()
    host.hide()


def test_no_wrapping_label_is_shorter_than_the_text_it_paints(qtbot):
    """The wrapped-QLabel trap, pinned across every label at once.

    `sizeHint()` is computed at a label's NATURAL width -- one line -- so a label
    that wraps reports less height than it needs and the layout hands it exactly
    that. Measured on the long thesis: 80px reported, 99px required, and the last
    line ("alone.") painted underneath the pinned caution. `visibleRegion()` still
    claimed 80 of 80, which is why this asserts against `heightForWidth` instead.

    `page._fit` shares the blind spot; it survives there only because those labels
    wrap at their natural width.
    """
    long_thesis = (
        "Grow teen-driver share in Utah by pricing telematics-verified low-mileage "
        "risk below the market, accepting a thinner margin for two years to build a "
        "book we can defend on loss ratio rather than on price alone.")
    payload = dict(_PAYLOAD, thesis=long_thesis)

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(1280, 900)
    host.show()
    qtbot.waitExposed(host)
    dialog = MandateReviewDialog(payload, signer_name="Dana Cole",
                                 signer_aid="E" + "A" * 43, parent=host)
    dialog.open()
    qtbot.waitUntil(dialog.isVisible, timeout=2000)

    squeezed = []
    for label in dialog.findChildren(QLabel):
        if not label.wordWrap() or not label.text() or label.width() <= 0:
            continue
        needed = label.heightForWidth(label.width())
        if needed > label.height():
            squeezed.append(
                f"{label.objectName() or label.text()[:24]!r}: "
                f"{label.height()}px for {needed}px of text")
    assert not squeezed, "labels painting outside their own height:\n  " + \
        "\n  ".join(squeezed)

    dialog._finished = True
    dialog.close()
    host.hide()
