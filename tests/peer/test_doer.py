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
