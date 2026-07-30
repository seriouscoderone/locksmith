"""Report payload fields the grounding cannot reach — visibility, not enforcement.

Phase 2A's review found a required payload field that was a plain string, yet whose own description
declared it to be the SAID of another credential. A model can invent such a value and a human then
signs an authority-bearing action referencing something that does not exist. A scan of the real corpus
found three such misses in three different naming shapes: a `<noun>_id` suffix, a **plural** `_saids`,
and a field named `ref` documented as "SAID *or* locator". The plural is the decisive one — an author
who was FOLLOWING the `*_said` convention was still missed, because the natural plural escapes it. So
naming is structurally the wrong mechanism, not merely an imperfect one.

Widening the `*_aid`/`*_said` convention to `_id` was rejected: `_id` suffixes are overwhelmingly
ordinary opaque identifiers, so constraining them all would repeat the over-broad never-verb error
that silently deleted a legitimate command from a surface. The settled fix is upstream — such a
reference becomes a self-issued ACDC chained by an ACDC **edge**, so it has a SAID by construction and
grounding becomes semantic (do I hold this credential?) rather than lexical. Rationale and scope: the
ugard backlog item dated 2026-07-30 on self-issued-ACDC references chained by edge.

So this module does NOT guess. It lists required free-string fields no rule constrains, so template
review and an eval gate can see the gap instead of it being silently absent. A field named `ref` that
may legitimately hold either a SAID or a locator cannot be enum-constrained by any mechanism; that is
a template-design problem, and reporting it is the correct response.
"""
from __future__ import annotations

from .actionschema import grounded_set_for
from .grounding import Grounding
from .surface import CommandSurface


def _walk(node: dict, grounding: Grounding, prefix: str) -> list[str]:
    if not isinstance(node, dict):
        return []
    found: list[str] = []
    required = set(node.get("required", []))
    for name, sub in (node.get("properties") or {}).items():
        if name not in required:
            continue  # only a required field can force a signature over an invented value
        path = f"{prefix}{name}"
        if grounded_set_for(name, grounding) is not None:
            continue  # a rule already reaches this field
        if isinstance(sub, dict) and (sub.get("properties") or sub.get("type") == "object"):
            found.extend(_walk(sub, grounding, f"{path}."))
        elif isinstance(sub, dict) and sub.get("type") == "string" and "enum" not in sub:
            found.append(path)
    return found


def unconstrained_entity_fields(
    surface: CommandSurface, grounding: Grounding
) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    for verb in surface.verbs:
        if verb.kind != "exchange":
            continue
        for path in _walk(verb.payload_schema, grounding, ""):
            out.append((verb.id, path))
    return tuple(sorted(out))
