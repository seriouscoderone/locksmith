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
