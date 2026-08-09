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
    assert page._manifest_said_label.text() == "", (
        "a stale manifest SAID is still on screen under a path that did not "
        "produce it")
    assert page._workbook_digest_label.text() == ""
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
