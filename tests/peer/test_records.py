from datetime import datetime, timezone

from locksmith.peer.records import PeerModeSettings, PeerRecord


def test_peer_record_defaults():
    rec = PeerRecord(aid="EAID123", label="Bob", endpoint_url="tcp://10.0.0.1:5621")
    assert rec.aid == "EAID123"
    assert rec.label == "Bob"
    assert rec.endpoint_url == "tcp://10.0.0.1:5621"
    assert rec.paired_at == ""
    assert rec.last_contacted_at == ""


def test_peer_record_with_timestamps():
    now = datetime.now(timezone.utc).isoformat()
    rec = PeerRecord(
        aid="EAID123",
        label="Bob",
        endpoint_url="tcp://10.0.0.1:5621",
        paired_at=now,
        last_contacted_at=now,
    )
    assert rec.paired_at == now
    assert rec.last_contacted_at == now


def test_peer_mode_settings_defaults():
    s = PeerModeSettings()
    assert s.enabled is False
    assert s.port == 5621
    assert s.bind_host == "0.0.0.0"
    assert s.advertised_host == ""


def test_baser_exposes_peer_komers(baser):
    assert baser.peerAllowlist is not None
    assert baser.peerSettings is not None
