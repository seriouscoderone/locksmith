"""A closed `LocksmithDialog` must be DESTROYED, not merely hidden.

`LocksmithDialog.__init__` sets `WA_DeleteOnClose`. Nothing asserted it until now,
and the cost of that gap has been paid twice:

1. Before the attribute existed, every open left a hidden, fully-built dialog in
   the parent's child tree, each carrying the SAME objectNames as the live one.
   Anything resolving a widget by name over the window's children — devctl's
   `_find_widget_any`, and any future accessibility or scripting surface — got the
   FIRST match, i.e. the oldest corpse. Measured: Add Peer and Add Schema each
   opened correctly once per session, and every later open produced a real dialog
   on screen that no selector could reach.
2. Five helpers in `tests/integration/roles/conftest.py` then hardcoded
   `occurrence=1` and `occurrence=2` indices to step past those corpses. When the
   attribute landed, the corpses vanished and every one of those indices selected
   NOTHING — three integration tests failing as "dialog never opened", each costing
   a 20s-to-150s UI run to diagnose.

So the attribute is load-bearing in both directions: remove it and the name-based
finders break; keep it and the indices must stay at 0. This file is the cheap,
fast guard that says which.

Note these tests deliberately do NOT `qtbot.addWidget` the dialogs. qtbot registers
widgets for teardown, and a dialog that has already deleted itself makes that
teardown raise "Internal C++ object already deleted" — which then cascades into
"previous item was not torn down properly" on the NEXT test. Only the parent is
registered; the dialogs are owned by it, or by their own close.
"""
import ast
import re
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src" / "locksmith"


@pytest.fixture(autouse=True)
def _no_leaked_current_dialog():
    """`_current_dialog` is CLASS-level state, so it leaks between tests in both
    directions: a dialog this file leaves behind poisons the next test, and one an
    earlier test left behind makes these assertions pass for the wrong reason."""
    LocksmithDialog._current_dialog = None
    yield
    LocksmithDialog._current_dialog = None


def _open(parent, object_name):
    content = QLabel("body")
    content.setObjectName(object_name)
    dialog = LocksmithDialog(parent, content=content, show_overlay=False)
    dialog.show()
    return dialog


def test_the_base_dialog_sets_delete_on_close(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = LocksmithDialog(parent, show_overlay=False)
    assert dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)


def test_closing_leaves_no_named_twin_in_the_parents_tree(qtbot):
    """The behaviour the attribute buys, asserted the way the finders see it:
    resolve by objectName over the PARENT's children, exactly as devctl does."""
    parent = QWidget()
    qtbot.addWidget(parent)

    first = _open(parent, "probeDialog.field")
    assert len(parent.findChildren(QWidget, "probeDialog.field")) == 1
    first.close()
    # Deferred delete: WA_DeleteOnClose POSTS the deletion, it is not immediate.
    qtbot.waitUntil(
        lambda: not parent.findChildren(QWidget, "probeDialog.field"), timeout=2000)

    second = _open(parent, "probeDialog.field")
    matches = parent.findChildren(QWidget, "probeDialog.field")
    assert len(matches) == 1, (
        f"{len(matches)} widgets named 'probeDialog.field' are alive after one "
        "close and one re-open. A name-based finder returns the FIRST match, so "
        "the extra one is what every selector would resolve to. This is the state "
        "the integration helpers' occurrence= indices used to compensate for.")
    assert matches[0] is second.findChild(QWidget, "probeDialog.field")
    second.close()
    qtbot.waitUntil(
        lambda: not parent.findChildren(QWidget, "probeDialog.field"), timeout=2000)


def test_repeated_open_close_cycles_do_not_accumulate(qtbot):
    """The leak was per-open, so one cycle could hide it."""
    parent = QWidget()
    qtbot.addWidget(parent)
    for _ in range(3):
        dialog = _open(parent, "cycleDialog.field")
        assert len(parent.findChildren(QWidget, "cycleDialog.field")) == 1
        dialog.close()
        qtbot.waitUntil(
            lambda: not parent.findChildren(QWidget, "cycleDialog.field"),
            timeout=2000)
    assert parent.findChildren(QWidget, "cycleDialog.field") == []


# ---------------------------------------------------------------------------
# The other half of WA_DeleteOnClose: EVERY exit path must release the pointer.
#
# `WA_DeleteOnClose` destroys the dialog on all of them, but only `close()` runs
# `closeEvent` -- `reject()`/`accept()` go through `QDialog::done()`, which does
# not. `closeEvent` used to be the only place `_current_dialog` was cleared, so
# one Escape left a class attribute pointing at a deleted C++ object and every
# later dialog in the process raised inside `showEvent`. Silently: PySide's
# excepthook logs the RuntimeError and the app carries on looking merely broken.
# ---------------------------------------------------------------------------

_EXITS = ("close", "reject", "accept", "escape")


def _exit_via(dialog, how, qtbot):
    """Escape is not a synonym for reject() here -- it is the route a USER takes,
    and it reaches reject() through Qt's own key handling rather than ours."""
    if how == "escape":
        qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    else:
        getattr(dialog, how)()


@pytest.mark.parametrize("how", _EXITS)
def test_every_exit_path_releases_the_current_dialog_pointer(how, qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = _open(parent, f"exit{how}Dialog.field")
    assert LocksmithDialog._current_dialog is dialog

    _exit_via(dialog, how, qtbot)

    left = LocksmithDialog._current_dialog
    state = "a LIVE" if left is None or shiboken6.Shiboken.isValid(left) else "a DELETED"
    assert left is None, (
        f"{how} left _current_dialog pointing at {state} dialog. Only close() runs "
        "closeEvent; reject/accept go through QDialog::done(), which deletes the "
        "object without it. Every destruction path must release the pointer.")


@pytest.mark.parametrize("how", _EXITS)
def test_a_dialog_still_opens_after_the_previous_one_exited(how, qtbot):
    """The user-visible consequence, and the whole reason the pointer matters: it
    is read by the NEXT dialog's `showEvent`. Pre-fix, `reject`, `accept` and
    Escape each made this raise "Internal C++ object (LocksmithDialog) already
    deleted" -- and since the raise happens BEFORE `showEvent` reassigns the
    pointer, the same corpse greeted every subsequent dialog until restart."""
    parent = QWidget()
    qtbot.addWidget(parent)
    first = _open(parent, f"first{how}Dialog.field")
    _exit_via(first, how, qtbot)
    # `WA_DeleteOnClose` POSTS the deletion. Without this wait the corpse is
    # still a valid C++ object when the second dialog opens, so the test passes
    # against the BUG -- measured: it did, on three of the four exits. A real
    # user always returns to the event loop between dismissing one dialog and
    # opening the next.
    qtbot.waitUntil(lambda: not shiboken6.Shiboken.isValid(first), timeout=2000)

    second = _open(parent, f"second{how}Dialog.field")
    assert LocksmithDialog._current_dialog is second
    second.close()


def test_show_event_discards_a_pointer_a_future_path_forgot_to_release(qtbot):
    """`_release_current_dialog` covers the three exits that exist today; this is
    the net for a fourth somebody adds later. A dead pointer must be DISCARDED,
    not dereferenced -- dereferencing it is what made the original defect
    permanent rather than momentary. Planted by hand, because after the fix no
    real path produces one."""
    parent = QWidget()
    qtbot.addWidget(parent)
    corpse = _open(parent, "corpseDialog.field")
    corpse.reject()
    qtbot.waitUntil(lambda: not shiboken6.Shiboken.isValid(corpse), timeout=2000)
    LocksmithDialog._current_dialog = corpse      # exactly what the bug looked like

    survivor = _open(parent, "survivorDialog.field")
    assert LocksmithDialog._current_dialog is survivor
    survivor.close()


def _reject_accept_overrides_missing_super():
    """Files that import `LocksmithDialog` and override `reject`/`accept` without
    delegating to it. Returns `[]` when clean."""
    offenders = []
    for path in _SRC.rglob("*.py"):
        text = path.read_text()
        if "LocksmithDialog" not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.FunctionDef) or node.name not in ("reject", "accept"):
                continue
            delegates = any(
                isinstance(call.func, ast.Attribute)
                and call.func.attr == node.name
                and isinstance(call.func.value, ast.Call)
                and isinstance(call.func.value.func, ast.Name)
                and call.func.value.func.id == "super"
                for call in ast.walk(node) if isinstance(call, ast.Call))
            if not delegates:
                offenders.append(f"{path.relative_to(_SRC)}:{node.lineno}: {node.name}")
    return offenders


def test_no_dialog_overrides_reject_or_accept_without_delegating():
    """`LocksmithDialog.reject`/`accept` are where the pointer is released, so an
    override that does not call super reintroduces the bug for that one dialog --
    and the symptom lands on some UNRELATED dialog opened later, which is why it
    took a whole-branch review to find the first time."""
    offenders = _reject_accept_overrides_missing_super()
    assert not offenders, (
        "these override a dialog exit without calling super, so "
        "`_current_dialog` keeps pointing at the deleted dialog and the next "
        "dialog opened anywhere in the app raises:\n  " + "\n  ".join(offenders))


def test_the_delegation_guard_can_actually_see_a_missing_super(tmp_path):
    """The sweep above passes vacuously if the AST walk is wrong -- the same way
    the occurrence guard below would rot. Feed it both shapes and check it
    separates them."""
    global _SRC
    original, _SRC = _SRC, tmp_path
    try:
        (tmp_path / "bad.py").write_text(
            "from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog\n"
            "class D(LocksmithDialog):\n"
            "    def reject(self):\n        self.hide()\n")
        (tmp_path / "good.py").write_text(
            "from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog\n"
            "class D(LocksmithDialog):\n"
            "    def reject(self):\n        super().reject()\n")
        (tmp_path / "unrelated.py").write_text(
            "class D:\n    def accept(self):\n        pass\n")
        found = _reject_accept_overrides_missing_super()
    finally:
        _SRC = original
    assert found == ["bad.py:3: reject"], f"the sweep reported {found}"


def test_no_subclass_turns_delete_on_close_back_off():
    """Source-level sweep, because a subclass CAN clear an inherited attribute and
    a behavioural test would only catch the subclasses somebody remembered to
    instantiate. `LocksmithDialog` has many subclasses across the UI, most needing
    an app/vault to construct."""
    pattern = re.compile(r"WA_DeleteOnClose\s*,\s*False")
    offenders = [str(p.relative_to(_SRC)) for p in _SRC.rglob("*.py")
                 if pattern.search(p.read_text())]
    assert not offenders, (
        f"{offenders} disable WA_DeleteOnClose. Every name-based widget finder "
        "then resolves the oldest hidden copy of that dialog instead of the live "
        "one, silently.")


def test_the_integration_helpers_carry_no_occurrence_overrides():
    """The other direction, and the one that actually broke: an `occurrence=N`
    (N>0) in these helpers is only ever right while a stale dialog exists to skip.
    With WA_DeleteOnClose in force it selects nothing, and the failure surfaces as
    an unrelated-looking "dialog never opened" in a multi-minute UI run.

    Parsed with `ast` rather than grepped: the surviving PROSE in those files
    explains the history and says `occurrence=1` several times, so a text sweep
    reports the documentation as the defect (it did, first run). This looks only at
    real keyword arguments with a literal value.
    """
    conftests = [_REPO / "tests" / "integration" / "roles" / "conftest.py",
                 _REPO / "tests" / "integration" / "peer" / "conftest.py"]
    present = [p for p in conftests if p.is_file()]
    assert present, "neither integration conftest found — retarget this guard"

    offenders = []
    for path in present:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                # occurrence=0 is harmless (it IS the default); only N>0 encodes
                # a stale twin to step past.
                if (kw.arg == "occurrence"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, int)
                        and kw.value.value > 0):
                    offenders.append(f"{path.name}:{kw.value.lineno}: "
                                     f"occurrence={kw.value.value}")
    assert not offenders, (
        "these pass occurrence>0, which only works if a stale dialog copy exists "
        "to skip past. WA_DeleteOnClose means there is none, so they resolve "
        "nothing:\n  " + "\n  ".join(offenders))


def test_the_occurrence_guard_can_actually_see_a_keyword_argument():
    """The guard above passes vacuously if the AST walk is wrong — which is exactly
    how it would rot. Feed it the shape it is looking for and check it matches."""
    tree = ast.parse('devctl(sock, "wait_for", target="x", occurrence=2)\n'
                     'devctl(sock, "wait_for", target="y", occurrence=0)\n')
    found = [kw.value.value for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             for kw in node.keywords
             if kw.arg == "occurrence" and isinstance(kw.value, ast.Constant)
             and kw.value.value > 0]
    assert found == [2], f"the walk missed a real occurrence= argument: {found}"
