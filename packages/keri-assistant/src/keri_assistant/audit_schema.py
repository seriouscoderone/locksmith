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
that silently deleted a legitimate command from a surface. The real corpus proves this out: the
actuary template alone has seven `product_id` fields plus a `thread_id`, and their own descriptions
say what they are — "Stable kebab-case product identifier", "the designer's negotiation thread" —
ordinary opaque identifiers, not credential references. Constraining every `_id` would have deleted
those legitimate commands from the surface. The settled fix is upstream — such a reference becomes a
self-issued ACDC chained by an ACDC **edge**, so it has a SAID by construction and grounding becomes
semantic (do I hold this credential?) rather than lexical. Rationale and scope: the ugard backlog item
dated 2026-07-30 on self-issued-ACDC references chained by edge.

So `unconstrained_entity_fields` does NOT guess. It lists every required free-string field no rule
constrains, so the gap is visible rather than silently absent. But on the real corpus that list runs
to dozens of rows — timestamps, dates, prose, ordinary identifiers — of which only a handful are
genuine credential references. Nobody reads a 55-row list to find the one live defect, so a plain
listing delivers the form of visibility without the substance.

`claimed_credential_refs` narrows that same list to the evidence the template ALREADY carries — this
is literally how the original `application_id` defect was found: by reading the field's own
description, not by guessing from its name. Two independent signals, because they have different
blind spots and neither alone covers the corpus:

  (A) the field's own `description` names a SAID, digest, or self-addressing identifier outright.
  (B) an undescribed field shares its leaf name with an (A) hit elsewhere in the same surface — the
      same reference, named the same way, just missing the prose this time.

Signal B is the interesting half: a template author who wrote a good description on one command and
then reused the field name on a sibling command (without repeating the prose) still gets caught. A
credential reference with NEITHER a claiming description NOR a claiming twin is caught by neither
signal — that residual gap is exactly why the upstream ACDC-edge fix, not a smarter detector here, is
the real fix. `claimed_credential_refs` is a strict filter over `unconstrained_entity_fields`'s own
candidates (never a widening): a field already reached by `grounded_set_for` (e.g. a `*_said` field)
never becomes a candidate in the first place, so it is never reported here either, no matter what its
description claims.
"""
from __future__ import annotations

import re

from .actionschema import grounded_set_for
from .grounding import Grounding
from .surface import CommandSurface

_SAID_CLAIM = re.compile(r"\bSAID\b|self-addressing|\bdigest\b", re.IGNORECASE)


def _walk(node: dict, grounding: Grounding, prefix: str) -> list[tuple[str, dict]]:
    if not isinstance(node, dict):
        return []
    found: list[tuple[str, dict]] = []
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
            found.append((path, sub))
    return found


def _candidates(surface: CommandSurface, grounding: Grounding) -> list[tuple[str, str, dict]]:
    """(verb_id, field_path, field_schema) for every exchange verb's unconstrained candidates."""
    out: list[tuple[str, str, dict]] = []
    for verb in surface.verbs:
        if verb.kind != "exchange":
            continue
        for path, schema in _walk(verb.payload_schema, grounding, ""):
            out.append((verb.id, path, schema))
    out.sort(key=lambda c: (c[0], c[1]))
    return out


def _claims_a_said(schema: dict) -> bool:
    return bool(_SAID_CLAIM.search(schema.get("description") or ""))


def unconstrained_entity_fields(
    surface: CommandSurface, grounding: Grounding
) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((verb_id, path) for verb_id, path, _schema in _candidates(surface, grounding)))


def claimed_credential_refs(
    surface: CommandSurface, grounding: Grounding
) -> tuple[tuple[str, str, str], ...]:
    """Of `unconstrained_entity_fields`'s candidates, which ones the TEMPLATE ITSELF claims are
    credential references — sorted `(verb_id, field_path, reason)`. See module docstring."""
    candidates = _candidates(surface, grounding)

    # First pass: every signal-A hit, indexed by leaf name (the property's own local name, not its
    # full dotted path — a sibling command's field at a different nesting depth still counts as
    # "the same name"). `setdefault` keeps the first hit per leaf under (verb_id, path) sort order,
    # so the reason text is deterministic even when more than one command describes the same name.
    origin_by_leaf: dict[str, tuple[str, str]] = {}
    for verb_id, path, schema in candidates:
        if _claims_a_said(schema):
            origin_by_leaf.setdefault(path.rsplit(".", 1)[-1], (verb_id, path))

    out: list[tuple[str, str, str]] = []
    for verb_id, path, schema in candidates:
        if _claims_a_said(schema):
            out.append((verb_id, path, "described as a SAID"))
            continue
        origin = origin_by_leaf.get(path.rsplit(".", 1)[-1])
        if origin is not None and origin != (verb_id, path):
            out.append((verb_id, path,
                        f"shares a name with {origin[0]}.{origin[1]}, which is described as a SAID"))

    return tuple(sorted(out))
