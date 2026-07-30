"""Compile the grounded proposal schema — the genuinely-custom piece of Phase 2.

CommandSurface + Grounding -> a JSON-Schema whose command is a `oneOf` of const-tagged
alternatives and whose world-naming parameters (receiver AID, credential schema SAID) are
restricted to currently-grounded values. Handed to a backend that compiles JSON-Schema into a
sampler-level grammar, an ungrounded action becomes IMPOSSIBLE to emit rather than merely
invalid. Only `kind == "exchange"` verbs are proposable; reads are loop tools. Escape hatches
are first-class alternatives so the grammar always has a truthful out. See design spec 4.1/8.1.
"""
from __future__ import annotations

from .grounding import Grounding
from .neververbs import is_never_verb
from .surface import CommandSurface, Verb

CLARIFY = "__clarify__"
UNSUPPORTED = "__unsupported__"
MAX_TEXT = 200


def grounded_set_for(prop_name: str, grounding: Grounding) -> frozenset[str] | None:
    """Which grounded set constrains this payload property, by naming convention.

    PUBLIC: `proposal.parse_proposal` reuses this so the schema constraint and the belt-and-braces
    re-validation can never drift apart.

    Convention (not annotation) is deliberate and temporary: the template spec has no field-level
    entity annotation yet, so `*_aid` / `*_said` naming is what we have. Fragile but closes a real
    hole today; replace with a declared annotation when the template spec gains one.
    """
    name = prop_name.lower()
    if name == "schema_said":
        return grounding.allowed_schema_saids
    if name == "said" or name.endswith("_said"):
        return grounding.known_credential_saids
    if name == "aid" or name.endswith("_aid"):
        return grounding.known_aids
    return None


def _grounded_subschema(subschema, grounding: Grounding):
    """Ground one `properties`/`items` member found by structural position, not by name.

    A subschema found this way is walked for entity fields nested *inside* it — it is never
    itself enum-constrained by its own name (only members of ITS `properties`/`items` can match
    `grounded_set_for`). Non-dict schema forms (e.g. a bare `true`/`false` schema) pass through
    unchanged — there is nothing to walk.
    """
    if not isinstance(subschema, dict):
        return subschema
    return _ground_node(subschema, grounding)


def _ground_node(schema: dict, grounding: Grounding) -> dict | None:
    """Copy `schema`, enum-constraining entity-naming fields at any depth under `properties`/
    `items`. None => unsatisfiable: a REQUIRED entity field, at this level or nested inside it,
    has nothing grounded.

    Recurses through exactly two constructs, matching the corpus: `properties` (each value is a
    subschema) and `items` (a single subschema, or the JSON-Schema tuple form — a list of
    subschemas). `allOf`/`oneOf`/`anyOf`/`patternProperties`/`$ref` are a documented, deliberate
    gap — see `test_allOf_declared_entity_fields_are_a_KNOWN_gap_not_grounded`.
    """
    node = dict(schema)  # never mutate the caller's dict — copy every level we touch

    if "properties" in node:
        properties = dict(node["properties"])
        required = list(node.get("required", []))
        for prop_name in list(properties):
            subschema = properties[prop_name]
            allowed = grounded_set_for(prop_name, grounding)
            if allowed is not None:
                # entity-naming leaf: enum-constrain or drop outright, never recurse into it.
                if allowed:
                    properties[prop_name] = {"enum": sorted(allowed)}
                    continue
                if prop_name in required:
                    return None  # required entity field with nothing grounded -> unsatisfiable
                del properties[prop_name]  # optional and ungroundable -> not emittable at all
                continue
            # not an entity field itself — but it may contain one, so walk its shape.
            grounded_sub = _grounded_subschema(subschema, grounding)
            if grounded_sub is None:
                if prop_name in required:
                    return None  # a nested required entity field is ungroundable -> unsatisfiable
                del properties[prop_name]  # optional -> the whole ungroundable shape drops
                continue
            properties[prop_name] = grounded_sub
        node["properties"] = properties
        if required:
            node["required"] = [r for r in required if r in properties]

    if "items" in node:
        items = node["items"]
        if isinstance(items, list):  # tuple form: positional per-item subschemas
            grounded_items = []
            for item_schema in items:
                grounded_item = _grounded_subschema(item_schema, grounding)
                if grounded_item is None:
                    return None  # one tuple slot unsatisfiable -> the whole array is
                grounded_items.append(grounded_item)
            node["items"] = grounded_items
        else:  # single subschema applies to every array element
            grounded_items = _grounded_subschema(items, grounding)
            if grounded_items is None:
                return None  # every element must satisfy this -> the array can never be satisfied
            node["items"] = grounded_items

    return node


def _ground_payload(payload_schema: dict, grounding: Grounding) -> dict | None:
    """Copy the payload schema, enum-constraining entity-naming fields. None => unsatisfiable."""
    schema = dict(payload_schema) or {"type": "object"}
    return _ground_node(schema, grounding)


def _verb_alternative(verb: Verb, grounding: Grounding) -> dict | None:
    """One `oneOf` branch, or None when this verb cannot be satisfied under this grounding."""
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

    payload = _ground_payload(verb.payload_schema, grounding)
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
            field: {"type": "string", "maxLength": MAX_TEXT},
        },
        "required": ["verb_id", field],
        "additionalProperties": False,
    }


def build_proposal_schema(surface: CommandSurface, grounding: Grounding) -> dict:
    alternatives: list[dict] = []

    for verb in surface.verbs:
        if verb.kind != "exchange":
            continue  # reads are loop tools (Phase 2B), not proposals
        # Defense in depth: the surface builder already excluded never-verbs.
        assert not is_never_verb(verb.route), f"never-verb reached schema: {verb.route}"
        alternative = _verb_alternative(verb, grounding)
        if alternative is not None:
            alternatives.append(alternative)

    # Always reachable: without a truthful out the model is forced to pick a wrong command.
    alternatives.append(_text_alternative(CLARIFY, "question"))
    alternatives.append(_text_alternative(UNSUPPORTED, "reason"))

    return {"oneOf": alternatives}
