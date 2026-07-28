from types import SimpleNamespace
from unittest.mock import MagicMock

from locksmith.peer.records import PeerModeSettings
from locksmith.ui.vault.identifiers import identifier_sections


def test_oobi_dropdown_includes_peer_role():
    """The role_map at identifier_sections.py is the source of truth for
    which roles the dropdown surfaces."""
    role_map_source = identifier_sections.__file__
    with open(role_map_source) as f:
        src = f.read()
    assert '"Peer": "peer"' in src or "'Peer': 'peer'" in src, \
        "OOBI role dropdown must include a Peer entry"


def test_publish_peer_role_dispatches_doer_to_vault(monkeypatch):
    """_publish_peer_role must dispatch a PublishPeerRoleDoer onto the
    vault's doist — that's how the rpys reach the witnesses. Local-only
    publishing has been the bug: it left witness.keri.host with nothing
    peer-role to serve.
    """
    extended = []
    vault = SimpleNamespace(
        db=SimpleNamespace(
            peerSettings=SimpleNamespace(
                get=lambda keys: PeerModeSettings(
                    advertised_host="192.168.1.42", port=5621
                )
            )
        ),
        hby=MagicMock(),
        signals=MagicMock(),
        extend=lambda doers: extended.extend(doers),
    )
    app = SimpleNamespace(vault=vault)
    hab = SimpleNamespace(pre="EAID_ALICE", db=MagicMock())

    captured_kwargs = {}

    class _SpyDoer:
        def __init__(self, **kwa):
            captured_kwargs.update(kwa)

    monkeypatch.setattr(
        "locksmith.peer.publishing.PublishPeerRoleDoer", _SpyDoer
    )

    class _Holder(identifier_sections.IdentifierViewSectionsMixin):
        pass

    holder = _Holder()
    holder.app = app
    holder.hab = hab
    holder._publish_peer_role()

    assert len(extended) == 1, "expected exactly one doer to be extended"
    assert isinstance(extended[0], _SpyDoer)
    assert captured_kwargs["hab"] is hab
    assert captured_kwargs["hby"] is vault.hby
    assert captured_kwargs["url"] == "tcp://192.168.1.42:5621"
    assert captured_kwargs["signal_bridge"] is vault.signals


def test_publish_peer_role_resolves_a_blank_advertised_host(monkeypatch):
    """The published /loc/scheme rpy is what witnesses serve and what a peer
    dials. With the advertised field left blank it used to publish loopback,
    which is unreachable for every peer that isn't this machine."""
    extended = []
    vault = SimpleNamespace(
        db=SimpleNamespace(
            peerSettings=SimpleNamespace(
                get=lambda keys: PeerModeSettings(advertised_host="", port=5621)
            )
        ),
        hby=MagicMock(),
        signals=MagicMock(),
        extend=lambda doers: extended.extend(doers),
    )
    captured_kwargs = {}

    class _SpyDoer:
        def __init__(self, **kwa):
            captured_kwargs.update(kwa)

    monkeypatch.setattr("locksmith.peer.publishing.PublishPeerRoleDoer", _SpyDoer)
    monkeypatch.setattr(
        "locksmith.peer.netaddr.resolve_advertised_host", lambda: "192.168.1.20")

    class _Holder(identifier_sections.IdentifierViewSectionsMixin):
        pass

    holder = _Holder()
    holder.app = SimpleNamespace(vault=vault)
    holder.hab = SimpleNamespace(pre="EAID_ALICE", db=MagicMock())
    holder._publish_peer_role()

    assert captured_kwargs["url"] == "tcp://192.168.1.20:5621"
