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


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return True


def windows_overlap(a_opens: str, a_closes: str,
                    b_opens: str, b_closes: str) -> bool:
    """The standard inclusive interval test, on ISO strings.

    ISO-8601 dates sort lexicographically, so string comparison IS the check --
    the same property the template's rules rely on. Touching endpoints overlap:
    both dates count as in force.
    """
    return a_opens <= b_closes and b_opens <= a_closes


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
    if c.fmt == "date" and not _is_iso_date(text):
        out.append(copy.date_error(c.name))
    return out


def _array_errors(c: FieldConstraints, value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return [copy.required_error(c.name)]
    items = list(value)
    out: list[str] = []
    if c.min_items is not None and len(items) < c.min_items:
        out.append(copy.required_error(c.name))
    if c.unique_items:
        seen: set[str] = set()
        for item in items:
            if item in seen:
                out.append(copy.COVERAGE_DUPLICATE.format(code=item))
                break
            seen.add(item)
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

    already = {e.field for e in errors}
    opens, closes = payload.get("window_opens"), payload.get("window_closes")
    both_are_dates = (isinstance(opens, str) and isinstance(closes, str)
                      and _is_iso_date(opens) and _is_iso_date(closes))
    if both_are_dates and "window_closes" not in already:
        # mandate_window_opens_before_it_closes -- STRICT, so equal dates fail.
        if not opens < closes:
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
                o_opens = str(other.get("window_opens") or "")
                o_closes = str(other.get("window_closes") or "")
                if not (o_opens and o_closes):
                    continue
                if windows_overlap(opens, closes, o_opens, o_closes):
                    errors.append(FieldError("window_opens", copy.WINDOW_OVERLAP.format(
                        line_of_business=line, jurisdiction=juris,
                        existing_opens=o_opens, existing_closes=o_closes)))
                    break
    return errors
