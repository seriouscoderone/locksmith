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


class FakeSerder:
    size = 4  # pretend "rawb" is the framed exn; "ytes" is the attachment


def _grant_doer_setup(monkeypatch, *, calls, sources=(), message=""):
    """Shared scaffolding for ServiceaidGrantDoer tests: a MagicMock app with
    a resolvable hab, a cloneCred-able credential, patched framing/poster/
    sendArtifacts recording into `calls`, and the constructed doer.
    """
    fake_hab = MagicMock()
    hby = MagicMock()
    hby.habs.get.return_value = fake_hab

    signal_bridge = MagicMock()
    creder = MagicMock(name="creder")
    vault = MagicMock(hby=hby, signals=signal_bridge)
    vault.rgy.reger.cloneCred.return_value = (creder, None, None, None)
    vault.rgy.reger.sources.return_value = list(sources)
    # No peer-mode settings configured -- a MagicMock's auto-attributes are
    # truthy by default, which would otherwise make `_inband_oobi_msgs`
    # silently "activate" (settings.enabled Mock is truthy) and queue two
    # extra sends nobody in these tests asked for. Explicit None matches
    # the real stock-wallet default (no peer mode) these tests model.
    vault.db.peerSettings.get.return_value = None
    app = MagicMock(vault=vault)

    mock_frame = MagicMock(return_value=("Egrant", b"rawbytes"))
    monkeypatch.setattr(bridge, "frame_grant_for", mock_frame)
    monkeypatch.setattr(bridge.serdering, "SerderKERI", lambda raw: FakeSerder())

    posters = []

    class FakePoster:
        def __init__(self, **kwa):
            calls.append(("PeerAwarePoster.__init__", kwa))
            posters.append(self)
            self.last_outcome = SimpleNamespace(value="peer")

        def send(self, serder, attachment=None):
            calls.append(("send", serder, attachment))

        def deliver(self):
            return []

    monkeypatch.setattr(bridge, "PeerAwarePoster", FakePoster)

    def fake_send_artifacts(hby_, reger_, postman_, creder_, recp_):
        calls.append(("sendArtifacts", hby_, reger_, postman_, creder_, recp_))

    monkeypatch.setattr(bridge.credentialing, "sendArtifacts", fake_send_artifacts)

    class FakeParser:
        def __init__(self, **kwa):
            pass

        def parseOne(self, ims=None, exc=None, version=None):
            calls.append(("parseOne", ims, exc, version))

    monkeypatch.setattr(bridge.parsing, "Parser", FakeParser)
    monkeypatch.setattr(bridge, "message_version", lambda ims: "V1")

    # Construct BEFORE patching doing.DoDoer: ServiceaidGrantDoer's own base
    # class is the real DoDoer, resolved at class-definition time, but its
    # __init__ chain looks up the *module-level* `DoDoer` name again via
    # `super(DoDoer, self)` -- patching the name first would break that.
    doer = ServiceaidGrantDoer(
        app, credential_said="Ecred", recipient="Erecp", hab_pre="Ehabpre",
        message=message,
    )
    doer.extend = lambda doers: calls.append(("extend", doers))

    class FakeDoDoer:
        def __init__(self, doers=None, **kwa):
            self.done = True

    monkeypatch.setattr(bridge.doing, "DoDoer", FakeDoDoer)

    return SimpleNamespace(
        doer=doer, app=app, hby=hby, hab=fake_hab, creder=creder,
        signal_bridge=signal_bridge, mock_frame=mock_frame, posters=posters,
        rgy=vault.rgy, exc=vault.exc,
    )


def test_grant_doer_frames_via_library_then_delivers_and_emits_send_complete(monkeypatch):
    calls = []
    s = _grant_doer_setup(monkeypatch, calls=calls)

    list(s.doer.grantDo(lambda: 0.0))

    # Framing came from the library with the full kwarg contract.
    assert s.mock_frame.call_args.args == (s.hby, s.hab, s.rgy)
    kw = s.mock_frame.call_args.kwargs
    assert kw["credential_said"] == "Ecred"
    assert kw["recipient"] == "Erecp"
    assert kw["return_raw"] is True
    assert type(kw["sink"]).__name__ == "QtProgressSink"

    # Artifact streaming (issuer KEL/TEL) happened once, on the SAME postman
    # the grant travels on, with the credential's creder -- BEFORE the exn send.
    artifact_calls = [c for c in calls if c[0] == "sendArtifacts"]
    assert len(artifact_calls) == 1
    _, hby_, reger_, postman_, creder_, recp_ = artifact_calls[0]
    assert hby_ is s.hby
    assert reger_ is s.rgy.reger
    assert postman_ is s.posters[0]
    assert creder_ is s.creder
    assert recp_ == "Erecp"
    assert calls.index(artifact_calls[0]) < calls.index(
        next(c for c in calls if c[0] == "send")
    )

    send_calls = [c for c in calls if c[0] == "send"]
    assert len(send_calls) == 1
    assert isinstance(send_calls[0][1], FakeSerder)
    assert send_calls[0][2] == b"ytes"  # attachment: raw bytes past serder.size
    s.signal_bridge.emit_doer_event.assert_called_once_with(
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


def test_grant_doer_forwards_message_to_frame_grant_for(monkeypatch):
    """Regression: the legacy `SendGrantDoer` preserved a user-typed IPEX
    message end-to-end; `ServiceaidGrantDoer` silently dropped it because it
    never accepted a `message` kwarg and never passed one to
    `frame_grant_for` (which itself used to hardcode `message=""` -- fixed
    upstream in keripy's `keri_serviceaid/providers/issue.py`). This pins the
    bridge-doer half of that fix: whatever `message` the doer is constructed
    with must reach `frame_grant_for`'s `message` kwarg verbatim.
    """
    calls = []
    s = _grant_doer_setup(monkeypatch, calls=calls, message="please review")

    list(s.doer.grantDo(lambda: 0.0))

    kw = s.mock_frame.call_args.kwargs
    assert kw["message"] == "please review"


def test_grant_doer_defaults_message_to_empty_string(monkeypatch):
    """Byte-identical-to-before default: omitting `message` at construction
    still frames an empty-string message, matching every existing caller
    that never threaded one."""
    calls = []
    s = _grant_doer_setup(monkeypatch, calls=calls)

    list(s.doer.grantDo(lambda: 0.0))

    kw = s.mock_frame.call_args.kwargs
    assert kw["message"] == ""


def test_grant_doer_parses_framed_grant_into_vault_exchanger_before_delivery(monkeypatch):
    calls = []
    s = _grant_doer_setup(monkeypatch, calls=calls)

    list(s.doer.grantDo(lambda: 0.0))

    # The freshly-framed grant is parsed into the WALLET's exchanger
    # (app.vault.exc) -- mirrors SendGrantDoer (ipexing.py:376). Without it
    # the grant never lands in hby.db.exns and the recipient's later
    # /ipex/admit fails IpexHandler.verify's cloneMessage lookup.
    parse_calls = [c for c in calls if c[0] == "parseOne"]
    assert len(parse_calls) == 1
    _, ims, exc, version = parse_calls[0]
    assert ims == b"rawbytes"  # the exact raw returned by frame_grant_for
    assert exc is s.exc  # the vault's exchanger, not a fresh one
    assert version == "V1"  # message_version(raw) threaded through

    # Parsed locally BEFORE any delivery activity.
    first_delivery = calls.index(
        next(
            c for c in calls
            if c[0] in ("PeerAwarePoster.__init__", "sendArtifacts", "send", "extend")
        )
    )
    assert calls.index(parse_calls[0]) < first_delivery


def test_grant_doer_streams_edge_source_artifacts_before_grant(monkeypatch):
    calls = []
    source = MagicMock(name="source")
    s = _grant_doer_setup(monkeypatch, calls=calls, sources=[(source, b"satc")])

    list(s.doer.grantDo(lambda: 0.0))

    # sendArtifacts for the credential itself AND for each chain source,
    # in that order -- mirrors SendGrantDoer's tail.
    artifact_calls = [c for c in calls if c[0] == "sendArtifacts"]
    assert len(artifact_calls) == 2
    assert artifact_calls[0][4] is s.creder
    assert artifact_calls[1][4] is source

    # The source serder+attachment go through the postman, before the exn.
    send_calls = [c for c in calls if c[0] == "send"]
    assert len(send_calls) == 2
    assert send_calls[0][1] is source
    assert send_calls[0][2] == b"satc"
    assert isinstance(send_calls[1][1], FakeSerder)  # the grant exn last


def test_grant_doer_queues_inband_oobi_between_artifacts_and_chain_sources(monkeypatch):
    """Task 7 wiring: when peer mode is enabled and the hab is peer-exposed,
    `grantDo` queues the two in-band OOBI rpys on the SAME postman, AFTER
    the credential's `sendArtifacts` call and BEFORE the chain-source loop
    -- see `_inband_oobi_msgs`'s module docstring for why that ordering
    matters (key state, then reachability, then the exn)."""
    from locksmith.peer.records import PeerModeSettings

    calls = []
    source = MagicMock(name="source")
    s = _grant_doer_setup(monkeypatch, calls=calls, sources=[(source, b"satc")])
    s.app.vault.db.peerSettings.get.return_value = PeerModeSettings(
        enabled=True, port=5622, advertised_host="127.0.0.1",
    )
    monkeypatch.setattr(bridge, "is_aid_peer_exposed", lambda hab: True)
    # This test is about WHERE the in-band rpys get queued, not what they
    # contain. `_inband_oobi_msgs` loads already-published records out of the db
    # (see test_inband_oobi.py, which exercises it against a real Habery) — a
    # MagicMock hab has no such records, so stub the whole helper here and let
    # the ordering assertions below be what this test actually proves.
    monkeypatch.setattr(
        bridge, "_inband_oobi_msgs",
        lambda hab, settings: [(FakeSerder(), None), (FakeSerder(), None)])

    list(s.doer.grantDo(lambda: 0.0))

    kinds = [c[0] for c in calls if c[0] in ("sendArtifacts", "send")]
    # sendArtifacts(credential) -> 2 in-band OOBI sends -> sendArtifacts
    # (chain source) -> chain-source send -> grant exn send.
    assert kinds == [
        "sendArtifacts", "send", "send", "sendArtifacts", "send", "send",
    ]
    send_calls = [c for c in calls if c[0] == "send"]
    assert len(send_calls) == 4
    # The first two sends are the in-band OOBI rpys (FakeSerder stand-ins,
    # attachment=None since the fake raw bytes have no trailing tail past
    # FakeSerder.size=4).
    assert isinstance(send_calls[0][1], FakeSerder)
    assert isinstance(send_calls[1][1], FakeSerder)
    # Then the chain source, then the grant exn last.
    assert send_calls[2][1] is source
    assert isinstance(send_calls[3][1], FakeSerder)


def test_grant_doer_emits_send_failed_when_credential_missing(monkeypatch):
    calls = []
    s = _grant_doer_setup(monkeypatch, calls=calls)
    s.rgy.reger.cloneCred.return_value = (None, None, None, None)

    list(s.doer.grantDo(lambda: 0.0))

    s.mock_frame.assert_not_called()
    assert [c for c in calls if c[0] == "sendArtifacts"] == []
    s.signal_bridge.emit_doer_event.assert_called_once_with(
        "SendGrantDoer",
        "send_failed",
        {
            "error": "Credential Ecred not found in registry",
            "success": False,
            "credential_said": "Ecred",
        },
    )


def test_grant_doer_emits_send_failed_on_transport_failure(monkeypatch):
    """serviceaid_bridge.py:328-339 -- `grantDo`'s OUTER `except Exception`,
    which is distinct from the two early-return guards (hab missing /
    credential missing) already covered above. Drive it via a transport
    failure: the real failure mode this guards against is delivery-layer
    (PeerAwarePoster), not framing -- so frame_grant_for succeeds and
    parsing into the vault exchanger succeeds, but constructing the
    transport itself raises. The doer must fail safe: log, emit the SAME
    "send_failed" vocabulary the other failure paths use, and return
    without propagating."""
    calls = []
    s = _grant_doer_setup(monkeypatch, calls=calls)

    class FailingPoster:
        def __init__(self, **kwa):
            raise ConnectionError("transport unavailable")

    monkeypatch.setattr(bridge, "PeerAwarePoster", FailingPoster)

    list(s.doer.grantDo(lambda: 0.0))

    # Framing and the local exchanger-parse both got far enough to run --
    # only the transport construction failed.
    s.mock_frame.assert_called_once()
    assert [c for c in calls if c[0] == "parseOne"]

    s.signal_bridge.emit_doer_event.assert_called_once_with(
        "SendGrantDoer",
        "send_failed",
        {
            "error": "transport unavailable",
            "success": False,
            "credential_said": "Ecred",
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


def test_make_grant_doer_forwards_message_to_bridge_doer():
    """Regression: the routing chokepoint must forward a caller's `message`
    kwarg to the bridge doer (eligible-hab path), not just the legacy doer
    -- otherwise a user-typed IPEX message silently vanishes the moment a
    hab happens to be single-sig/unwitnessed."""
    app = MagicMock()
    hab = MagicMock()
    hab.__class__.__name__ = "Hab"
    hab.kever.wits = []
    hab.pre = "Eissuer"

    d = make_grant_doer(
        app, hab, credential_said="Ecred", recipient="Erecp",
        message="please review",
    )
    assert isinstance(d, ServiceaidGrantDoer)
    assert d.message == "please review"


def test_make_grant_doer_forwards_message_to_legacy_doer():
    from locksmith.core.ipexing import SendGrantDoer

    app = MagicMock()
    hab = MagicMock()
    hab.__class__.__name__ = "Hab"
    hab.kever.wits = ["B" + "W" * 43]
    hab.pre = "Eissuer"

    d = make_grant_doer(
        app, hab, credential_said="Ecred", recipient="Erecp",
        message="please review",
    )
    assert isinstance(d, SendGrantDoer)
    assert d.message == "please review"


def test_grant_doer_tolerates_vault_without_db(monkeypatch):
    """Regression: when the vault has no db (e.g., test harnesses with
    stubbed transport), `grantDo` must not fail trying to read peer settings.
    The in-band OOBI block degrades gracefully: it reads `db.peerSettings`
    only if `db` exists, passes `None` to `_inband_oobi_msgs` (which short-
    circuits and returns [] for `None` settings), and the grant completes
    successfully with `send_complete`."""
    calls = []
    s = _grant_doer_setup(monkeypatch, calls=calls)
    # Simulate a stubbed vault with no db (test harness case)
    s.app.vault.db = None

    list(s.doer.grantDo(lambda: 0.0))

    # In-band OOBI sends must NOT be queued (no db means no settings)
    send_calls = [c for c in calls if c[0] == "send"]
    assert len(send_calls) == 1  # only the grant exn, no OOBI rpys
    assert isinstance(send_calls[0][1], FakeSerder)

    # Grant must complete successfully despite missing db
    s.signal_bridge.emit_doer_event.assert_called_once_with(
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


def test_grant_doer_goes_loud_when_fallback_has_nowhere_to_deliver(monkeypatch):
    """The silent-loss case from the first live two-machine test
    (backlog/2026-07-29-grant-send-reports-success-while-undeliverable.md):
    the peer dial failed (channel=peer→mailbox) AND the recipient has no
    mailbox/agent/witness ends — the fallback delivered nowhere. The doer
    must emit send_failed with an operator-readable reason instead of
    send_complete, so the grant dialog shows a failure instead of implying
    success."""
    calls = []
    s = _grant_doer_setup(monkeypatch, calls=calls)

    # The transport fell back...
    class FallbackPoster:
        def __init__(self, **kwa):
            self.last_outcome = SimpleNamespace(value="peer→mailbox")

        def send(self, serder, attachment=None):
            pass

        def deliver(self):
            return []

    monkeypatch.setattr(bridge, "PeerAwarePoster", FallbackPoster)

    # ...and the recipient has no ends the mailbox path could route through.
    s.hab.endsFor.return_value = {}
    # Pairing label present → the failure copy names the peer.
    s.app.vault.db.peerAllowlist.get.return_value = SimpleNamespace(
        aid="Erecp", label="requester-vm", endpoint_url="tcp://10.211.55.7:5622")

    list(s.doer.grantDo(lambda: 0.0))

    s.signal_bridge.emit_doer_event.assert_called_once_with(
        "SendGrantDoer",
        "send_failed",
        {
            "error": "couldn't reach requester-vm's wallet — it may be "
                     "behind a firewall or NAT",
            "success": False,
            "credential_said": "Ecred",
            "recipient": "Erecp",
            "grant_said": "Egrant",
            "channel": "peer→mailbox",
            "undeliverable": True,
        },
    )


def test_grant_doer_fallback_with_a_real_mailbox_route_stays_a_success(monkeypatch):
    """An honest fallback is not a failure: when the recipient DOES have a
    located mailbox end, peer→mailbox means the grant is queued somewhere
    the recipient can fetch from — keep the existing send_complete +
    channel contract (the dialog renders 'peer unreachable, sent via
    mailbox')."""
    calls = []
    s = _grant_doer_setup(monkeypatch, calls=calls)

    class FallbackPoster:
        def __init__(self, **kwa):
            self.last_outcome = SimpleNamespace(value="peer→mailbox")

        def send(self, serder, attachment=None):
            pass

        def deliver(self):
            return []

    monkeypatch.setattr(bridge, "PeerAwarePoster", FallbackPoster)

    # endsFor reports a located mailbox end for the recipient.
    s.hab.endsFor.return_value = {
        "mailbox": {"BMBX": {"http": "http://mailbox.example:5632/"}},
    }

    list(s.doer.grantDo(lambda: 0.0))

    s.signal_bridge.emit_doer_event.assert_called_once_with(
        "SendGrantDoer",
        "send_complete",
        {
            "success": True,
            "credential_said": "Ecred",
            "recipient": "Erecp",
            "grant_said": "Egrant",
            "channel": "peer→mailbox",
        },
    )
