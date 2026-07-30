"""Pin the compiled proposal schema for the sample template so drift in the compiler is caught."""
import json

from keri_assistant.actionschema import build_proposal_schema
from keri_assistant.grounding import Grounding
from keri_assistant.surface import build_micro_app_surface
from tests.fixtures.sample_template import SAMPLE_TEMPLATE

BROKER = "EBroker000000000000000000000000000000000000"
QUOTE = "ESchemaQuote0000000000000000000000000000000"


def test_golden_proposal_schema():
    schema = build_proposal_schema(
        build_micro_app_surface(SAMPLE_TEMPLATE),
        Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE})),
    )
    # Order is significant (surface order, then the two escape hatches) — pin it as emitted.
    #
    # `create_application` is deliberately ABSENT: its fixture payload declares
    # `additionalProperties: true`, an open payload that an adversarial review proved (with a
    # `jsonschema` oracle) lets an ungrounded `holder_aid` validate through untouched, so open
    # payloads now fail closed and the verb is omitted rather than emitted with a hatch of its
    # own (see `test_shipped_open_payload_fixture_create_application_is_omitted` in
    # test_actionschema.py). Both escape hatches carry `"minLength": 1` — an empty string is not
    # a truthful "out". If this assertion fails, diff the actual emitted schema against this one
    # and establish which side is wrong before touching the literal.
    assert json.dumps(schema, sort_keys=True) == json.dumps({
        "oneOf": [
            {"type": "object", "additionalProperties": False,
             "required": ["verb_id", "receiver_aid", "schema_said", "payload"],
             "properties": {"verb_id": {"const": "submit_quote"},
                            "receiver_aid": {"enum": [BROKER]},
                            "schema_said": {"const": QUOTE},
                            "payload": {"type": "object", "additionalProperties": False,
                                        "properties": {"amount": {"type": "number"}},
                                        "required": ["amount"]}}},
            {"type": "object", "additionalProperties": False,
             "required": ["verb_id", "question"],
             "properties": {"verb_id": {"const": "__clarify__"},
                            "question": {"type": "string", "minLength": 1, "maxLength": 200}}},
            {"type": "object", "additionalProperties": False,
             "required": ["verb_id", "reason"],
             "properties": {"verb_id": {"const": "__unsupported__"},
                            "reason": {"type": "string", "minLength": 1, "maxLength": 200}}},
        ]
    }, sort_keys=True)
