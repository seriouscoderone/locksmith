from keri_assistant.intent import ResolvedIntent
from keri_assistant.grounding import Grounding, check_grounded

G = Grounding(
    known_aids=frozenset({"EBroker000000000000000000000000000000000000"}),
    allowed_schema_saids=frozenset({"ESchemaQuote0000000000000000000000000000000"}),
)


def test_fully_grounded_intent_passes():
    it = ResolvedIntent(route="/insurance/cmd/submit_quote", verb_id="submit_quote", kind="exchange",
                        payload={"amount": 1}, receiver_aid="EBroker000000000000000000000000000000000000",
                        schema_said="ESchemaQuote0000000000000000000000000000000")
    assert check_grounded(it, G) is None


def test_unknown_receiver_is_refused():
    it = ResolvedIntent(route="/insurance/cmd/submit_quote", verb_id="submit_quote", kind="exchange",
                        payload={}, receiver_aid="EStranger000000000000000000000000000000000")
    reason = check_grounded(it, G)
    assert reason is not None and "receiver" in reason.lower()


def test_ungrounded_schema_is_refused():
    it = ResolvedIntent(route="/insurance/cmd/submit_quote", verb_id="submit_quote", kind="exchange",
                        payload={}, schema_said="EUnknownSchema00000000000000000000000000000")
    reason = check_grounded(it, G)
    assert reason is not None and "schema" in reason.lower()


def test_none_fields_are_not_checked():
    it = ResolvedIntent(route="/qry/issued_credentials", verb_id="issued_credentials", kind="query", payload={})
    assert check_grounded(it, G) is None
