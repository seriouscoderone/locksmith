import copy

from keri_assistant.actionschema import CLARIFY, UNSUPPORTED, build_proposal_schema
from keri_assistant.grounding import Grounding
from keri_assistant.surface import build_micro_app_surface
from tests.fixtures.sample_template import SAMPLE_TEMPLATE

SURF = build_micro_app_surface(SAMPLE_TEMPLATE)
BROKER = "EBroker000000000000000000000000000000000000"
QUOTE = "ESchemaQuote0000000000000000000000000000000"
G = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}))


def _alts(schema):
    return {a["properties"]["verb_id"]["const"]: a for a in schema["oneOf"]}


def test_exchange_verbs_and_escape_hatches_are_alternatives():
    alts = _alts(build_proposal_schema(SURF, G))
    assert set(alts) == {"submit_quote", "create_application", CLARIFY, UNSUPPORTED}


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


def test_verb_without_counterparty_has_no_receiver_field():
    alt = _alts(build_proposal_schema(SURF, G))["create_application"]
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
    alts = _alts(build_proposal_schema(SURF, empty))
    assert "submit_quote" not in alts
    assert "create_application" in alts          # needs no receiver, still reachable


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


def test_allOf_declared_entity_fields_are_a_KNOWN_gap_not_grounded():
    # KNOWN GAP, not a passing guarantee: `allOf`/`oneOf`/`anyOf`/`patternProperties`/`$ref` are
    # deliberately unhandled. Closing this needs a decision this codebase hasn't made yet — e.g.
    # whether an allOf branch's `required` binds at the branch or the parent, and how multiple
    # branches' `properties` compose before grounding is applied. Until that decision is made,
    # an entity field declared only inside `allOf` is NOT grounded. This test pins that so a
    # future fix is a deliberate, visible change here, not a silent regression found in prod.
    alt = _alts(build_proposal_schema(ALLOFSURF, G))["allof_holder"]
    allof_branch = alt["properties"]["payload"]["allOf"][0]
    assert allof_branch["properties"]["holder_aid"] == {"type": "string"}  # NOT enum-constrained
