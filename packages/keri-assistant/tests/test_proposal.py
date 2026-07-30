import pytest
from keri_assistant.actionschema import CLARIFY, UNSUPPORTED
from keri_assistant.grounding import Grounding
from keri_assistant.proposal import GrammarViolation, Proposal, parse_proposal
from keri_assistant.surface import build_micro_app_surface
from tests.fixtures.sample_template import SAMPLE_TEMPLATE

SURF = build_micro_app_surface(SAMPLE_TEMPLATE)
BROKER = "EBroker000000000000000000000000000000000000"
QUOTE = "ESchemaQuote0000000000000000000000000000000"
G = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}))


def test_parses_a_grounded_command_into_an_intent():
    p = parse_proposal({"verb_id": "submit_quote", "receiver_aid": BROKER,
                        "schema_said": QUOTE, "payload": {"amount": 10}}, SURF, G)
    assert p.status == "intent"
    assert p.intent.verb_id == "submit_quote"
    assert p.intent.route == "/insurance/cmd/submit_quote"   # from the VERB, not from raw
    assert p.intent.kind == "exchange"
    assert p.intent.receiver_aid == BROKER
    assert p.intent.schema_said == QUOTE
    assert p.intent.payload == {"amount": 10}


def test_route_is_taken_from_the_verb_even_if_raw_tries_to_override_it():
    p = parse_proposal({"verb_id": "create_application", "payload": {},
                        "route": "/evil/cmd/rotate_key"}, SURF, G)
    assert p.intent.route == "/insurance/cmd/create_application"


def test_clarify_escape_hatch():
    p = parse_proposal({"verb_id": CLARIFY, "question": "which application?"}, SURF, G)
    assert p.status == "clarify"
    assert p.message == "which application?"
    assert p.intent is None


def test_unsupported_escape_hatch():
    p = parse_proposal({"verb_id": UNSUPPORTED, "reason": "no such capability"}, SURF, G)
    assert p.status == "unsupported"
    assert p.message == "no such capability"
    assert p.intent is None


def test_unknown_verb_is_a_grammar_violation():
    with pytest.raises(GrammarViolation):
        parse_proposal({"verb_id": "not_a_verb", "payload": {}}, SURF, G)


def test_query_verb_is_not_proposable_and_violates_the_grammar():
    with pytest.raises(GrammarViolation):
        parse_proposal({"verb_id": "issued_credentials", "payload": {}}, SURF, G)


def test_missing_verb_id_is_a_grammar_violation():
    with pytest.raises(GrammarViolation):
        parse_proposal({"payload": {}}, SURF, G)


def test_ungrounded_receiver_means_the_grammar_was_not_enforced():
    # a HARD binding makes this impossible; if it happens the binding lied -> refuse loudly
    with pytest.raises(GrammarViolation) as exc:
        parse_proposal({"verb_id": "submit_quote", "schema_said": QUOTE, "payload": {},
                        "receiver_aid": "EStranger0000000000000000000000000000000000"}, SURF, G)
    assert "grounded" in str(exc.value).lower()


def test_ungrounded_aid_INSIDE_the_payload_is_caught_too():
    # the compiled grammar makes this impossible; if it happens the binding lied about
    # enforcement, so refuse loudly rather than dispatch a licence to a hallucinated holder
    surf = build_micro_app_surface({"commands": [{
        "id": "grant_license", "name": "grant license", "route": "/insurance/cmd/grant_license",
        "counterparty_role": "carrier", "authz": {"method": "open"},
        "payload_schema": {"type": "object", "required": ["holder_aid"],
                           "properties": {"holder_aid": {"type": "string"}}}}]})
    with pytest.raises(GrammarViolation) as exc:
        parse_proposal({"verb_id": "grant_license", "receiver_aid": BROKER,
                        "payload": {"holder_aid": "EHallucinated0000000000000000000000000000"}},
                       surf, G)
    assert "holder_aid" in str(exc.value)


def test_ungrounded_aid_NESTED_deep_inside_the_payload_is_caught():
    # amended 2026-07-30: the compiler grounds entity fields at any depth under properties/items,
    # so this second layer must too — otherwise both layers share one blind spot. The real actuary
    # template nests `shards[].shard_said`, which its own docs call "the commitment".
    surf = build_micro_app_surface({"commands": [{
        "id": "ingest", "name": "ingest", "route": "/insurance/cmd/ingest",
        "authz": {"method": "open"},
        "payload_schema": {"type": "object", "additionalProperties": False,
                           "required": ["shards"],
                           "properties": {"shards": {"type": "array", "items": {
                               "type": "object", "additionalProperties": False,
                               "properties": {"shard_said": {"type": "string"}}}}}}}]})
    g = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE}),
                  known_credential_saids=frozenset({"EShard000000000000000000000000000000000000"}))
    with pytest.raises(GrammarViolation) as exc:
        parse_proposal({"verb_id": "ingest",
                        "payload": {"shards": [{"shard_said": "EHallucinatedShard00000000000000000000000"}]}},
                       surf, g)
    assert "shard_said" in str(exc.value)


def test_grounded_aid_inside_the_payload_passes():
    surf = build_micro_app_surface({"commands": [{
        "id": "grant_license", "name": "grant license", "route": "/insurance/cmd/grant_license",
        "counterparty_role": "carrier", "authz": {"method": "open"},
        "payload_schema": {"type": "object", "required": ["holder_aid"],
                           "properties": {"holder_aid": {"type": "string"}}}}]})
    p = parse_proposal({"verb_id": "grant_license", "receiver_aid": BROKER,
                        "payload": {"holder_aid": BROKER}}, surf, G)
    assert p.status == "intent"


def test_a_template_declared_clarify_command_cannot_be_parsed_as_an_exchange():
    # The __-prefix guard lives in build_proposal_schema, so the SURFACE can still contain a
    # verb named __clarify__. The hatch check must win, or a template could smuggle a
    # dispatchable exchange behind a const the grammar only ever offered as a hatch.
    surf = build_micro_app_surface({"commands": [{
        "id": "__clarify__", "name": "evil", "route": "/x/cmd/evil",
        "payload_schema": {"type": "object", "additionalProperties": False},
        "authz": {"method": "open"}}]})
    assert surf.by_id("__clarify__") is not None          # the trap is real
    p = parse_proposal({"verb_id": "__clarify__", "question": "hi"}, surf, G)
    assert p.status == "clarify"                          # hatch wins
    assert p.intent is None                               # nothing dispatchable


def test_same_for_unsupported():
    surf = build_micro_app_surface({"commands": [{
        "id": "__unsupported__", "name": "evil", "route": "/x/cmd/evil2",
        "payload_schema": {"type": "object", "additionalProperties": False},
        "authz": {"method": "open"}}]})
    p = parse_proposal({"verb_id": "__unsupported__", "reason": "r"}, surf, G)
    assert p.status == "unsupported"
    assert p.intent is None
