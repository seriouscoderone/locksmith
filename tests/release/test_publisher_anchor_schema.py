"""Validate the committed publisher_anchor.json is schema-correct.

Until the production ceremony runs, this file is a placeholder. The test asserts
the *shape* is correct so any future overwrite is structurally valid.
"""
import json
from pathlib import Path


def test_publisher_anchor_has_expected_keys():
    path = Path(__file__).resolve().parents[2] / "src" / "locksmith" / "release" / "publisher_anchor.json"
    body = json.loads(path.read_text())
    assert set(body.keys()) == {"publisher_aid", "embedded_kel_hash", "embedded_kel_sn", "witness_oobis"}
    assert isinstance(body["publisher_aid"], str)
    assert isinstance(body["embedded_kel_hash"], str)
    assert isinstance(body["embedded_kel_sn"], int)
    assert isinstance(body["witness_oobis"], list)
    assert len(body["witness_oobis"]) >= 3
    for oobi in body["witness_oobis"]:
        assert oobi.startswith("https://")
