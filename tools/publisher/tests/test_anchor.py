import json
from pathlib import Path

from locksmith_publisher.anchor import (
    PublisherAnchor,
    write_publisher_anchor,
    write_publisher_summary,
)


def make_anchor(tmp_path: Path) -> PublisherAnchor:
    return PublisherAnchor(
        publisher_aid="EAbc123",
        embedded_kel_hash="EHsh456",
        embedded_kel_sn=0,
        witness_oobis=[
            "https://api.keri.host/witness/oobi/Bwit1",
            "https://api.keri.host/witness/oobi/Bwit2",
            "https://api.keri.host/witness/oobi/Bwit3",
        ],
    )


def test_write_publisher_anchor_produces_expected_json(tmp_path: Path) -> None:
    anchor = make_anchor(tmp_path)
    out = tmp_path / "publisher_anchor.json"
    write_publisher_anchor(anchor, out)
    body = json.loads(out.read_text())
    assert body == {
        "publisher_aid": "EAbc123",
        "embedded_kel_hash": "EHsh456",
        "embedded_kel_sn": 0,
        "witness_oobis": [
            "https://api.keri.host/witness/oobi/Bwit1",
            "https://api.keri.host/witness/oobi/Bwit2",
            "https://api.keri.host/witness/oobi/Bwit3",
        ],
    }


def test_write_publisher_summary_writes_aid_and_latest_event(tmp_path: Path) -> None:
    anchor = make_anchor(tmp_path)
    out = tmp_path / "publisher-aid.json"
    write_publisher_summary(anchor, out, latest_kel_url="https://releases.keri.host/publisher/v1/kel-events/")
    body = json.loads(out.read_text())
    assert body["publisher_aid"] == "EAbc123"
    assert body["latest_kel_hash"] == "EHsh456"
    assert body["latest_kel_sn"] == 0
    assert body["kel_events_url"] == "https://releases.keri.host/publisher/v1/kel-events/"
    assert body["witnesses"] == anchor.witness_oobis


def test_publisher_anchor_rejects_fewer_than_three_witnesses() -> None:
    import pytest
    with pytest.raises(ValueError, match="at least 3 witnesses"):
        PublisherAnchor(
            publisher_aid="E1",
            embedded_kel_hash="E2",
            embedded_kel_sn=0,
            witness_oobis=["https://api.keri.host/witness/oobi/Bwit1"],
        )
