# -*- encoding: utf-8 -*-
"""No schema value may be written into Python. This is what "from the EGF" means.

If the enum is duplicated in source, the form and the credential can disagree, and
the disagreement shows up as a mint failure the user cannot act on -- the exact
loop this plan removes.

Two independent checks, not one, because a single substring scan gets this wrong
in both directions:

* A naive `value in text` scan false-positives on ordinary English: `"life"` is
  a substring of the comment word "lifecycle", and `"property"` is a substring
  of the ordinary word "properties" (both appear, legitimately, in this
  package's prose). A scan that cannot pass on correct code is worse than no
  guard: the next person to trip it will delete it, and it will not be there
  the day someone really does paste an enum member into a dropdown.
* Conversely, requiring the value to be a *quoted* literal (matching the
  boundary quotes exactly) already rules out the substring problem for
  anything actually inside quotes -- `"lifecycle"` does not contain the
  four-character sequence `"life"` (quote, l, i, f, e, quote). But a schema
  value COULD in principle reach source unquoted -- some bare token that
  happens to equal it -- and a scan that only ever looks inside quotes would
  miss that.

So this file runs both:

`_quoted_hits` -- STRICT, and scans the WHOLE file, comments and docstrings
included. A quoted `"workers_compensation"` sitting in a comment is still a
restatement of the schema, word for word, and the fact that it is inert to the
Python interpreter does not make it any less likely to drift from the EGF the
day the enum changes. This is the check Step 3 of the task brief exercises:
pasting `_TEMP = "workers_compensation"` must fail here.

`_bare_word_hits` -- word-bounded (`\\b`-delimited, so "lifecycle" cannot match
"life"), and scans only executable code: comments and string contents (which
`_quoted_hits` already covers) are blanked out first via `tokenize`, so an
English word inside a comment -- "property" in ordinary prose -- is out of
scope for this check specifically because it is prose, not code. What is left
after blanking is the token stream Python actually runs; a bare, unquoted
occurrence of a schema word there (an identifier, a bare name) is still the
defect this guard exists to catch, just a rarer shape of it.

Every offense names the file, the literal, and which of the two checks fired,
so a failure here is something a person can act on without re-deriving the
scan.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

import pytest

from locksmith.core.branding import egf_local_dir
from locksmith.plugins.cuo.schema_source import load_mandate_schema

_SRC = Path(__file__).resolve().parents[3] / "src" / "locksmith" / "plugins" / "cuo"

_QUOTED = "quoted string literal (comments and docstrings included)"
_BARE = "bare word in executable code (comments and strings excluded)"


def _sources() -> list[Path]:
    return sorted(p for p in _SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _code_only(text: str) -> str:
    """`text` with every comment and every string literal blanked out, in place.

    Blanking (not deleting) is what keeps line and column numbers stable, which
    matters not for this function's own output but for correctness of the
    blanking itself: `tokenize` reports each token's span in (row, 1-indexed;
    col, 0-indexed) coordinates against the ORIGINAL text, so shortening the
    text as we go would desync every span after the first change.

    Raises if the file cannot be tokenized -- a source file this guard cannot
    parse is a file it cannot vouch for either way, and staying silent about
    that is worse than a loud, actionable failure.
    """
    grid = [list(line) for line in text.splitlines(keepends=True)]
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    for tok in tokens:
        if tok.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (start_row, start_col), (end_row, end_col) = tok.start, tok.end
        for row in range(start_row, end_row + 1):
            if row - 1 >= len(grid):
                continue
            line = grid[row - 1]
            col_from = start_col if row == start_row else 0
            col_to = end_col if row == end_row else len(line)
            for col in range(col_from, min(col_to, len(line))):
                if line[col] not in ("\n", "\r"):
                    line[col] = " "
    return "".join("".join(line) for line in grid)


def _quoted_hits(text: str, literal: str) -> bool:
    """Does `literal` appear as an exact Python string literal anywhere in
    `text` -- code, comment or docstring alike? The quote characters are the
    boundary, so this can never match a mere substring of a longer word."""
    pattern = re.compile(r"([\"'])" + re.escape(literal) + r"\1")
    return bool(pattern.search(text))


def _bare_word_hits(code_only_text: str, literal: str) -> bool:
    """Does `literal` appear as a whole word (`\\b`-bounded) in `code_only_text`
    -- text that has already had every comment and string blanked out? Applying
    this to the RAW file would flag "lifecycle" for "life" and "properties" for
    "property"; applying the quote requirement here instead would just
    duplicate `_quoted_hits`. Word-bounded and code-only is what makes this
    check catch a literal that reached source unquoted, without also catching
    prose."""
    pattern = re.compile(r"\b" + re.escape(literal) + r"\b")
    return bool(pattern.search(code_only_text))


def _offenders(literal: str) -> dict[str, str]:
    """{filename: which check fired} for every source file that restates
    `literal`. Checked once per file since `_code_only` is not free, computed
    at most once per file per literal (this package is small; a per-value
    cache is not worth the complexity it would add to a test whose whole job
    is being obviously correct)."""
    offenders: dict[str, str] = {}
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        if _quoted_hits(text, literal):
            offenders[path.name] = _QUOTED
            continue
        if _bare_word_hits(_code_only(text), literal):
            offenders[path.name] = _BARE
    return offenders


def test_the_guard_has_sources_to_scan():
    assert _sources(), f"no python found under {_SRC} -- retarget this guard"


@pytest.mark.parametrize("literal", ["^US-[A-Z]{2}$", "^[A-Z0-9][A-Z0-9-]*$"])
def test_no_schema_regex_appears_in_source(literal):
    offenders = _offenders(literal)
    assert not offenders, (
        f"{offenders} hardcode {literal!r}; read it from the schema instead")


def test_no_enum_member_appears_in_source():
    """The enum is the most tempting thing to paste into a dropdown."""
    enum = load_mandate_schema(egf_local_dir()).fields["line_of_business"].enum
    assert enum, "the schema has no enum -- this guard would be vacuous"
    offenders: dict[str, dict[str, str]] = {}
    for value in enum:
        for name, how in _offenders(value).items():
            offenders.setdefault(name, {})[value] = how
    assert not offenders, (
        f"{offenders} hardcode line_of_business values; build the dropdown from "
        f"the schema's enum")
