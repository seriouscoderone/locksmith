from unittest.mock import MagicMock, patch

from keri_serviceaid.egf.documents import Endpoint

DOI = "E" + "R" * 43


def _authority(endpoints):
    a = MagicMock()
    a.aid = DOI
    a.display_name = "Utah DOI"
    a.endpoints = tuple(endpoints)
    return a


def _egf(endpoints):
    egf = MagicMock()
    egf.roles = [MagicMock(id="carrier")]
    egf.authorities = MagicMock(return_value=[_authority(endpoints)])
    return egf


def _app(settings=None):
    app = MagicMock()
    app.vault.db.peerSettings.get.return_value = settings
    # Nothing paired yet by default -- an unconfigured MagicMock attribute
    # returns a truthy stub Mock (not None), which would defeat the
    # "already paired" guard's `is not None` check. Tests that need a
    # specific pairing state override this explicitly (see
    # test_idempotent_second_call).
    app.vault.db.peerAllowlist.get.return_value = None
    app.vault.hby.habs = {"E" + "C" * 43: MagicMock(pre="E" + "C" * 43)}
    app.vault._peer_exposed_aids = set()
    return app


@patch("locksmith.core.direct_transport.parse_oobi_cesr", return_value=DOI)
@patch("locksmith.core.direct_transport.find_free_port", return_value=5622)
def test_bring_up_full_sequence(_fp, _parse):
    from locksmith.core.direct_transport import ensure_direct_transport
    app = _app(settings=None)
    src = MagicMock(); src.fetch.return_value = b"cesr"
    ep = Endpoint(mode="direct", scheme="tcp", oobi_ref=DOI)
    ensure_direct_transport(app, _egf([ep]), src, ("bootstrap", "production"))

    pinned = app.vault.db.peerSettings.pin.call_args.kwargs["val"]
    assert pinned.enabled is True and pinned.port == 5622
    app.vault.restart_peer_mode.assert_called_once()
    assert "E" + "C" * 43 in app.vault._peer_exposed_aids
    app.vault.extend.assert_called()          # PublishPeerRoleDoer scheduled
    src.fetch.assert_called_once_with(DOI)
    rec = app.vault.db.peerAllowlist.pin.call_args.kwargs["val"]
    assert rec.aid == DOI and rec.endpoint_url.startswith("tcp://")


@patch("locksmith.core.direct_transport.parse_oobi_cesr", return_value=DOI)
def test_idempotent_second_call(_parse):
    from locksmith.core.direct_transport import ensure_direct_transport
    from locksmith.peer.records import PeerModeSettings, PeerRecord
    app = _app(settings=PeerModeSettings(enabled=True, port=5622))
    app.vault.db.peerAllowlist.get.return_value = PeerRecord(
        aid=DOI, label="Utah DOI", endpoint_url="tcp://127.0.0.1:5621")
    src = MagicMock(); src.fetch.return_value = b"cesr"
    ep = Endpoint(mode="direct", scheme="tcp", oobi_ref=DOI)
    ensure_direct_transport(app, _egf([ep]), src, ("bootstrap", "production"))
    app.vault.db.peerSettings.pin.assert_not_called()   # settings kept
    src.fetch.assert_not_called()                       # already paired


def test_no_direct_endpoints_is_a_noop():
    from locksmith.core.direct_transport import ensure_direct_transport
    app = _app()
    ensure_direct_transport(app, _egf([]), MagicMock(), ("production",))
    app.vault.restart_peer_mode.assert_not_called()


def test_missing_oobi_emits_transport_failed():
    from locksmith.core.direct_transport import ensure_direct_transport
    from keri_serviceaid.egf.errors import OobiNotFound
    app = _app(settings=None)
    src = MagicMock(); src.fetch.side_effect = OobiNotFound(DOI, "bundle")
    ep = Endpoint(mode="direct", scheme="tcp", oobi_ref=DOI)
    with patch("locksmith.core.direct_transport.find_free_port", return_value=5622):
        ensure_direct_transport(app, _egf([ep]), src, ("bootstrap", "production"))
    name, etype, data = app.vault.signals.emit_doer_event.call_args.args
    assert (name, etype) == ("DirectTransport", "transport_failed")
