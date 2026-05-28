"""Verify Vault wires PeerDoer when peerSettings.enabled is True.

Full Vault construction is heavy (Habery + multiple doers); we assert
on the Vault.__init__ source containing the peer wiring instead.
Integration tests in tests/integration/peer cover the live wiring.
"""
import inspect


def test_vault_init_declares_peer_doer():
    from locksmith.core import vaulting

    src = inspect.getsource(vaulting.Vault.__init__)
    assert "self.peer_doer" in src, "Vault.__init__ must declare self.peer_doer"


def test_peer_doer_constructs_directly(tmp_path):
    """Sanity-check that PeerDoer is import-compatible with the Vault path."""
    from types import SimpleNamespace
    from locksmith.peer.doer import PeerDoer
    from locksmith.peer.records import PeerModeSettings
    from locksmith.db.basing import LocksmithBaser

    baser = LocksmithBaser(name="wiretest", headDirPath=str(tmp_path),
                           reopen=True, temp=True)
    try:
        settings = PeerModeSettings(enabled=True, port=0, bind_host="127.0.0.1")
        hby = SimpleNamespace(habs={"EAID_VAULT": SimpleNamespace(pre="EAID_VAULT")},
                              name="wiretest")
        exchanger = SimpleNamespace(processEvent=lambda *a, **k: None)
        doer = PeerDoer(
            hby=hby, baser=baser, settings=settings,
            exchanger=exchanger, is_destination_exposed=lambda aid: True,
        )
        try:
            assert doer.server is not None
        finally:
            doer.server.close()
    finally:
        baser.close(clear=True)
