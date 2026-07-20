from unittest.mock import MagicMock, patch

from keri_serviceaid.egf.documents import Endpoint

DOI = "E" + "R" * 43
DEFAULT_HAB_PRE = "E" + "C" * 43


def _authority(endpoints):
    a = MagicMock()
    a.aid = DOI
    a.display_name = "Utah DOI"
    a.endpoints = tuple(endpoints)
    return a


def _egf(endpoints):
    egf = MagicMock()
    egf.all_authorities = MagicMock(return_value=[_authority(endpoints)])
    return egf


def _app(settings=None, no_hab=False):
    app = MagicMock()
    app.vault.db.peerSettings.get.return_value = settings
    # Nothing paired yet by default -- an unconfigured MagicMock attribute
    # returns a truthy stub Mock (not None), which would defeat the
    # "already paired" guard's `is not None` check. Tests that need a
    # specific pairing state override this explicitly (see
    # test_idempotent_second_call).
    app.vault.db.peerAllowlist.get.return_value = None
    if no_hab:
        # Neither the brand()-alias lookup nor the "any hab" fallback
        # resolves an identifier -- exercises the no-identifiers-yet guard.
        app.vault.hby.habByName.return_value = None
        app.vault.hby.habs = {}
    else:
        hab = MagicMock(pre=DEFAULT_HAB_PRE)
        # Configured on BOTH paths so the test doesn't depend on whether
        # the real brand().default_aid_alias is set in this process: a
        # MagicMock's return_value ignores the call argument, so whichever
        # branch ensure_direct_transport takes resolves to the same hab.
        app.vault.hby.habByName.return_value = hab
        app.vault.hby.habs = {DEFAULT_HAB_PRE: hab}
    loc = MagicMock()
    loc.url = "tcp://127.0.0.1:5621"
    app.vault.hby.db.locs.get.return_value = loc
    app.vault._peer_exposed_aids = set()
    return app


@patch("locksmith.core.direct_transport.parse_oobi_cesr", return_value=DOI)
@patch("locksmith.core.direct_transport.find_free_port", return_value=5622)
def test_bring_up_full_sequence(_fp, _parse):
    from locksmith.core.direct_transport import ensure_direct_transport
    app = _app(settings=None)
    src = MagicMock(); src.fetch.return_value = b"cesr"
    ep = Endpoint(mode="direct", scheme="tcp", oobi_ref=DOI)
    assert ensure_direct_transport(
        app, _egf([ep]), src, ("bootstrap", "production")) is True

    pinned = app.vault.db.peerSettings.pin.call_args.kwargs["val"]
    assert pinned.enabled is True and pinned.port == 5622
    app.vault.restart_peer_mode.assert_called_once()
    assert DEFAULT_HAB_PRE in app.vault._peer_exposed_aids
    app.vault.extend.assert_called()          # PublishPeerRoleDoer scheduled
    src.fetch.assert_called_once_with(DOI)
    rec = app.vault.db.peerAllowlist.pin.call_args.kwargs["val"]
    assert rec.aid == DOI and rec.endpoint_url == "tcp://127.0.0.1:5621"


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


def test_no_hab_yet_is_a_noop():
    """Empty vault (no identifiers created yet): the hab guard must fire
    BEFORE the listener/settings steps run -- no peer listener without an
    identity to expose, and no AttributeError/StopIteration out of vault
    open."""
    from locksmith.core.direct_transport import ensure_direct_transport
    app = _app(settings=None, no_hab=True)
    ep = Endpoint(mode="direct", scheme="tcp", oobi_ref=DOI)
    # Returns False (DEFERRED, not done) so the window wiring knows to retry
    # once the async InceptDoer creates the default AID.
    assert ensure_direct_transport(
        app, _egf([ep]), MagicMock(), ("bootstrap", "production")) is False
    app.vault.db.peerSettings.pin.assert_not_called()
    app.vault.restart_peer_mode.assert_not_called()


def test_no_direct_endpoints_returns_done():
    """Nothing to pair -> True (done), so the caller does not retry."""
    from locksmith.core.direct_transport import ensure_direct_transport
    app = _app()
    assert ensure_direct_transport(
        app, _egf([]), MagicMock(), ("production",)) is True


def test_direct_authorities_against_real_egf_document():
    from keri_serviceaid.egf.documents import EgfDocument
    from keri_serviceaid.tests.egf.fixtures.make_fixture_egf import fixture_egf
    from locksmith.core.direct_transport import direct_authorities
    _, sad = fixture_egf()
    doc = EgfDocument.from_sad(sad)
    pairs = direct_authorities(doc, ("bootstrap", "production"))
    assert len(pairs) == 1
    auth, ep = pairs[0]
    assert ep.mode == "direct" and ep.oobi_ref == auth.aid
