# -*- encoding: utf-8 -*-
"""No platform-specific strftime codes anywhere in the shipped source.

`%-I` / `%-d` / `%-m` (drop the leading zero) are glibc and BSD extensions.
Python does not implement strftime itself -- it hands the format to the
platform C library -- so these work on macOS and Linux and raise
`ValueError: Invalid format string` on Windows, whose CRT spells it `%#I`.

This is a one-way failure: every developer machine and every CI runner that
builds the macOS artifact accepts them, so the defect can only ever be found by
a Windows user running the shipped app. It reached one in 0.4.0
(`actuary/page.py` stamped its heartbeat with `%-I`), where it fired inside a
page constructor, escaped through `get_pages`, and cost the whole actuary
workspace: the role read ACTIVE from its credential but registered no page, so
there was no Open button and no sidebar entry -- a symptom that looks nothing
like a date-formatting bug.

Formatting an unpadded hour portably needs no format code at all:

    f"{now:%m/%d/%Y} {now.hour % 12 or 12}:{now:%M %p}"

The scan is AST-based rather than line-based so that prose ABOUT these codes --
this docstring, the comment in `actuary/page.py:_stamp` -- is not itself a
finding. Comments never enter the AST; docstrings are skipped explicitly. String
literals in real code are what remain, and f-string format specs are covered
too, since `f"{x:%-I}"` puts the spec in the tree as a Constant.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

#: The padding modifiers, restricted to the conversion letters they can precede,
#: so an ordinary "%-5s" width spec or "20%-ish" in prose is not a hit.
_NAUGHTY = re.compile(r"%[-#](?=[aAbBcdHIjmMpSUwWxXyYZ])")


def _docstring_ids(tree: ast.AST) -> set[int]:
    """`id()` of every Constant node that is a module/class/function docstring."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            out.add(id(body[0].value))
    return out


def _offenders_in(source: str, label: str) -> list[str]:
    tree = ast.parse(source)
    skip = _docstring_ids(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip:
            continue
        if _NAUGHTY.search(node.value):
            hits.append(f"{label}:{node.lineno}: {node.value!r}")
    return hits


def _offenders() -> list[str]:
    hits: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:                      # pragma: no cover
            continue
        try:
            hits += _offenders_in(source, str(path.relative_to(SRC.parent.parent)))
        except SyntaxError:                             # pragma: no cover
            continue
    return hits


def test_no_platform_specific_strftime_padding_codes():
    offenders = _offenders()
    assert not offenders, (
        "Platform-specific strftime padding codes found. These raise "
        "ValueError: Invalid format string on Windows and cannot be caught by "
        "any macOS or Linux test run:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_can_actually_see_an_offender():
    """A detector that matches nothing would pass this suite forever.

    Pins what must match, and — equally load-bearing — what must not, since a
    guard that flags its own explanation gets deleted by the next person.
    """
    assert _offenders_in('x = t.strftime("%m/%d/%Y %-I:%M %p")', "f.py")
    assert _offenders_in('x = f"{now:%-d} of the month"', "f.py")
    assert _offenders_in('x = "%#I on windows"', "f.py")

    assert not _offenders_in('"""Never use %-I here."""', "f.py")   # docstring
    assert not _offenders_in("x = 1  # avoid %-I", "f.py")          # comment
    assert not _offenders_in('x = "%-5s"', "f.py")                  # width spec
    assert not _offenders_in('x = "discount 20%-ish"', "f.py")
    assert not _offenders_in('x = t.strftime("%m/%d/%Y %I:%M %p")', "f.py")
