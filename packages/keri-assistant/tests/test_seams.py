from keri_assistant.intent import ResolvedIntent
from keri_assistant.seams import Preview, DispatchResult, AuditEvent
from tests.fakes import FakeConfirmer, RecordingDispatcher, RecordingAudit


def test_fake_confirmer_returns_configured_answer():
    p = Preview(route="/r", verb_id="v", kind="exchange", receiver_aid=None, schema_said=None,
                payload={}, summary="do a thing")
    assert FakeConfirmer(True).confirm(p) is True
    assert FakeConfirmer(False).confirm(p) is False


def test_recording_dispatcher_captures_intent_and_returns_ok():
    d = RecordingDispatcher()
    it = ResolvedIntent(route="/r", verb_id="v", kind="exchange", payload={})
    res = d.dispatch(it)
    assert isinstance(res, DispatchResult) and res.ok is True
    assert d.dispatched == [it]


def test_recording_audit_captures_events():
    a = RecordingAudit()
    ev = AuditEvent(proposed_by="assistant", authorized_by="user", intent=None, outcome="dispatched")
    a.record(ev)
    assert a.events == [ev]
