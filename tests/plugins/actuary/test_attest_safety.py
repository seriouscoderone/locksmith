"""The three defects that made an attestation unsafe, pinned.

`attest()` mints a permanent, PUBLIC, edge-linked credential. Until these fixes
it could commit bytes the screen was not showing, commit them twice, and look
armed while it was not. Each test here fails against the pre-fix source.
"""
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
    page._selected_mandate_said = _MANDATE
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

    shell, page = _page(qtbot)
    family = get_monospace_font_family()
    for label in (page._manifest_said_label, page._workbook_digest_label):
        assert family in label.styleSheet()
        assert label.text() == "—", "the unloaded state must not be a blank"

    _loaded(page)
    assert page._manifest_said_label.text() == _MANIFEST, "truncated or altered"
    shell.hide()
