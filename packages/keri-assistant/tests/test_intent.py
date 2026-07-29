import pytest
from keri_assistant.intent import ResolvedIntent


def test_valid_intent_roundtrips_fields():
    it = ResolvedIntent(route="/ipex/grant", verb_id="grant_license", kind="exchange", payload={"x": 1})
    assert it.route == "/ipex/grant"
    assert it.verb_id == "grant_license"
    assert it.kind == "exchange"
    assert it.payload == {"x": 1}
    assert it.receiver_aid is None and it.schema_said is None


def test_intent_is_frozen():
    it = ResolvedIntent(route="/q", verb_id="v", kind="query", payload={})
    with pytest.raises(Exception):
        it.route = "/other"


@pytest.mark.parametrize("kind", ["exchange", "query"])
def test_kind_allowed(kind):
    ResolvedIntent(route="/r", verb_id="v", kind=kind, payload={})


def test_bad_kind_rejected():
    with pytest.raises(ValueError):
        ResolvedIntent(route="/r", verb_id="v", kind="mutate", payload={})


def test_empty_route_rejected():
    with pytest.raises(ValueError):
        ResolvedIntent(route="", verb_id="v", kind="query", payload={})


def test_non_dict_payload_rejected():
    with pytest.raises(ValueError):
        ResolvedIntent(route="/r", verb_id="v", kind="query", payload=["not", "a", "dict"])
