from types import SimpleNamespace

from locksmith.peer.doer import PeerDoer
from locksmith.peer.records import PeerModeSettings


def _fake_hby():
    hab = SimpleNamespace(pre="EAID_VAULT")
    return SimpleNamespace(habs={"EAID_VAULT": hab}, name="fake-hby")


def _fake_exchanger():
    return SimpleNamespace(processEvent=lambda *a, **k: None)


def test_disabled_settings_yields_no_inner_doers(baser):
    settings = PeerModeSettings(enabled=False)
    doer = PeerDoer(
        hby=_fake_hby(),
        baser=baser,
        settings=settings,
        exchanger=_fake_exchanger(),
        is_destination_exposed=lambda aid: True,
    )
    assert doer.server is None
    assert doer.directant is None


def test_enabled_settings_constructs_server_and_directant(baser):
    settings = PeerModeSettings(enabled=True, port=0, bind_host="127.0.0.1")
    doer = PeerDoer(
        hby=_fake_hby(),
        baser=baser,
        settings=settings,
        exchanger=_fake_exchanger(),
        is_destination_exposed=lambda aid: True,
    )
    try:
        assert doer.server is not None
        assert doer.directant is not None
        assert doer.shim is not None
    finally:
        if doer.server is not None:
            doer.server.close()


def test_server_doer_recur_no_ops_after_close(baser):
    """Regression: closing the socket out-of-band must not crash the
    stale GuardedServerDoer's recur. Stock hio ServerDoer raises
    AttributeError on accept(None.ss); the guard makes it inert.
    """
    settings = PeerModeSettings(enabled=True, port=0, bind_host="127.0.0.1")
    doer = PeerDoer(
        hby=_fake_hby(),
        baser=baser,
        settings=settings,
        exchanger=_fake_exchanger(),
        is_destination_exposed=lambda aid: True,
    )
    server_doer = doer.doers[0]
    try:
        doer.server.reopen()
        assert doer.server.opened is True

        doer.server.close()
        assert doer.server.opened is False
        assert doer.server.ss is None

        # Stock ServerDoer.recur would AttributeError here. Guard returns
        # False without touching the dead socket.
        result = server_doer.recur(tyme=0.0)
        assert result is False
    finally:
        if doer.server is not None and doer.server.opened:
            doer.server.close()
