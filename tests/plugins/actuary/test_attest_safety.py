"""The three defects that made an attestation unsafe, pinned.

`attest()` mints a permanent, PUBLIC, edge-linked credential. Until these fixes
it could commit bytes the screen was not showing, commit them twice, and look
armed while it was not. Each test here fails against the pre-fix source.
"""
import pytest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from locksmith.plugins.actuary.page import ActuaryPage

_MANIFEST = "EManifestSaid" + "A" * 31
_MANDATE = "EMandate" + "A" * 36


def _page(qtbot):
    shell = QWidget()
    qtbot.addWidget(shell)
    shell.resize(1180, 940)
    layout = QVBoxLayout(shell)
    layout.setContentsMargins(0, 0, 0, 0)
    page = ActuaryPage(app=None, parent=shell)
    layout.addWidget(page)
    shell.show()
    qtbot.waitExposed(shell)
    return shell, page


def _loaded(page):
    """The state after a successful Load Parse, without needing a real parse dir."""
    page._parse_manifest = {"workbook_digest": "EWorkbookDigest"}
    page._parse_manifest_said = _MANIFEST
    page._manifest_said_label.setText(_MANIFEST)
    page._workbook_digest_label.setText("EWorkbookDigest")
    # `_load_parse_inner` sets these three ATOMICALLY with the manifest -- it
    # refuses the directory outright if index.json does not carry them -- so a
    # helper that sets the manifest without them describes a state the page
    # cannot actually be in.
    page._parse_filing_date = "2027-03-15"
    page._parse_action = "Sandbox"
    page._parse_mandate_said = _MANDATE
    page._filing_date_label.setText("03/15/2027")
    page._action_label.setText("Sandbox")
    page._selected_mandate_said = _MANDATE
    # Schema-required and the actuary's own label, so the gate holds without it.
    page._version.setText("2027.1")
    page._update_attest_enabled()


def test_editing_the_path_forgets_the_parse_it_loaded(qtbot):
    """THE defect where the ARTEFACT is wrong, not just hard to read.

    `attest()` reads `_parse_manifest_said`, never the field. With no
    invalidation the actuary could load directory A, edit the field to B, and
    mint a permanent public credential binding A's manifest SAID and workbook
    digest while the screen displayed B -- the UI behaving exactly as designed.
    """
    shell, page = _page(qtbot)
    _loaded(page)
    assert page._attest.isEnabled() is True

    page._parse_dir.setText("/some/other/directory")

    assert page._parse_manifest_said is None
    assert page._parse_manifest is None
    assert page._attest.isEnabled() is False
    # The em dash is the "nothing loaded" placeholder. What matters is that the
    # STALE value is gone -- a manifest SAID left on screen under a path that did
    # not produce it is the same lie in a quieter font.
    assert _MANIFEST not in page._manifest_said_label.text()
    assert page._manifest_said_label.text() == "—"
    assert page._workbook_digest_label.text() == "—"
    shell.hide()


def test_a_second_attest_is_refused_while_one_is_in_flight(qtbot):
    """A double-click scheduled two `ServiceaidIssueDoer`s and minted two
    permanent credentials for one rate program -- and the second listener
    replaced the first, so one banner covered both and the actuary never learned
    there were two. `CuoMandatePage` has carried this guard (`_anchoring`) all
    along; this page was the irreversible mint without it."""
    shell, page = _page(qtbot)
    _loaded(page)

    page._attesting = True
    page._error_banner.setVisible(False)
    page.attest()
    assert page._error_banner.isVisible() is False, (
        "a refused re-entry must return before validation, not fall through it")

    # And the guard must also un-arm the button, not merely gate the handler.
    page._update_attest_enabled()
    assert page._attest.isEnabled() is False
    shell.hide()


def test_the_guard_lifts_on_failure_as_well_as_success(qtbot):
    """A guard that only lifts on `credential_issued` turns one failed
    attestation into a permanently dead button. The sibling read-back shipped
    exactly that bug for a commit -- its modal survived its own success."""
    shell, page = _page(qtbot)
    _loaded(page)
    page._attesting = True
    page._update_attest_enabled()
    assert page._attest.isEnabled() is False

    page._release_attest()

    assert page._attesting is False
    assert page._attest.isEnabled() is True, "the actuary cannot retry"
    shell.hide()


def test_a_released_guard_does_not_re_arm_an_invalidated_parse(qtbot):
    """The two fixes must compose: if the path changed while the attestation was
    in flight, lifting the guard must NOT hand back an armed button."""
    shell, page = _page(qtbot)
    _loaded(page)
    page._attesting = True
    page._parse_dir.setText("/changed/mid/flight")

    page._release_attest()

    assert page._attest.isEnabled() is False, (
        "re-armed over a parse that no longer matches the path on screen")
    shell.hide()


def test_the_disabled_primary_does_not_look_armed(qtbot):
    """Measured: 0 of 46,612 pixels differed between the disabled and enabled
    Attest button. `LocksmithButton` declared `QPushButton`, `:hover` and
    `:pressed` and no `:disabled`, and a QSS background overrides Qt's
    palette-based greying -- so the control that mints an irreversible public
    credential rendered as a fully-armed primary on an empty screen."""
    shell, page = _page(qtbot)
    button = page._attest

    button.setEnabled(False)
    qtbot.wait(60)
    off = button.grab().toImage()
    button.setEnabled(True)
    qtbot.wait(60)
    on = button.grab().toImage()

    total = off.width() * off.height()
    differing = sum(1 for y in range(off.height()) for x in range(off.width())
                    if off.pixelColor(x, y) != on.pixelColor(x, y))
    assert differing > total * 0.5, (
        f"only {differing}/{total} pixels differ between disabled and enabled; "
        "the irreversible primary looks armed when it is not")
    shell.hide()


# --- the visual contract, from the UX panel --------------------------------------


def test_the_page_has_exactly_one_filled_primary(qtbot):
    """Load Parse is a local, re-runnable directory read; Attest mints a
    permanent public credential. They were both `LocksmithButton` at 1084x43, so
    the page had two primaries and therefore none (design-system.md:236)."""
    from locksmith.ui.toolkit.widgets.buttons import (
        LocksmithButton, LocksmithInvertedButton)

    shell, page = _page(qtbot)
    assert isinstance(page._attest, LocksmithButton)
    assert isinstance(page._load_parse, LocksmithInvertedButton)
    assert not isinstance(page._load_parse, LocksmithButton)
    shell.hide()


def test_neither_button_is_full_bleed_and_the_primary_stays_right(qtbot):
    """A hidden widget surrenders its stretch, so the primary drifted to the
    centre of the page the moment the blocker line cleared. Its position must not
    depend on whether something else happens to be visible."""
    shell, page = _page(qtbot)

    def right_gap():
        geometry = page._attest.geometry()
        return page.width() - (geometry.x() + geometry.width())

    assert page._attest.width() < page.width() * 0.5, "the primary is full-bleed"
    gated = right_gap()
    _loaded(page)
    qtbot.wait(50)
    assert right_gap() == gated, "the primary moved when the blocker line hid"
    shell.hide()


def test_the_gate_says_what_is_missing_without_a_hover(qtbot):
    """Qt tooltips are unreachable by keyboard, and "silently disabled" is the
    state the actuary meets most. One reason at a time, in the page's own
    sequence, so it reads as the next step."""
    shell, page = _page(qtbot)

    assert "mandate" in page._attest_blocker.text().lower()
    assert page._attest_blocker.isVisible() is True

    page._selected_mandate_said = _MANDATE
    page._update_attest_enabled()
    assert "parse" in page._attest_blocker.text().lower()

    _loaded(page)
    assert page._attest_blocker.text() == ""
    assert page._attest.toolTip() == ""
    shell.hide()


def test_the_empty_state_says_something(qtbot):
    """Measured before: the list interior was 1080x188 with ZERO non-background
    pixels, so a healthy quiet watch and a broken one were pixel-identical."""
    shell, page = _page(qtbot)

    assert page._empty_state.isVisible() is True
    assert page._observed_list.isVisible() is False
    text = page._empty_state.text().lower()
    assert "no mandates observed" in text
    assert "never sent" in text, "the placard must name the mechanic"

    page._observed = {_MANDATE: {"line_of_business": "auto",
                                 "jurisdiction": "US-UT", "coverages": ["BI"]}}
    page._refresh_observed_list()
    assert page._empty_state.isVisible() is False
    assert page._observed_list.isVisible() is True
    shell.hide()


def test_a_mandate_can_be_selected_with_the_keyboard(qtbot):
    """`clicked` fires for the mouse and for devctl and for nothing else, so
    arrow keys moved the highlight while `_selected_mandate_said` stayed put and
    Attest went on refusing. The whole flow was mouse-only."""
    from PySide6.QtCore import Qt

    shell, page = _page(qtbot)
    page._observed = {
        _MANDATE: {"line_of_business": "auto", "jurisdiction": "US-UT",
                   "coverages": ["BI"]},
        "EOther" + "B" * 38: {"line_of_business": "property",
                              "jurisdiction": "US-CA", "coverages": ["BB"]},
    }
    page._refresh_observed_list()
    page._observed_list.setFocus()
    page._observed_list.setCurrentRow(0)
    assert page._selected_mandate_said == _MANDATE

    qtbot.keyClick(page._observed_list, Qt.Key.Key_Down)
    assert page._selected_mandate_said != _MANDATE, (
        "arrow keys move the highlight but not the selection")
    shell.hide()


def test_the_evidence_values_are_monospaced_and_not_truncated(qtbot):
    """Two 44-char digests are the entire content of the credential. In a
    proportional face `l`/`I`/`1` and `O`/`0` are the same shape."""
    from locksmith.ui.styles import get_monospace_font_family

    from PySide6.QtGui import QFontInfo, QFontMetrics

    shell, page = _page(qtbot)
    family = get_monospace_font_family()
    for label in (page._manifest_said_label, page._workbook_digest_label):
        assert family in label.styleSheet()
        assert label.text() == "—", "the unloaded state must not be a blank"

        # The string being right proves nothing: the module default is the
        # literal "monospace", which is NOT a registered family on macOS, and an
        # unresolvable family falls back SILENTLY to the proportional system
        # face. Measured before quoting + a real fallback were added: resolved
        # .AppleSystemUIFont, fixedPitch False, `I` 3px against `W` 12px.
        metrics = QFontMetrics(label.font())
        assert metrics.horizontalAdvance("I") == metrics.horizontalAdvance("W"), (
            f"{label.objectName()} resolved to "
            f"{QFontInfo(label.font()).family()!r}, which is proportional — "
            "the digests are not actually proof-readable")

    _loaded(page)
    assert page._manifest_said_label.text() == _MANIFEST, "truncated or altered"
    shell.hide()


def test_no_form_layout_can_reintroduce_the_style_dependent_field_width(qtbot):
    """A defect no offscreen render could show, now removed by construction.

    `QFormLayout.fieldGrowthPolicy` has a STYLE-DEPENDENT default and the two
    styles disagree: Fusion — which the offscreen platform selects, so every test
    and every screenshot runs under it — defaults to `AllNonFixedFieldsGrow`,
    while the macOS style defaults to `FieldsStayAtSizeHint`. Measured under the
    macOS style: the parse-directory field was 151px of an 1180px page, narrower
    than the absolute paths it exists to accept, while every render I checked
    showed it full width.

    The page now builds label-above-field blocks in `QVBoxLayout`s, which have no
    such default and cannot regress this way. So this asserts the CONSTRUCT is
    gone rather than that one instance is configured correctly — a policy
    assertion only guards the form layouts that exist today, and the next one
    added would arrive with the style default again.
    """
    from PySide6.QtWidgets import QFormLayout

    shell, page = _page(qtbot)
    assert page.findChildren(QFormLayout) == [], (
        "a QFormLayout is back; either set fieldGrowthPolicy explicitly on it or "
        "use _field_block, because its default is FieldsStayAtSizeHint on macOS")

    # And the field really does take the column, under whatever style is active.
    column = page.findChild(QWidget, "actuaryPage.column")
    assert page._parse_dir.width() > column.width() * 0.9, (
        f"the parse field is {page._parse_dir.width()}px of a "
        f"{column.width()}px column")
    shell.hide()


# --- the states the page could not express -------------------------------------


def test_a_broken_watch_does_not_look_like_a_quiet_one(qtbot):
    """Three failure paths swallowed into `logger` and painted as the same empty
    box, so a page that CANNOT observe was pixel-identical to one with nothing to
    observe — and the log is not where the actuary is looking."""
    shell, page = _page(qtbot)
    assert "no mandates observed" in page._empty_state.text().lower()
    assert page._watch_retry.isVisible() is False

    page._watch_error = "The mandate schema could not be prepared."
    page._render_empty_state()

    text = page._empty_state.text().lower()
    assert "not working" in text
    assert "schema could not be prepared" in text
    assert page._watch_retry.isVisible() is True, "no way out of the failed state"
    shell.hide()


def test_retrying_the_watch_clears_the_cached_verdict(qtbot):
    """The failures are CACHED — `_egf_doc_cache` in particular — so a retry that
    does not reset them reports the same verdict without having re-tried
    anything, which is worse than no retry button at all."""
    shell, page = _page(qtbot)
    page._watch_error = "boom"
    page._egf_doc_cache = None
    page._render_empty_state()
    assert page._watch_retry.isVisible() is True

    # A retry against a still-broken environment must RE-REPORT, not clear: this
    # page has no vault, so watching genuinely cannot work.
    page._retry_watch()
    assert page._watch_error != "", "a failed retry silently reported success"
    assert page._egf_doc_cache == "unresolved", "the cached verdict survived"

    # ...and when the cause is gone, the retry clears it.
    page._prepare_import_schema = lambda: None
    page._scan_for_mandates = lambda: None
    page._retry_watch()
    assert page._watch_error == ""
    assert page._watch_retry.isVisible() is False
    shell.hide()


def test_loading_a_parse_cannot_be_re_entered(qtbot):
    """`_build_manifest` rglobs the directory, reads every shard and the whole
    .xlsm and Blake3s all of it, synchronously on the GUI thread. With no
    feedback the natural response to a frozen window is to click again and re-run
    the entire hash."""
    shell, page = _page(qtbot)
    calls = []
    page._load_parse_inner = lambda: calls.append(1)

    page.load_parse()
    assert calls == [1]

    page._loading_parse = True
    page.load_parse()
    assert calls == [1], "a second click re-ran the whole hash"

    page._loading_parse = False
    page.load_parse()
    assert calls == [1, 1]
    shell.hide()


def test_the_loading_state_is_actually_painted(qtbot):
    """The work never returns to the event loop, so a label set without an
    explicit repaint is queued and painted only after the hashing finishes —
    which from the actuary's point of view is never."""
    shell, page = _page(qtbot)
    seen = {}

    def spy():
        seen["text"] = page._load_parse.text()
        seen["enabled"] = page._load_parse.isEnabled()
        seen["readonly"] = page._parse_dir.isReadOnly()

    page._load_parse_inner = spy
    page.load_parse()

    assert "loading" in seen["text"].lower()
    assert seen["enabled"] is False
    assert seen["readonly"] is True, "the path can be edited mid-hash"
    # ...and it must all come back afterwards, including on the failure path.
    assert page._load_parse.isEnabled() is True
    assert page._parse_dir.isReadOnly() is False
    shell.hide()


def test_the_loading_state_is_restored_even_when_the_load_raises(qtbot):
    """A parse directory that disappears mid-read must not leave the button dead."""
    shell, page = _page(qtbot)

    def boom():
        raise OSError("the directory went away")

    page._load_parse_inner = boom
    with pytest.raises(OSError):
        page.load_parse()

    assert page._loading_parse is False
    assert page._load_parse.isEnabled() is True
    assert page._parse_dir.isReadOnly() is False
    shell.hide()


# --- the layout defects the owner saw, and I did not ------------------------------


def test_no_field_is_compressed_below_the_height_it_asked_for(qtbot):
    """Measured at 1180x940 on the macOS style: the parse-directory field was
    clipped through its own bottom border and the version field's help text was
    drawn ON TOP of its input.

    Every widget was configured correctly — a QVBoxLayout simply squeezes children
    past their size hints when it runs out of room, and this page's tallest
    element (the observed-mandates list) only grows. The page is inside a
    QScrollArea now, so it scrolls instead of crushing. Asserted as
    height >= sizeHint rather than as a pixel count, because the hint is what the
    widget asked for under whatever style is active.
    """
    from PySide6.QtWidgets import QScrollArea

    shell, page = _page(qtbot)
    shell.resize(900, 560)              # deliberately too short for the content
    qtbot.wait(60)

    assert page.findChild(QScrollArea, "actuaryPage.scroll") is not None, (
        "no scroll area; a page taller than its window will compress its fields")
    for field in (page._parse_dir, page._version):
        assert field.height() >= field.sizeHint().height(), (
            f"{field.objectName()} is {field.height()}px against a "
            f"{field.sizeHint().height()}px hint — it is being clipped")
    shell.hide()


def test_the_four_values_from_the_parse_are_grouped_apart_from_the_one_input(qtbot):
    """The boundary between "read from the artefact" and "typed by the actuary"
    is the whole point of this screen's shape, so it is drawn, not just stated in
    a caption."""
    shell, page = _page(qtbot)
    card = page.findChild(QWidget, "actuaryEvidence")
    assert card is not None, "the evidence group is gone"

    for label in (page._manifest_said_label, page._workbook_digest_label,
                  page._filing_date_label, page._action_label):
        assert card.isAncestorOf(label), (
            f"{label.objectName()} is outside the read-from-the-parse group")
    assert not card.isAncestorOf(page._version), (
        "the one field the actuary types is inside the group that says nothing "
        "here is chosen")
    shell.hide()


def test_no_visible_label_shows_raw_markdown(qtbot):
    """A backtick is markdown, and a QLabel renders it as a backtick. The
    evidence caption shipped `ipd-parse` with the quotes visible on screen."""
    from PySide6.QtWidgets import QLabel

    shell, page = _page(qtbot)
    offenders = [(w.objectName(), w.text()) for w in page.findChildren(QLabel)
                 if "`" in w.text() or "**" in w.text()]
    assert offenders == [], f"raw markdown on screen: {offenders}"
    shell.hide()


def test_the_mandate_list_does_not_reserve_a_row_it_has_nothing_to_put_in(qtbot):
    """One mandate sat above ~90px of empty box, which reads as a pane that
    failed to load rather than a list with one entry. The list is hidden entirely
    when there is nothing to show, so there is no first-arrival jump to smooth
    over — the placard is what fills that space."""
    shell, page = _page(qtbot)
    page._observed = {_MANDATE: {"line_of_business": "auto",
                                 "jurisdiction": "US-UT", "coverages": ["BI"]}}
    page._refresh_observed_list()
    qtbot.wait(50)

    row = page._observed_list.sizeHintForRow(0)
    assert row > 0
    assert page._observed_list.height() < 2 * row, (
        f"the list is {page._observed_list.height()}px for one {row}px row")
    shell.hide()
