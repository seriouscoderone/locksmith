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
