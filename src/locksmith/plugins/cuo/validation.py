# -*- encoding: utf-8 -*-
"""Validation of a mandate payload. Pure, Qt-free, and the only place rules live.

Two sources, and the docstrings say which:

* the payload schema (Task 1) -- enum, pattern, minItems, uniqueItems, minLength,
  format: date;
* the micro-app template's two PRE-MINT gates --
  `mandate_window_opens_before_it_closes` and
  `no_overlapping_mandate_for_this_scope`.

The ordering gate is the reason this module is worth writing carefully. Its own
description: "checked BEFORE the ACDC is anchored, which is the only point at which
refusing costs nothing... nothing re-checks this after issuance" -- ACDC cannot
constrain two values inside one container. If this function is wrong, a mandate
whose window closes before it opens is anchored permanently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from locksmith.plugins.cuo import mandate_copy as copy
from locksmith.plugins.cuo.schema_source import FieldConstraints, MandateSchema


@dataclass(frozen=True)
class FieldError:
    field: str
    message: str


def _as_date(value: Any) -> date | None:
    """Parse a `format: date` value, or None. Deliberately does NOT coerce.

    Two defects live in the alternative. `date.fromisoformat` accepts every ISO
    8601 form since 3.11 -- `20270101` and `2027-W01-1` both parse -- and the schema
    puts no `pattern` on these fields, so a string compare between two different
    forms inverts (`'-'` 0x2D < `'0'` 0x30). And coercing a non-string with `str()`
    makes it pass the field check while failing the gate's own isinstance test, so
    the ordering block is skipped entirely. Measured: both let an inverted window
    validate clean, which nothing re-checks after the ACDC is anchored.
    """
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def windows_overlap(a_opens: str, a_closes: str,
                    b_opens: str, b_closes: str) -> bool:
    """The standard inclusive interval test, on PARSED dates.

    An earlier revision compared the raw strings, reasoning that ISO-8601 dates
    sort lexicographically. That is only true within one fixed form: `format:
    date` puts no `pattern` on the underlying fields, `date.fromisoformat` has
    accepted every ISO 8601 date form since Python 3.11 (`20270101`,
    `2027-W01-1`, ...), and a string compare between two different forms
    inverts, because `'-'` is 0x2D and `'0'` is 0x30. Parsing to `date` objects
    before comparing removes the dependence on form entirely. Touching
    endpoints still overlap: both dates count as in force.

    Any argument that fails to parse makes this return False -- an unparseable
    date cannot overlap anything, and `validate_payload` never reaches this
    function without first confirming all four parse.
    """
    a_opens_d, a_closes_d = _as_date(a_opens), _as_date(a_closes)
    b_opens_d, b_closes_d = _as_date(b_opens), _as_date(b_closes)
    if None in (a_opens_d, a_closes_d, b_opens_d, b_closes_d):
        return False
    return a_opens_d <= b_closes_d and b_opens_d <= a_closes_d


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set)):
        return len(value) == 0
    return False


def _scalar_errors(c: FieldConstraints, value: Any) -> list[str]:
    out: list[str] = []
    text = value if isinstance(value, str) else str(value)
    if c.enum is not None and text not in c.enum:
        out.append(copy.enum_error(c.name, text, c.enum))
    if c.pattern is not None and not re.fullmatch(c.pattern, text):
        out.append(copy.pattern_error(c.name))
    if c.min_length is not None and len(text) < c.min_length:
        out.append(copy.required_error(c.name))
    # Consumes the RAW value, not `text` -- `str(date(2027, 1, 1))` would
    # otherwise parse cleanly and hide a non-string date from this check (see
    # `_as_date`'s docstring for the defect this closes).
    if c.fmt == "date" and _as_date(value) is None:
        out.append(copy.date_error(c.name))
    return out


def _array_errors(c: FieldConstraints, value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        # Not `required_error`: the field is not empty, it is the wrong shape
        # (e.g. a bare string where a list was expected), and "add at least
        # one coverage code" would misdiagnose a value the user did supply.
        return [copy.pattern_error(c.name)]
    items = list(value)
    out: list[str] = []
    if c.min_items is not None and len(items) < c.min_items:
        out.append(copy.required_error(c.name))
    if c.unique_items:
        seen: set[str] = set()
        for item in items:
            # `str(item)` for membership, matching the pattern loop below --
            # an unhashable item (e.g. a nested list) must not crash the
            # uniqueness check.
            key = str(item)
            if key in seen:
                out.append(copy.COVERAGE_DUPLICATE.format(code=item))
                break
            seen.add(key)
    if c.item_pattern is not None:
        for item in items:
            if not re.fullmatch(c.item_pattern, str(item)):
                out.append(copy.COVERAGE_PATTERN.format(code=item))
                break
    return out


def validate_payload(payload: Mapping[str, Any], schema: MandateSchema,
                     existing: Sequence[Mapping[str, Any]] = ()) -> list[FieldError]:
    """Every error in the payload, in the schema's own field order.

    Returns ALL errors rather than the first: the summary banner counts them and
    `ux-patterns.md:192` focuses the first invalid field, so both need the full set.
    """
    errors: list[FieldError] = []
    # copy.FIELD_ORDER, not schema.order: presentation and error order are a UI
    # decision, and the schema's own key order is alphabetized. See FIELD_ORDER.
    for name in copy.FIELD_ORDER:
        c = schema.fields.get(name)
        if c is None:
            continue
        value = payload.get(name)
        if _empty(value):
            if c.required:
                errors.append(FieldError(name, copy.required_error(name)))
            continue
        messages = (_array_errors(c, value) if c.type == "array"
                    else _scalar_errors(c, value))
        errors.extend(FieldError(name, m) for m in messages)

    opens, closes = payload.get("window_opens"), payload.get("window_closes")
    opens_d, closes_d = _as_date(opens), _as_date(closes)
    # Gated on "did this parse as a date" -- NOT on "does window_closes have
    # ANY error" (an earlier revision used the latter via `already`). Scoped
    # this way on purpose: if `window_closes` ever gains its own `pattern`,
    # a value that fails that pattern but still parses fine as a date must
    # still run the ordering/overlap check below, or this function would
    # silently stop returning ALL errors, contradicting its own docstring.
    if opens_d is not None and closes_d is not None:
        # mandate_window_opens_before_it_closes -- STRICT, so equal dates fail.
        # Compares parsed dates, not the raw strings: see `_as_date` and
        # `windows_overlap`'s docstrings for the defect a string compare hid.
        if not opens_d < closes_d:
            errors.append(FieldError("window_closes", copy.WINDOW_ORDER))
        else:
            # no_overlapping_mandate_for_this_scope. Reported against
            # window_opens so the two window rules never collide on one field.
            line = payload.get("line_of_business")
            juris = payload.get("jurisdiction")
            for other in existing:
                if (other.get("line_of_business") != line
                        or other.get("jurisdiction") != juris):
                    continue
                o_opens = other.get("window_opens")
                o_closes = other.get("window_closes")
                if _as_date(o_opens) is None or _as_date(o_closes) is None:
                    continue
                if windows_overlap(opens, closes, o_opens, o_closes):
                    errors.append(FieldError("window_opens", copy.WINDOW_OVERLAP.format(
                        line_of_business=line, jurisdiction=juris,
                        existing_opens=o_opens, existing_closes=o_closes)))
                    break
    return errors
