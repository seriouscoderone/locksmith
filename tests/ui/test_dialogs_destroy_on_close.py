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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src" / "locksmith"


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
