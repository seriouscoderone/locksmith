"""Compile the grounded proposal schema — the genuinely-custom piece of Phase 2.

CommandSurface + Grounding -> a JSON-Schema whose command is a `oneOf` of const-tagged
alternatives and whose world-naming parameters (receiver AID, credential schema SAID) are
restricted to currently-grounded values. Handed to a backend that compiles JSON-Schema into a
sampler-level grammar, an ungrounded action becomes IMPOSSIBLE to emit rather than merely
invalid. Only `kind == "exchange"` verbs are proposable; reads are loop tools. Escape hatches
are first-class alternatives so the grammar always has a truthful out. See design spec 4.1/8.1.
"""
from __future__ import annotations

import copy

from .grounding import Grounding
from .neververbs import is_never_verb
from .surface import CommandSurface, Verb

CLARIFY = "__clarify__"
UNSUPPORTED = "__unsupported__"
MAX_TEXT = 200

# Composition/reference constructs we do not attempt to ground. An adversarial review proved
# (with a `jsonschema` oracle) that a payload using any of these lets an ungrounded entity value
# validate through untouched, so a node using one is NOT "left alone" — it fails closed (the
# containing verb is omitted). Closing this for real needs a decision about composition semantics
# (does an `allOf` branch's `required` bind at the branch or the parent? do multiple `oneOf`/
# `anyOf` branches' `properties` merge before or after grounding?) that hasn't been made yet.
#
# `prefixItems` (the 2020-12 spelling of tuple-form `items`) belongs here for the same reason:
# we only ever recurse into `items`, so a `prefixItems` array passed through UNGROUNDED while
# `allOf`/`$ref` failed closed right next to it — an inconsistent policy that is worse than
# either choice. Fail closed until it gets the same tuple-form handling `items` already has.
_UNSUPPORTED_CONSTRUCTS = (
    "$ref", "$defs", "patternProperties", "oneOf", "anyOf", "allOf", "prefixItems",
)


def grounded_set_for(prop_name: str, grounding: Grounding) -> frozenset[str] | None:
    """Which grounded set constrains this payload property, by naming convention.

    PUBLIC: `proposal.parse_proposal` reuses this so the schema constraint and the belt-and-braces
    re-validation can never drift apart.

    Convention (not annotation) is deliberate and temporary: the template spec has no field-level
    entity annotation yet, so `*_aid` / `*_said` naming is what we have. Fragile but closes a real
    hole today; replace with a declared annotation when the template spec gains one.

    `schema_said` is checked before the generic `_said` suffix so `credential_schema_said` (or
    any other `*schema_said`) routes to `allowed_schema_saids`, not `known_credential_saids` —
    `endswith("_said")` alone would have matched it first.
    """
    name = prop_name.lower()
    if name.endswith("schema_said"):
        return grounding.allowed_schema_saids
    if name == "said" or name.endswith("_said"):
        return grounding.known_credential_saids
    if name == "aid" or name.endswith("_aid"):
        return grounding.known_aids
    return None


def _grounded_subschema(subschema, grounding: Grounding, pinned_schema_said: str | None):
    """Ground one `properties`/`items` member found by structural position, not by name.

    A subschema found this way is walked for entity fields nested *inside* it — it is never
    itself enum-constrained by its own name (only members of ITS `properties`/`items` can match
    `grounded_set_for`). Non-dict schema forms (e.g. a bare `true`/`false` schema) pass through
    unchanged — there is nothing to walk.
    """
    if not isinstance(subschema, dict):
        return subschema
    return _ground_node(subschema, grounding, pinned_schema_said)


def _ground_node(schema: dict, grounding: Grounding, pinned_schema_said: str | None) -> dict | None:
    """Copy `schema`, enum-constraining entity-naming fields at any depth under `properties`/
    `items`. None => unsatisfiable / unrepresentable: either a REQUIRED entity field (at this
    level or nested inside it) has nothing grounded, or this node uses a construct we cannot
    safely constrain at all (see `_UNSUPPORTED_CONSTRUCTS`, and the `additionalProperties` check
    below) — both fail closed, never silently pass an ungrounded value through.

    Recurses through exactly two constructs, matching the corpus: `properties` (each value is a
    subschema) and `items` (a single subschema, or the JSON-Schema tuple form — a list of
    subschemas).
    """
    if any(construct in schema for construct in _UNSUPPORTED_CONSTRUCTS):
        return None  # composition/reference schema -> fail closed, not guessed at

    node = dict(schema)  # never mutate the caller's dict — copy every level we touch

    # A value constraint (`enum`/`const`), not an object -- leave it untouched. Placed AFTER the
    # unsupported-construct check (so fail-closed still wins over it), but BEFORE the is-object
    # test below: that test alone would treat an untyped `enum`/`const` leaf as "could be an
    # object" and force it closed, producing a hybrid `{"enum": [...], "properties": {},
    # "additionalProperties": false}` node. That's a no-op for a validator (object keywords on a
    # non-object instance are simply ignored, which is why nothing failed), but our consumer is a
    # backend that compiles JSON-Schema into GBNF, which has open bugs on unusual shapes (e.g.
    # ggml-org/llama.cpp#25923: an empty-object schema emits invalid GBNF and breaks the WHOLE
    # grammar, not just this branch) — emitting a novel hybrid shape for no semantic benefit is a
    # bad trade. Grounded entity fields are unaffected: `grounded_set_for` matches those by NAME
    # in the parent's `properties` loop and overwrites them with a fresh `{"enum": [...]}` without
    # ever routing the field's own original subschema through `_ground_node`.
    if "enum" in node or "const" in node:
        return node

    # Treat a node as an object UNLESS it provably is not one. An adversarial review proved (with
    # a `jsonschema` oracle) that the previous test — object only if `type: object`, or
    # `properties`/`additionalProperties` present — let an ungrounded entity value validate
    # through UNTOUCHED whenever a node omitted all three (`{"description": "..."}`,
    # `{"minProperties": 1}`, `{"title": "P"}`, `{"required": ["amount"]}`, ...): nothing in JSON
    # Schema stops such a node from also being an object with any extra properties. A declared
    # `type` that is (or includes, in union form) "object" is still an object; a declared type
    # that is anything else definitely is not; the absence of `type` is NOT proof of non-object,
    # so it defaults to "could be" -> force closed rather than guess.
    declared = node.get("type")
    is_object = declared is None or declared == "object" or (
        isinstance(declared, list) and "object" in declared
    )
    if is_object:
        # Force the payload closed. An object left open (`additionalProperties: true`, or a
        # schema author who never bothered saying `false`) accepts ANY extra key with ANY value
        # — including one with an entity-field name our enum-constraining below never sees,
        # because it isn't declared in `properties` at all. Absent -> default closed (safe,
        # silent). Explicitly open -> we cannot retroactively enumerate what it might contain,
        # so fail closed (omit the verb) rather than silently rewriting the author's schema.
        if node.setdefault("additionalProperties", False) is not False:
            return None
        properties = dict(node.get("properties", {}))
        required = list(node.get("required", []))
        for prop_name in list(properties):
            subschema = properties[prop_name]
            allowed = grounded_set_for(prop_name, grounding)
            if allowed is not None:
                if pinned_schema_said is not None and prop_name.lower().endswith("schema_said"):
                    # This verb's own credential schema is already pinned (and was already
                    # confirmed grounded before we got here) — a payload field naming "which
                    # schema" must match THAT schema exactly, not any grounded schema.
                    properties[prop_name] = {"const": pinned_schema_said}
                    continue
                if allowed:
                    properties[prop_name] = {"enum": sorted(allowed)}
                    continue
                if prop_name in required:
                    return None  # required entity field with nothing grounded -> unsatisfiable
                del properties[prop_name]  # optional and ungroundable -> not emittable at all
                required = [r for r in required if r != prop_name]
                continue
            # not an entity field itself — but it may contain one, so walk its shape.
            grounded_sub = _grounded_subschema(subschema, grounding, pinned_schema_said)
            if grounded_sub is None:
                if prop_name in required:
                    return None  # a nested required entity field is ungroundable -> unsatisfiable
                del properties[prop_name]  # optional -> the whole ungroundable shape drops
                required = [r for r in required if r != prop_name]
                continue
            properties[prop_name] = grounded_sub
        node["properties"] = properties
        if required:
            node["required"] = required
        elif "required" in node:
            del node["required"]  # never emit an empty `required` — invalid in draft-04

    if "items" in node:
        items = node["items"]
        if isinstance(items, list):  # tuple form: positional per-item subschemas
            grounded_items = []
            for item_schema in items:
                grounded_item = _grounded_subschema(item_schema, grounding, pinned_schema_said)
                if grounded_item is None:
                    return None  # one tuple slot unsatisfiable -> the whole array is
                grounded_items.append(grounded_item)
            node["items"] = grounded_items
        else:  # single subschema applies to every array element
            grounded_items = _grounded_subschema(items, grounding, pinned_schema_said)
            if grounded_items is None:
                return None  # every element must satisfy this -> the array can never be satisfied
            node["items"] = grounded_items

    return node


def _ground_payload(
    payload_schema: dict, grounding: Grounding, pinned_schema_said: str | None = None
) -> dict | None:
    """Copy the payload schema, enum-constraining entity-naming fields. None => unsatisfiable.

    Deep-copies up front: `_ground_node` only shallow-copies each dict LEVEL it recurses through
    (`properties`/`items`), so a leaf's own list/dict VALUES (an `enum`, a nested keyword we never
    walk) would otherwise still be the SAME objects as the template's. Mutating a compiled
    schema's leaf in place (or a caller simply holding onto it) would then permanently rewrite
    `Verb.payload_schema` and the source template, widening what every LATER compilation in the
    process grounds. A deep copy here means nothing downstream can alias the template at all.
    """
    schema = copy.deepcopy(payload_schema) or {"type": "object"}
    return _ground_node(schema, grounding, pinned_schema_said)


def verb_alternative(verb: Verb, grounding: Grounding) -> dict | None:
    """One `oneOf` branch, or None when this verb cannot be satisfied under this grounding.

    PUBLIC: `proposal.parse_proposal` re-derives the same branch (or its absence) as
    belt-and-braces, so a future compiler change can never silently leave layer 2 (the
    re-validation) behind layer 1 (the compiled grammar) — both read this one decision.
    """
    props: dict = {"verb_id": {"const": verb.id}}
    required = ["verb_id"]

    if verb.counterparty_role is not None:
        aids = sorted(grounding.known_aids)
        if not aids:
            return None  # no grounded recipient -> omit the alternative entirely
        props["receiver_aid"] = {"enum": aids}
        required.append("receiver_aid")

    if verb.schema_said is not None:
        if verb.schema_said not in grounding.allowed_schema_saids:
            return None  # the verb's own credential schema is not grounded -> omit
        props["schema_said"] = {"const": verb.schema_said}
        required.append("schema_said")

    payload = _ground_payload(verb.payload_schema, grounding, verb.schema_said)
    if payload is None:
        return None  # a REQUIRED payload entity field cannot be grounded -> verb unreachable
    props["payload"] = payload
    required.append("payload")

    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _text_alternative(verb_id: str, field: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "verb_id": {"const": verb_id},
            field: {"type": "string", "minLength": 1, "maxLength": MAX_TEXT},
        },
        "required": ["verb_id", field],
        "additionalProperties": False,
    }


def build_proposal_schema(surface: CommandSurface, grounding: Grounding) -> dict:
    alternatives: list[dict] = []
    seen_ids: set[str] = set()

    for verb in surface.verbs:
        if verb.kind != "exchange":
            continue  # reads are loop tools (Phase 2B), not proposals
        # Defense in depth: the surface builder already excluded never-verbs.
        if is_never_verb(verb.route):
            raise ValueError(f"never-verb reached schema: {verb.route}")
        if verb.id.startswith("__"):
            continue  # reserved for escape hatches — a template verb cannot claim this namespace
        if verb.id in seen_ids:
            # Two commands sharing an id would compile to two satisfiable `oneOf` branches with
            # the same `verb_id` const, so it would stop discriminating — `parse_proposal`
            # dispatches on `verb_id`, so this is a template defect, not something to paper over.
            raise ValueError(f"duplicate verb id: {verb.id!r}")
        seen_ids.add(verb.id)
        alternative = verb_alternative(verb, grounding)
        if alternative is not None:
            alternatives.append(alternative)

    # Always reachable: without a truthful out the model is forced to pick a wrong command.
    alternatives.append(_text_alternative(CLARIFY, "question"))
    alternatives.append(_text_alternative(UNSUPPORTED, "reason"))

    return {"oneOf": alternatives}
