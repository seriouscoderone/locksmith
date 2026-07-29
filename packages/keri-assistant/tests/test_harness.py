import pytest
from keri_assistant.surface import build_micro_app_surface
from keri_assistant.grounding import Grounding
from keri_assistant.harness import Assistant, Outcome
from tests.fixtures.sample_template import SAMPLE_TEMPLATE
from tests.fakes import FakeConfirmer, RecordingDispatcher, RecordingAudit

SURF = build_micro_app_surface(SAMPLE_TEMPLATE)
BROKER = "EBroker000000000000000000000000000000000000"
QUOTE_SCHEMA = "ESchemaQuote0000000000000000000000000000000"
G = Grounding(known_aids=frozenset({BROKER}), allowed_schema_saids=frozenset({QUOTE_SCHEMA}))


def _assistant(confirm: bool):
    conf, disp, aud = FakeConfirmer(confirm), RecordingDispatcher(), RecordingAudit()
    a = Assistant(surface=SURF, grounding=G, confirmer=conf, dispatcher=disp, audit=aud,
                  proposed_by="assistant")
    return a, conf, disp, aud


def test_confirmed_command_dispatches_and_audits():
    a, conf, disp, aud = _assistant(confirm=True)
    out = a.handle("submit the quote", payload={"amount": 10}, receiver_aid=BROKER)
    assert out.status == "dispatched"
    assert len(disp.dispatched) == 1
    assert disp.dispatched[0].route == "/insurance/cmd/submit_quote"
    assert disp.dispatched[0].schema_said == QUOTE_SCHEMA
    assert len(conf.previews) == 1  # confirm ceremony always shown
    assert aud.events[-1].outcome == "dispatched"
    assert aud.events[-1].authorized_by == "human"
    assert aud.events[-1].proposed_by == "assistant"


def test_rejected_command_does_not_dispatch():
    a, conf, disp, aud = _assistant(confirm=False)
    out = a.handle("submit the quote", payload={"amount": 10}, receiver_aid=BROKER)
    assert out.status == "rejected"
    assert disp.dispatched == []  # NEVER dispatched without confirm
    assert aud.events[-1].outcome == "rejected"
    assert aud.events[-1].authorized_by is None


def test_no_match_is_audited_and_never_dispatches():
    a, conf, disp, aud = _assistant(confirm=True)
    out = a.handle("what is the weather")
    assert out.status == "no_match"
    assert disp.dispatched == [] and conf.previews == []
    assert aud.events[-1].outcome == "no_match"


def test_ambiguous_utterance_asks_to_disambiguate_without_dispatch():
    a, conf, disp, aud = _assistant(confirm=True)
    out = a.handle("credentials application")
    assert out.status == "disambiguation"
    assert {v.id for v in out.candidates} == {"create_application", "issued_credentials"}
    assert disp.dispatched == [] and conf.previews == []


def test_ungrounded_receiver_is_refused_before_confirm():
    a, conf, disp, aud = _assistant(confirm=True)
    out = a.handle("submit the quote", payload={"amount": 1}, receiver_aid="EStranger0000000000000000000000000000000000")
    assert out.status == "refused_ungrounded"
    assert conf.previews == [] and disp.dispatched == []
    assert aud.events[-1].outcome == "refused_ungrounded"
