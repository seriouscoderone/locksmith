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


def _ground_payload(payload_schema: dict, grounding: Grounding) -> dict | None:
    """Copy the payload schema, enum-constraining entity-naming fields. None => unsatisfiable."""
    schema = dict(payload_schema) or {"type": "object"}
    properties = dict(schema.get("properties", {}))
    required = list(schema.get("required", []))
    if not properties:
        return schema

    for prop_name in list(properties):
        allowed = grounded_set_for(prop_name, grounding)
        if allowed is None:
            continue  # not an entity field — leave the author's schema alone
        if allowed:
            properties[prop_name] = {"enum": sorted(allowed)}
        elif prop_name in required:
            return None  # required entity field with nothing grounded -> omit the whole verb
        else:
            del properties[prop_name]  # optional and ungroundable -> not emittable at all

    schema["properties"] = properties
    if required:
        schema["required"] = [r for r in required if r in properties]
    return schema


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
