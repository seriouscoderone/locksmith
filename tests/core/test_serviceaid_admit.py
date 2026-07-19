"""Tests for `ServiceaidAdmitDoer`/`make_admit_doer`: the envelope-guarded
chokepoint that wraps `keri_serviceaid.providers.admit_grant` in Locksmith's
Qt doer/signal machinery, matching `make_issue_doer`/`make_grant_doer`'s
established shape.

Covers:
- `ServiceaidAdmitDoer.do` calls `admit_grant` with a `QtProgressSink` and
  the constructor's `grant_said`.
- On `admit_grant` failure, emits the legacy `("AdmitDoer", "admit_failed")`
  vocabulary so existing UI handlers keep working unmodified.
- `make_admit_doer` routes eligible (single-sig, unwitnessed) habs to the
  bridge doer and witnessed/GroupHab habs to the legacy `AdmitDoer`.
"""
from unittest.mock import MagicMock, patch


def _hab(group=False, wits=()):
    h = MagicMock()
    h.__class__.__name__ = "GroupHab" if group else "Hab"
    h.kever.wits = list(wits)
    h.pre = "E" + "C" * 43
    return h


def _app(hab):
    app = MagicMock()
    app.vault.hby.habs = {hab.pre: hab}
    return app


@patch("locksmith.core.serviceaid_bridge.admit_grant", return_value="Eadmit")
def test_admit_doer_calls_library_with_qt_sink(mock_admit):
    from locksmith.core.serviceaid_bridge import ServiceaidAdmitDoer
    hab = _hab(); app = _app(hab)
    d = ServiceaidAdmitDoer(app, grant_said="Egrant", hab_pre=hab.pre)
    list(d.do(MagicMock(), 0.0))
    assert mock_admit.call_args.kwargs["grant_said"] == "Egrant"
    assert type(mock_admit.call_args.kwargs["sink"]).__name__ == "QtProgressSink"


@patch("locksmith.core.serviceaid_bridge.admit_grant", side_effect=ValueError("boom"))
def test_admit_failure_emits_admit_failed(mock_admit):
    from locksmith.core.serviceaid_bridge import ServiceaidAdmitDoer
    hab = _hab(); app = _app(hab)
    d = ServiceaidAdmitDoer(app, grant_said="Egrant", hab_pre=hab.pre)
    list(d.do(MagicMock(), 0.0))
    name, etype, data = app.vault.signals.emit_doer_event.call_args.args
    assert (name, etype) == ("AdmitDoer", "admit_failed")
    assert data["success"] is False


def test_eligible_routes_to_bridge():
    from locksmith.core.serviceaid_bridge import make_admit_doer
    d = make_admit_doer(_app(_hab()), _hab(), grant_said="Eg")
    assert type(d).__name__ == "ServiceaidAdmitDoer"


def test_witnessed_routes_to_legacy():
    from locksmith.core.serviceaid_bridge import make_admit_doer
    d = make_admit_doer(_app(_hab()), _hab(wits=["B" + "W" * 43]), grant_said="Eg")
    assert type(d).__name__ == "AdmitDoer"


def test_group_hab_routes_to_legacy():
    from locksmith.core.serviceaid_bridge import make_admit_doer
    d = make_admit_doer(_app(_hab()), _hab(group=True), grant_said="Eg")
    assert type(d).__name__ == "AdmitDoer"


def test_make_admit_doer_forwards_message_to_bridge_doer():
    from locksmith.core.serviceaid_bridge import make_admit_doer
    hab = _hab()
    d = make_admit_doer(_app(hab), hab, grant_said="Eg", message="please review")
    assert d.message == "please review"


def test_make_admit_doer_forwards_message_to_legacy_doer():
    from locksmith.core.serviceaid_bridge import make_admit_doer
    hab = _hab(wits=["B" + "W" * 43])
    d = make_admit_doer(_app(hab), hab, grant_said="Eg", message="please review")
    assert d.message == "please review"


@patch("locksmith.core.serviceaid_bridge.admit_grant", return_value="Eadmit")
def test_admit_doer_delivers_admit_back_best_effort(mock_admit):
    """The admit-back delivery is a courtesy: if it raises, the doer must
    swallow the exception (log only) rather than surface it -- the LOCAL
    landing (admit_grant succeeding) is what gates success, per the
    module docstring/brief. Here `_deliver_admit_back` isn't patched, so it
    runs for real against MagicMock vault internals and is expected to
    raise deep inside (e.g. cloneMessage on a non-real Habery) -- `do()`
    must still complete without propagating."""
    from locksmith.core.serviceaid_bridge import ServiceaidAdmitDoer
    hab = _hab(); app = _app(hab)
    d = ServiceaidAdmitDoer(app, grant_said="Egrant", hab_pre=hab.pre)
    # Should not raise even though _deliver_admit_back will hit MagicMock
    # internals unable to satisfy cloneMessage/serializeMessage for real.
    list(d.do(MagicMock(), 0.0))
    mock_admit.assert_called_once()


class _FakeAdmitSerder:
    size = 4  # pretend "rawb" is the framed exn; "ytes" is the attachment


@patch("locksmith.core.serviceaid_bridge.exchanging")
@patch("locksmith.core.serviceaid_bridge.admit_grant", return_value="Eadmit")
def test_admit_doer_delivers_admit_back_over_peer_aware_poster(
    mock_admit, mock_exchanging, monkeypatch
):
    """Pins the *shape* of the admit-back delivery discovered from
    `exchanging.cloneMessage`'s real (serder, pathed) 2-tuple return (NOT
    an object with `.serder`/`.pathed` attributes) and `serializeMessage`
    being the primitive that reconstructs a sendable raw message (body +
    its own signature attachment) from storage by SAID -- `cloneMessage`'s
    `pathed` only carries nested embed-signature paths (empty for a
    no-embeds admit exn), never the exn's own top-level attachment."""
    import locksmith.core.serviceaid_bridge as bridge
    from locksmith.core.serviceaid_bridge import ServiceaidAdmitDoer

    grant_serder = MagicMock()
    grant_serder.ked = {"i": "Egranter"}
    mock_exchanging.cloneMessage.return_value = (grant_serder, {})
    mock_exchanging.serializeMessage.return_value = b"rawbytes"

    monkeypatch.setattr(bridge.serdering, "SerderKERI",
                         lambda raw: _FakeAdmitSerder())

    hab = _hab(); app = _app(hab)
    d = ServiceaidAdmitDoer(app, grant_said="Egrant", hab_pre=hab.pre)

    posted = {}

    class FakePoster:
        def __init__(self, **kwa):
            posted["init_kwargs"] = kwa

        def send(self, serder, attachment=None):
            posted["serder"] = serder
            posted["attachment"] = attachment

        def deliver(self):
            return []

    monkeypatch.setattr(bridge, "PeerAwarePoster", FakePoster)
    monkeypatch.setattr(bridge.doing, "DoDoer", lambda doers=None, **kwa: MagicMock())

    list(d.do(MagicMock(), 0.0))

    # cloneMessage unpacked as a 2-tuple (serder, pathed) -- not
    # `.serder`/`.pathed` attribute access.
    mock_exchanging.cloneMessage.assert_called_once_with(
        app.vault.hby, "Egrant"
    )
    # serializeMessage reconstructs the admit's raw message + attachment
    # from storage by SAID, framed so no extra attachment-group wrapper is
    # needed around a single individually-sent message.
    mock_exchanging.serializeMessage.assert_called_once_with(
        app.vault.hby, "Eadmit", framed=True
    )
    # Granter resolved from the grant's `.ked["i"]` (2-tuple unpack), and
    # PeerAwarePoster targets that AID.
    assert posted["init_kwargs"]["recp"] == "Egranter"
    assert posted["attachment"] == b"ytes"
