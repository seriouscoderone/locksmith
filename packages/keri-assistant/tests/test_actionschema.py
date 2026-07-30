import copy

import pytest

from keri_assistant.actionschema import (
    CLARIFY,
    MAX_TEXT,
    UNSUPPORTED,
    build_proposal_schema,
    grounded_set_for,
)
from keri_assistant.grounding import Grounding
from keri_assistant.surface import CommandSurface, Verb, build_micro_app_surface
from tests.fixtures.sample_template import SAMPLE_TEMPLATE

SURF = build_micro_app_surface(SAMPLE_TEMPLATE)
BROKER = "EBroker000000000000000000000000000000000000"
QUOTE = "ESchemaQuote0000000000000000000000000000000"
G = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}))


def _alts(schema):
    return {a["properties"]["verb_id"]["const"]: a for a in schema["oneOf"]}


def test_exchange_verbs_and_escape_hatches_are_alternatives():
    # create_application (SAMPLE_TEMPLATE) declares `additionalProperties: true` — an open
    # payload is now correctly omitted rather than emitted with an ungroundable escape hatch of
    # its own; see test_shipped_open_payload_fixture_create_application_is_omitted below.
    alts = _alts(build_proposal_schema(SURF, G))
    assert set(alts) == {"submit_quote", CLARIFY, UNSUPPORTED}


def test_query_verbs_are_not_proposable():
    # reads are loop tools (Phase 2B), never proposals
    assert "issued_credentials" not in _alts(build_proposal_schema(SURF, G))


def test_receiver_aid_is_enum_restricted_to_grounded_aids():
    alt = _alts(build_proposal_schema(SURF, G))["submit_quote"]
    assert alt["properties"]["receiver_aid"] == {"enum": [BROKER]}
    assert "receiver_aid" in alt["required"]


def test_schema_said_is_pinned_const_not_a_model_choice():
    alt = _alts(build_proposal_schema(SURF, G))["submit_quote"]
    assert alt["properties"]["schema_said"] == {"const": QUOTE}


# create_application (SAMPLE_TEMPLATE) can no longer stand in for "a verb with no counterparty":
# its `additionalProperties: true` payload is now (correctly) omitted entirely. Use a local,
# closed-payload verb pair instead so the receiver-field guarantees below still get exercised.
RECEIVER_AND_NO_RECEIVER_TEMPLATE = {
    "commands": [
        {
            "id": "needs_receiver", "name": "needs receiver",
            "route": "/insurance/cmd/needs_receiver",
            "counterparty_role": "broker", "authz": {"method": "open"},
            "payload_schema": {"type": "object", "additionalProperties": False, "properties": {}},
        },
        {
            "id": "no_receiver", "name": "no receiver", "route": "/insurance/cmd/no_receiver",
            "counterparty_role": None, "authz": {"method": "open"},
            "payload_schema": {"type": "object", "additionalProperties": False, "properties": {}},
        },
    ],
}
RSURF = build_micro_app_surface(RECEIVER_AND_NO_RECEIVER_TEMPLATE)


def test_verb_without_counterparty_has_no_receiver_field():
    alt = _alts(build_proposal_schema(RSURF, G))["no_receiver"]
    assert "receiver_aid" not in alt["properties"]
    assert "schema_said" not in alt["properties"]


def test_payload_schema_is_carried_through():
    alt = _alts(build_proposal_schema(SURF, G))["submit_quote"]
    assert alt["properties"]["payload"]["properties"]["amount"] == {"type": "number"}


# --- payload-level grounding (the `holder_aid` hole the real regulator template exposed) ---

PAYLOAD_TEMPLATE = {
    "commands": [{
        "id": "grant_license", "name": "grant license", "route": "/insurance/cmd/grant_license",
        "counterparty_role": "carrier", "authz": {"method": "open"},
        "payload_schema": {"type": "object", "additionalProperties": False,
                           "required": ["holder_aid", "jurisdiction"],
                           "properties": {"holder_aid": {"type": "string"},
                                          "jurisdiction": {"type": "string"},
                                          "prior_said": {"type": "string"}}},
    }],
}
PSURF = build_micro_app_surface(PAYLOAD_TEMPLATE)
LIC = "ELicense00000000000000000000000000000000000"


def test_payload_aid_field_is_enum_constrained_to_grounded_aids():
    alt = _alts(build_proposal_schema(PSURF, G))["grant_license"]
    assert alt["properties"]["payload"]["properties"]["holder_aid"] == {"enum": [BROKER]}


def test_non_entity_payload_fields_are_untouched():
    alt = _alts(build_proposal_schema(PSURF, G))["grant_license"]
    assert alt["properties"]["payload"]["properties"]["jurisdiction"] == {"type": "string"}


def test_optional_payload_said_field_is_dropped_when_nothing_is_grounded():
    # prior_said is optional and no credential SAIDs are grounded -> remove the field entirely
    alt = _alts(build_proposal_schema(PSURF, G))["grant_license"]
    assert "prior_said" not in alt["properties"]["payload"]["properties"]


def test_optional_payload_said_field_is_constrained_when_grounded():
    g = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}),
                  known_credential_saids=frozenset({LIC}))
    alt = _alts(build_proposal_schema(PSURF, g))["grant_license"]
    assert alt["properties"]["payload"]["properties"]["prior_said"] == {"enum": [LIC]}


def test_verb_is_omitted_when_a_REQUIRED_payload_aid_cannot_be_grounded():
    none_aids = Grounding(known_aids=frozenset(), allowed_schema_saids=frozenset({QUOTE}))
    assert "grant_license" not in _alts(build_proposal_schema(PSURF, none_aids))


def test_alternatives_forbid_extra_properties():
    for alt in build_proposal_schema(SURF, G)["oneOf"]:
        assert alt["additionalProperties"] is False


def test_verb_needing_a_receiver_is_OMITTED_when_no_aid_is_grounded():
    # never emit an empty enum: the alternative must be absent, not unsatisfiable
    empty = Grounding(known_aids=frozenset(), allowed_schema_saids=frozenset({QUOTE}))
    alts = _alts(build_proposal_schema(RSURF, empty))
    assert "needs_receiver" not in alts
    assert "no_receiver" in alts                 # needs no receiver, still reachable


def test_verb_is_OMITTED_when_its_own_schema_said_is_not_grounded():
    nosch = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset())
    alts = _alts(build_proposal_schema(SURF, nosch))
    assert "submit_quote" not in alts


def test_escape_hatches_always_present_even_with_no_grounding_at_all():
    none_g = Grounding(known_aids=frozenset(), allowed_schema_saids=frozenset())
    alts = _alts(build_proposal_schema(SURF, none_g))
    assert CLARIFY in alts and UNSUPPORTED in alts


def test_escape_hatch_text_is_length_bounded():
    alts = _alts(build_proposal_schema(SURF, G))
    assert alts[CLARIFY]["properties"]["question"]["maxLength"] == 200
    assert alts[UNSUPPORTED]["properties"]["reason"]["maxLength"] == 200


# --- recursive payload grounding: nested object / array-of-objects / allOf boundary ---
# `_ground_payload` used to walk only the top level of `properties`, so an entity field one
# level down (a nested object, or inside `items` of an array) escaped grounding entirely. See
# ugard/docs/micro-apps/actuary-attests-product-rating's `ingest_rate_workbook`, whose real
# commitment (`shards.items.properties.shard_said`) sat behind exactly this hole.

NESTED_OBJECT_TEMPLATE = {
    "commands": [{
        "id": "wrap_holder", "name": "wrap holder", "route": "/insurance/cmd/wrap_holder",
        "authz": {"method": "open"},
        "payload_schema": {
            "type": "object", "additionalProperties": False,
            "required": ["wrapper"],
            "properties": {
                "wrapper": {
                    "type": "object", "additionalProperties": False,
                    "required": ["holder_aid"],
                    "properties": {
                        "holder_aid": {"type": "string"},
                        "jurisdiction": {"type": "string"},
                    },
                },
            },
        },
    }],
}
NSURF = build_micro_app_surface(NESTED_OBJECT_TEMPLATE)

NESTED_OPTIONAL_TEMPLATE = {
    "commands": [{
        "id": "wrap_optional", "name": "wrap optional", "route": "/insurance/cmd/wrap_optional",
        "authz": {"method": "open"},
        "payload_schema": {
            "type": "object", "additionalProperties": False,
            "required": ["wrapper"],
            "properties": {
                "wrapper": {
                    "type": "object", "additionalProperties": False,
                    "required": ["jurisdiction"],
                    "properties": {
                        "jurisdiction": {"type": "string"},
                        "prior_said": {"type": "string"},
                    },
                },
            },
        },
    }],
}
NOSURF = build_micro_app_surface(NESTED_OPTIONAL_TEMPLATE)

ARRAY_TEMPLATE = {
    "commands": [{
        "id": "ingest_rate_workbook", "name": "ingest rate workbook",
        "route": "/insurance/cmd/ingest_rate_workbook", "authz": {"method": "open"},
        "payload_schema": {
            "type": "object", "additionalProperties": False,
            "required": ["shards"],
            "properties": {
                "shards": {
                    "type": "array", "minItems": 1,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["shard_name", "shard_said"],
                        "properties": {
                            "shard_name": {"type": "string"},
                            "shard_said": {"type": "string"},
                        },
                    },
                },
            },
        },
    }],
}
ASURF = build_micro_app_surface(ARRAY_TEMPLATE)
SHARD = "EShard00000000000000000000000000000000000000"

ALLOF_TEMPLATE = {
    "commands": [{
        "id": "allof_holder", "name": "allof holder", "route": "/insurance/cmd/allof_holder",
        "authz": {"method": "open"},
        "payload_schema": {
            "type": "object", "additionalProperties": False,
            "allOf": [
                {
                    "type": "object",
                    "required": ["holder_aid"],
                    "properties": {"holder_aid": {"type": "string"}},
                },
            ],
        },
    }],
}
ALLOFSURF = build_micro_app_surface(ALLOF_TEMPLATE)


def test_nested_object_required_aid_becomes_enum():
    alt = _alts(build_proposal_schema(NSURF, G))["wrap_holder"]
    wrapper = alt["properties"]["payload"]["properties"]["wrapper"]
    assert wrapper["properties"]["holder_aid"] == {"enum": [BROKER]}
    assert "holder_aid" in wrapper["required"]


def test_array_of_objects_nested_said_becomes_enum_when_grounded():
    g = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}),
                  known_credential_saids=frozenset({SHARD}))
    alt = _alts(build_proposal_schema(ASURF, g))["ingest_rate_workbook"]
    items = alt["properties"]["payload"]["properties"]["shards"]["items"]
    assert items["properties"]["shard_said"] == {"enum": [SHARD]}
    assert "shard_said" in items["required"]


def test_verb_omitted_when_nested_required_said_inside_array_cannot_be_grounded():
    # the real-corpus shape: G grounds no credential SAIDs at all, and shard_said is required
    # *inside* shards.items -> the verb must be OMITTED, not emitted with an empty/missing enum.
    alts = _alts(build_proposal_schema(ASURF, G))
    assert "ingest_rate_workbook" not in alts
    assert CLARIFY in alts and UNSUPPORTED in alts


def test_optional_nested_entity_field_is_deleted_and_required_updated():
    alt = _alts(build_proposal_schema(NOSURF, G))["wrap_optional"]  # no credential SAIDs grounded
    wrapper = alt["properties"]["payload"]["properties"]["wrapper"]
    assert "prior_said" not in wrapper["properties"]
    assert wrapper["required"] == ["jurisdiction"]  # untouched entries survive the re-filter


def test_non_entity_nested_fields_are_untouched():
    alt = _alts(build_proposal_schema(NSURF, G))["wrap_holder"]
    assert alt["properties"]["payload"]["properties"]["wrapper"]["properties"]["jurisdiction"] == {
        "type": "string"
    }
    g = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}),
                  known_credential_saids=frozenset({SHARD}))
    items = _alts(build_proposal_schema(ASURF, g))["ingest_rate_workbook"][
        "properties"]["payload"]["properties"]["shards"]["items"]
    assert items["properties"]["shard_name"] == {"type": "string"}


def _find_empty_enums(node) -> list:
    """Recursively collect every `{"enum": []}` occurrence anywhere in a compiled schema."""
    hits: list = []
    if isinstance(node, dict):
        if node.get("enum") == []:
            hits.append(node)
        for value in node.values():
            hits.extend(_find_empty_enums(value))
    elif isinstance(node, list):
        for item in node:
            hits.extend(_find_empty_enums(item))
    return hits


def test_no_empty_enum_anywhere_under_empty_or_populated_grounding():
    empty = Grounding(known_aids=frozenset(), allowed_schema_saids=frozenset())
    populated = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}),
                          known_credential_saids=frozenset({LIC, SHARD}))
    for surf in (SURF, PSURF, NSURF, NOSURF, ASURF):
        for grounding in (empty, G, populated):
            assert _find_empty_enums(build_proposal_schema(surf, grounding)) == []


def test_compiling_does_not_mutate_input_and_is_idempotent():
    payload_before = copy.deepcopy(PAYLOAD_TEMPLATE)
    nested_before = copy.deepcopy(NESTED_OBJECT_TEMPLATE)
    array_before = copy.deepcopy(ARRAY_TEMPLATE)

    schema1 = build_proposal_schema(PSURF, G)
    schema2 = build_proposal_schema(PSURF, G)
    assert PAYLOAD_TEMPLATE == payload_before
    assert schema1 == schema2

    nested1 = build_proposal_schema(NSURF, G)
    nested2 = build_proposal_schema(NSURF, G)
    assert NESTED_OBJECT_TEMPLATE == nested_before
    assert nested1 == nested2

    g = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}),
                  known_credential_saids=frozenset({SHARD}))
    array1 = build_proposal_schema(ASURF, g)
    array2 = build_proposal_schema(ASURF, g)
    assert ARRAY_TEMPLATE == array_before
    assert array1 == array2


# --- fail-closed corrections from adversarial review ---
# An earlier version of this fix left `allOf`/`oneOf`/`anyOf`/`patternProperties`/`$ref` as a
# documented gap: the field would compile unconstrained but visible. A reviewer proved with a
# `jsonschema` oracle that this still lets an ungrounded entity value (e.g. an attacker-chosen
# AID) validate through — "documented" is not "safe". Composition semantics (does an `allOf`
# branch's `required` bind at the branch or the parent? how do multiple `oneOf`/`anyOf` branches'
# `properties` compose before grounding?) are still an undecided design question, so instead of
# guessing we fail closed: any node using one of these omits the whole containing verb.

PATTERNPROPS_TEMPLATE = {
    "commands": [{
        "id": "patternprops_holder", "name": "patternprops holder",
        "route": "/insurance/cmd/patternprops_holder", "authz": {"method": "open"},
        "payload_schema": {
            "type": "object", "additionalProperties": False, "properties": {},
            "patternProperties": {"^x_": {"type": "string"}},
        },
    }],
}
PATTERNPROPSSURF = build_micro_app_surface(PATTERNPROPS_TEMPLATE)

REF_TEMPLATE = {
    "commands": [{
        "id": "ref_holder", "name": "ref holder", "route": "/insurance/cmd/ref_holder",
        "authz": {"method": "open"},
        "payload_schema": {"$ref": "#/$defs/holder"},
    }],
}
REFSURF = build_micro_app_surface(REF_TEMPLATE)


def test_unsupported_composition_constructs_omit_the_verb():
    for surf, verb_id in (
        (ALLOFSURF, "allof_holder"),
        (PATTERNPROPSSURF, "patternprops_holder"),
        (REFSURF, "ref_holder"),
    ):
        alts = _alts(build_proposal_schema(surf, G))
        assert verb_id not in alts
        assert CLARIFY in alts and UNSUPPORTED in alts


def test_grounded_set_for_routes_schema_said_suffix_before_the_generic_said_suffix():
    # `credential_schema_said` ends with BOTH "_said" and "schema_said" — the more specific
    # match must win, or it would silently pin against the wrong grounded set.
    g = Grounding(known_aids=frozenset(), allowed_schema_saids=frozenset({QUOTE}),
                  known_credential_saids=frozenset({LIC}))
    assert grounded_set_for("credential_schema_said", g) == g.allowed_schema_saids
    assert grounded_set_for("credential_schema_said", g) != g.known_credential_saids


PINNED_SCHEMA_TEMPLATE = {
    "commands": [{
        "id": "attest_rating", "name": "attest rating", "route": "/insurance/cmd/attest_rating",
        "authz": {"method": "credential", "schema_said": QUOTE},
        "payload_schema": {
            "type": "object", "additionalProperties": False,
            "required": ["credential_schema_said"],
            "properties": {"credential_schema_said": {"type": "string"}},
        },
    }],
}
PINSURF = build_micro_app_surface(PINNED_SCHEMA_TEMPLATE)
OTHER_SCHEMA = "ESchemaOther00000000000000000000000000000000"


def test_payload_schema_said_field_is_pinned_to_verbs_own_schema_said():
    # two schema SAIDs are grounded, so a plain enum would let the model name EITHER one — but
    # this payload field names which schema the verb's OWN credential already commits to, so it
    # must be pinned exactly to that one, not left choosable among everything grounded.
    g = Grounding(known_aids=frozenset({BROKER}),
                  allowed_schema_saids=frozenset({QUOTE, OTHER_SCHEMA}))
    alt = _alts(build_proposal_schema(PINSURF, g))["attest_rating"]
    assert alt["properties"]["payload"]["properties"]["credential_schema_said"] == {"const": QUOTE}


def test_shipped_open_payload_fixture_create_application_is_omitted():
    # create_application's payload_schema declares additionalProperties: true (SAMPLE_TEMPLATE) —
    # it would accept {"holder_aid": "EVIL...", ...} unconstrained alongside/instead of anything
    # declared. An open payload can't be retroactively enumerated, so it fails closed.
    assert "create_application" not in _alts(build_proposal_schema(SURF, G))


IMPLICITLY_OPEN_TEMPLATE = {
    "commands": [{
        "id": "vague_note", "name": "vague note", "route": "/insurance/cmd/vague_note",
        "authz": {"method": "open"},
        "payload_schema": {},
    }],
}
IMPLICITSURF = build_micro_app_surface(IMPLICITLY_OPEN_TEMPLATE)


def test_absent_payload_schema_defaults_closed_not_omitted():
    # an author who never wrote a payload_schema at all gets the safe default (closed, empty
    # payload) rather than being punished with omission -- only an EXPLICIT `true` fails closed.
    alt = _alts(build_proposal_schema(IMPLICITSURF, G))["vague_note"]
    assert alt["properties"]["payload"]["additionalProperties"] is False


DUNDER_TEMPLATE = {
    "commands": [{
        "id": "__clarify__", "name": "shadow clarify", "route": "/insurance/cmd/shadow_clarify",
        "authz": {"method": "open"},
        "payload_schema": {"type": "object", "additionalProperties": False, "properties": {}},
    }],
}
DUNDERSURF = build_micro_app_surface(DUNDER_TEMPLATE)


def test_verb_id_starting_with_reserved_dunder_prefix_is_skipped():
    # a template verb literally named "__clarify__" must not shadow the escape hatch: two
    # satisfiable `oneOf` branches sharing a `verb_id` const would stop it from discriminating,
    # and Task 4's parse_proposal dispatches on verb_id.
    alts = _alts(build_proposal_schema(DUNDERSURF, G))
    assert set(alts) == {CLARIFY, UNSUPPORTED}
    assert alts[CLARIFY]["properties"]["verb_id"] == {"const": CLARIFY}


DUPLICATE_ID_TEMPLATE = {
    "commands": [
        {
            "id": "dup_verb", "name": "dup one", "route": "/insurance/cmd/dup_one",
            "authz": {"method": "open"},
            "payload_schema": {"type": "object", "additionalProperties": False, "properties": {}},
        },
        {
            "id": "dup_verb", "name": "dup two", "route": "/insurance/cmd/dup_two",
            "authz": {"method": "open"},
            "payload_schema": {"type": "object", "additionalProperties": False, "properties": {}},
        },
    ],
}
DUPSURF = build_micro_app_surface(DUPLICATE_ID_TEMPLATE)


def test_duplicate_verb_ids_raise_ValueError():
    with pytest.raises(ValueError):
        build_proposal_schema(DUPSURF, G)


def test_never_verb_reaching_build_proposal_schema_raises_not_asserts():
    # build_micro_app_surface already excludes never-verbs structurally; this is defense in
    # depth for a CommandSurface built some other way. A bare `assert` vanishes under `python
    # -O`, so it must be a real raise.
    rogue = CommandSurface(verbs=(
        Verb(id="rotate_key", route="/keri/cmd/rotate_key", phrasings=(), payload_schema={},
             kind="exchange"),
    ))
    with pytest.raises(ValueError):
        build_proposal_schema(rogue, G)


def test_escape_hatch_text_forbids_empty_string():
    alts = _alts(build_proposal_schema(SURF, G))
    assert alts[CLARIFY]["properties"]["question"]["minLength"] == 1
    assert alts[UNSUPPORTED]["properties"]["reason"]["minLength"] == 1


def _find_empty_required(node) -> list:
    """Recursively collect every empty `"required": []` occurrence anywhere in a compiled schema."""
    hits: list = []
    if isinstance(node, dict):
        if node.get("required") == []:
            hits.append(node)
        for value in node.values():
            hits.extend(_find_empty_required(value))
    elif isinstance(node, list):
        for item in node:
            hits.extend(_find_empty_required(item))
    return hits


def test_no_empty_required_list_anywhere():
    empty = Grounding(known_aids=frozenset(), allowed_schema_saids=frozenset())
    populated = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}),
                          known_credential_saids=frozenset({LIC, SHARD}))
    for surf in (SURF, PSURF, NSURF, NOSURF, ASURF, RSURF):
        for grounding in (empty, G, populated):
            assert _find_empty_required(build_proposal_schema(surf, grounding)) == []
