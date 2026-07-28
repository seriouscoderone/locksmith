"""The HOA shell's connection/diagnostics surface.

HoaVaultPage peels identifiers/settings/peers, so an HOA build has no way to
see its own listener port, what address it is telling peers to dial, or
whether the authority is reachable — and there is no in-app log viewer. When
a role request fails with "the administrator's application isn't reachable"
this page is the only field-diagnosis path.

The snapshot is a pure function so the diagnosis it renders is assertable
without a running listener.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from locksmith.peer.records import PeerHealth, PeerModeSettings, PeerRecord
from locksmith.ui.hoa.connection_page import HoaConnectionPage, connection_snapshot


def _vault(baser, *, server=None):
    return SimpleNamespace(db=baser, hby=MagicMock(),
                           peer_doer=SimpleNamespace(server=server) if server else None)


def test_snapshot_reports_not_listening_when_there_is_no_listener(baser):
    snap = connection_snapshot(_vault(baser))
    assert snap.listening is False
    assert snap.port is None
    assert snap.peers == []


def test_snapshot_reports_the_bound_port_and_advertised_address(baser):
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(
        enabled=True, port=5622, bind_host="0.0.0.0",
        advertised_host="192.168.1.20"))
    vault = _vault(baser, server=SimpleNamespace(opened=True, ha=("0.0.0.0", 5622)))
    snap = connection_snapshot(vault)
    assert snap.listening is True
    assert snap.port == 5622
    assert snap.bind_host == "0.0.0.0"
    assert snap.advertised_host == "192.168.1.20"
    assert snap.advertised_url == "tcp://192.168.1.20:5622"


def test_snapshot_flags_a_loopback_advertised_address(baser):
    """The exact bug this page exists to make visible: a wallet advertising
    loopback looks healthy from the inside and is unreachable from outside."""
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(
        enabled=True, port=5622, advertised_host="127.0.0.1"))
    snap = connection_snapshot(_vault(baser))
    assert snap.advertised_is_routable is False


def test_snapshot_does_not_flag_a_lan_address(baser):
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(
        enabled=True, port=5622, advertised_host="192.168.1.20"))
    assert connection_snapshot(_vault(baser)).advertised_is_routable is True


def test_snapshot_carries_per_peer_reachability(baser):
    aid = "E" + "R" * 43
    baser.peerAllowlist.pin(keys=(aid,), val=PeerRecord(
        aid=aid, label="Usurance admin", endpoint_url="tcp://192.168.1.30:5621"))
    baser.peerHealth.pin(keys=(aid,), val=PeerHealth(
        aid=aid, last_probed_at="2026-07-28T12:00:00+00:00",
        last_outcome="refused", last_message="connection refused",
        consecutive_failures=4))
    peers = connection_snapshot(_vault(baser)).peers
    assert len(peers) == 1
    assert peers[0].label == "Usurance admin"
    assert peers[0].endpoint_url == "tcp://192.168.1.30:5621"
    assert peers[0].color == "red"
    assert "4" in peers[0].status


def test_page_renders_the_advertised_address_and_peers(qapp, baser):
    aid = "E" + "R" * 43
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(
        enabled=True, port=5622, advertised_host="192.168.1.20"))
    baser.peerAllowlist.pin(keys=(aid,), val=PeerRecord(
        aid=aid, label="Usurance admin", endpoint_url="tcp://192.168.1.30:5621"))
    page = HoaConnectionPage(lambda: _vault(baser))
    assert "tcp://192.168.1.20:5622" in page.advertised_label.text()
    assert page.peers_list.count() == 1


def test_page_warns_when_advertising_loopback(qapp, baser):
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(
        enabled=True, port=5622, advertised_host="127.0.0.1"))
    page = HoaConnectionPage(lambda: _vault(baser))
    # isVisible() needs a shown top-level; isHidden() is the explicit state.
    assert page.warning_label.isHidden() is False


def test_page_hides_the_warning_for_a_routable_address(qapp, baser):
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(
        enabled=True, port=5622, advertised_host="192.168.1.20"))
    page = HoaConnectionPage(lambda: _vault(baser))
    assert page.warning_label.isHidden() is True


def test_page_refresh_picks_up_a_newly_paired_peer(qapp, baser):
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(
        enabled=True, port=5622, advertised_host="192.168.1.20"))
    vault = _vault(baser)
    page = HoaConnectionPage(lambda: vault)
    assert page.peers_list.count() == 0
    aid = "E" + "R" * 43
    baser.peerAllowlist.pin(keys=(aid,), val=PeerRecord(
        aid=aid, label="Usurance admin", endpoint_url="tcp://192.168.1.30:5621"))
    page.refresh()
    assert page.peers_list.count() == 1


def test_page_survives_construction_with_no_open_vault(qapp):
    """Registered at ui-ready time, before any vault exists."""
    page = HoaConnectionPage(lambda: None)
    assert page.peers_list.count() == 0
    assert "Not listening" in page.listener_label.text()
