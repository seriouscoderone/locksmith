"""Validate the committed publisher_anchor.example.json is schema-correct.

The REAL ``publisher_anchor.json`` is gitignored + build-injected (privacy
rule: no real publisher AID / witness domains committed). The committed source
of truth is the placeholder template ``publisher_anchor.example.json``; this
test asserts its *shape* is correct so any future build-injected anchor is
structurally valid. Detailed loader/placeholder coverage lives in
``tests/unit/release/test_publisher_anchor_loader.py``.
"""
import json
from pathlib import Path


def test_publisher_anchor_example_has_expected_keys():
    path = (
        Path(__file__).resolve().parents[2]
        / "src" / "locksmith" / "release" / "publisher_anchor.example.json"
    )
    body = json.loads(path.read_text())
    assert {"publisher_aid", "embedded_kel_hash", "embedded_kel_sn", "witness_oobis"}.issubset(set(body.keys()))
    assert isinstance(body["publisher_aid"], str)
    assert isinstance(body["embedded_kel_hash"], str)
    assert isinstance(body["embedded_kel_sn"], int)
    assert isinstance(body["witness_oobis"], list)
    assert len(body["witness_oobis"]) >= 3
    for oobi in body["witness_oobis"]:
        assert oobi.startswith("https://")
