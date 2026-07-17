"""Tests for `locksmith.core.serviceaid_bridge`: the Qt-facing adapter over
keri_serviceaid's host-agnostic `issue_credential`/`frame_grant_for`.

Covers:
- `QtProgressSink` forwards `on_event` to `DoerSignalBridge.emit_doer_event`
  unchanged, so serviceaid emissions surface as the SAME Qt events the
  gate/UI already filter on.
- `serviceaid_eligible` (single-sig, unwitnessed hab guard).
- `ServiceaidIssueDoer`/`ServiceaidGrantDoer` call the library functions with
  a `QtProgressSink`, and mirror the legacy doers' event vocabulary
  (`"IssueCredentialDoer"`/`"SendGrantDoer"`) on failure/success so existing
  UI dialogs keep working unmodified against the new bridge doers.
- `make_issue_doer`/`make_grant_doer` route eligible habs to the bridge
  doers and ineligible ones (GroupHab / witnessed) to the legacy doers.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import locksmith.core.serviceaid_bridge as bridge
from locksmith.core.serviceaid_bridge import (
    QtProgressSink,
    ServiceaidGrantDoer,
    ServiceaidIssueDoer,
    make_grant_doer,
    make_issue_doer,
    serviceaid_eligible,
)


def test_qt_sink_forwards_to_signal_bridge():
    signal_bridge = MagicMock()
    QtProgressSink(signal_bridge).on_event(
        "IssueCredentialDoer", "credential_issued", {"said": "E1"}
    )
    signal_bridge.emit_doer_event.assert_called_once_with(
        "IssueCredentialDoer", "credential_issued", {"said": "E1"}
    )


def test_eligibility_guard():
    single = MagicMock()
    single.__class__.__name__ = "Hab"
    single.kever.wits = []

    witnessed = MagicMock()
    witnessed.__class__.__name__ = "Hab"
    witnessed.kever.wits = ["B" + "W" * 43]

    group = MagicMock()
    group.__class__.__name__ = "GroupHab"
    group.kever.wits = []

    assert serviceaid_eligible(single) is True
    assert serviceaid_eligible(witnessed) is False
    assert serviceaid_eligible(group) is False


@patch("locksmith.core.serviceaid_bridge.issue_credential", return_value="Ecred")
def test_issue_doer_calls_library_with_qt_sink(mock_issue):
    app = MagicMock()
    d = ServiceaidIssueDoer(
        app, schema_said="Es", recipient="Er", attributes={"a": 1}, registry_name="Es"
    )
    list(d.do(MagicMock(), 0.0))  # drive the generator to completion

    assert mock_issue.call_args.kwargs["schema_said"] == "Es"
    assert type(mock_issue.call_args.kwargs["sink"]).__name__ == "QtProgressSink"
    assert d.credential_said == "Ecred"


@patch(
    "locksmith.core.serviceaid_bridge.issue_credential",
    side_effect=RuntimeError("boom"),
)
def test_issue_doer_emits_legacy_failure_event_on_exception(mock_issue):
    signal_bridge = MagicMock()
    vault = MagicMock(signals=signal_bridge)
    app = MagicMock(vault=vault)

    d = ServiceaidIssueDoer(
        app, schema_said="Es", recipient="Er", attributes={"a": 1}, registry_name="Es"
    )
    list(d.do(MagicMock(), 0.0))

    signal_bridge.emit_doer_event.assert_called_once_with(
        "IssueCredentialDoer",
        "credential_issuance_failed",
        {
            "error": "boom",
            "schema_said": "Es",
            "recipient_pre": "Er",
            "success": False,
        },
    )


def test_grant_doer_frames_via_library_then_delivers_and_emits_send_complete(monkeypatch):
    calls = []

    fake_hab = MagicMock()
    hby = MagicMock()
    hby.habs.get.return_value = fake_hab

    signal_bridge = MagicMock()
    vault = MagicMock(hby=hby, signals=signal_bridge)
    app = MagicMock(vault=vault)

    monkeypatch.setattr(
        bridge, "frame_grant_for", lambda *a, **kw: ("Egrant", b"rawbytes")
    )

    class FakeSerder:
        size = 4  # pretend "rawb" is the framed exn; "ytes" is the attachment

    monkeypatch.setattr(bridge.serdering, "SerderKERI", lambda raw: FakeSerder())

    class FakePoster:
        def __init__(self, **kwa):
            calls.append(("PeerAwarePoster.__init__", kwa))
            self.sent = []
            self.last_outcome = SimpleNamespace(value="peer")

        def send(self, serder, attachment=None):
            calls.append(("send", serder, attachment))

        def deliver(self):
            return []

    monkeypatch.setattr(bridge, "PeerAwarePoster", FakePoster)

    # Construct BEFORE patching doing.DoDoer: ServiceaidGrantDoer's own base
    # class is the real DoDoer, resolved at class-definition time, but its
    # __init__ chain looks up the *module-level* `DoDoer` name again via
    # `super(DoDoer, self)` -- patching the name first would break that.
    doer = ServiceaidGrantDoer(
        app, credential_said="Ecred", recipient="Erecp", hab_pre="Ehabpre"
    )
    doer.extend = lambda doers: calls.append(("extend", doers))

    class FakeDoDoer:
        def __init__(self, doers=None, **kwa):
            self.done = True

    monkeypatch.setattr(bridge.doing, "DoDoer", FakeDoDoer)

    list(doer.grantDo(lambda: 0.0))

    send_calls = [c for c in calls if c[0] == "send"]
    assert len(send_calls) == 1
    assert isinstance(send_calls[0][1], FakeSerder)
    assert send_calls[0][2] == b"ytes"  # attachment: raw bytes past serder.size
    signal_bridge.emit_doer_event.assert_called_once_with(
        "SendGrantDoer",
        "send_complete",
        {
            "success": True,
            "credential_said": "Ecred",
            "recipient": "Erecp",
            "grant_said": "Egrant",
            "channel": "peer",
        },
    )


def test_grant_doer_emits_legacy_failure_event_when_hab_missing():
    signal_bridge = MagicMock()
    hby = MagicMock()
    hby.habs.get.return_value = None
    vault = MagicMock(hby=hby, signals=signal_bridge)
    app = MagicMock(vault=vault)

    doer = ServiceaidGrantDoer(
        app, credential_said="Ecred", recipient="Erecp", hab_pre="Emissing"
    )
    doer.extend = lambda doers: None

    list(doer.grantDo(lambda: 0.0))

    signal_bridge.emit_doer_event.assert_called_once_with(
        "SendGrantDoer",
        "send_failed",
        {
            "error": "Issuer identifier not found",
            "success": False,
            "credential_said": "Ecred",
        },
    )


def test_make_issue_doer_routes_eligible_hab_to_bridge_doer():
    app = MagicMock()
    hab = MagicMock()
    hab.__class__.__name__ = "Hab"
    hab.kever.wits = []

    d = make_issue_doer(
        app,
        hab,
        schema_said="Es",
        recipient="Er",
        attributes={"a": 1},
        registry_name="Es",
    )
    assert isinstance(d, ServiceaidIssueDoer)


def test_make_issue_doer_routes_ineligible_hab_to_legacy_doer():
    from locksmith.core.credentialing import IssueCredentialDoer

    app = MagicMock()
    hab = MagicMock()
    hab.__class__.__name__ = "GroupHab"
    hab.kever.wits = []

    d = make_issue_doer(
        app,
        hab,
        schema_said="Es",
        recipient="Er",
        attributes={"a": 1},
        registry_name="Es",
    )
    assert isinstance(d, IssueCredentialDoer)


def test_make_grant_doer_routes_eligible_hab_to_bridge_doer():
    app = MagicMock()
    hab = MagicMock()
    hab.__class__.__name__ = "Hab"
    hab.kever.wits = []
    hab.pre = "Eissuer"

    d = make_grant_doer(app, hab, credential_said="Ecred", recipient="Erecp")
    assert isinstance(d, ServiceaidGrantDoer)


def test_make_grant_doer_routes_ineligible_hab_to_legacy_doer():
    from locksmith.core.ipexing import SendGrantDoer

    app = MagicMock()
    hab = MagicMock()
    hab.__class__.__name__ = "Hab"
    hab.kever.wits = ["B" + "W" * 43]
    hab.pre = "Eissuer"

    d = make_grant_doer(app, hab, credential_said="Ecred", recipient="Erecp")
    assert isinstance(d, SendGrantDoer)
