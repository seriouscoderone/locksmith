"""Tests for micro-app-template SAID computation."""
from __future__ import annotations

import json

from locksmith.micro_app_template.saidify import (
    PLACEHOLDER,
    compute_said,
    saidify_document,
    verify_said,
)


def test_compute_said_produces_44_char_blake3():
    doc = {"d": "", "ecosystem": {"id": "test"}}
    said = compute_said(doc)
    assert isinstance(said, str)
    assert len(said) == 44
    assert said.startswith("E")  # Blake3-256 CESR prefix


def test_saidify_document_fills_d_field():
    doc = {"d": "", "header": {"id": "carrier-license"}}
    out = saidify_document(doc)
    assert out["d"] != ""
    assert len(out["d"]) == 44


def test_saidify_is_deterministic():
    doc = {"d": "", "header": {"id": "carrier-license"}, "role": {"id": "carrier"}}
    a = saidify_document(json.loads(json.dumps(doc)))  # deep copy
    b = saidify_document(json.loads(json.dumps(doc)))
    assert a["d"] == b["d"]


def test_saidify_does_not_mutate_input():
    doc = {"d": "", "header": {"id": "carrier-license"}}
    saidify_document(doc)
    assert doc["d"] == ""


def test_verify_said_passes_on_stamped_document():
    doc = {"d": "", "header": {"id": "carrier-license"}}
    stamped = saidify_document(doc)
    assert verify_said(stamped) is True


def test_verify_said_fails_on_tampered_document():
    doc = {"d": "", "header": {"id": "carrier-license"}}
    stamped = saidify_document(doc)
    stamped["header"]["id"] = "different-id"
    assert verify_said(stamped) is False


def test_placeholder_constant_is_correct_length():
    assert len(PLACEHOLDER) == 44


def test_saidify_requires_d_field():
    import pytest
    with pytest.raises(KeyError):
        saidify_document({"header": {"id": "x"}})


def test_saidify_independent_of_input_key_order():
    """SAID computation must be independent of the input dict's key order —
    it operates against the canonical (sorted-keys) form."""
    doc_a = {"d": "", "header": {"id": "x"}, "role": {"id": "y"}}
    doc_b = {"role": {"id": "y"}, "header": {"id": "x"}, "d": ""}
    assert saidify_document(doc_a)["d"] == saidify_document(doc_b)["d"]


def test_saidify_matches_canonical_form_round_trip():
    """A stamped doc, written via canonicalize and read back, must still
    verify. This is the round-trip the CLI depends on."""
    import json
    from locksmith.micro_app_template.canonical_json import canonicalize
    doc = {"d": "", "header": {"id": "test", "version": "1.0"}, "role": {"id": "tester"}}
    stamped = saidify_document(doc)
    written = canonicalize(stamped)
    re_read = json.loads(written)
    assert verify_said(re_read) is True
