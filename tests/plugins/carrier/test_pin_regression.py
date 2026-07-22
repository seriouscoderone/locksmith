# -*- encoding: utf-8 -*-
"""Tests for carrier plugin trust constants — pin regression against bundled EGF doc."""
import json
import pathlib

from locksmith.plugins.carrier.plugin import (
    CARRIER_LICENSE_SCHEMA_SAID, DOI_ISSUER_AID)

BUNDLE = pathlib.Path("tests/fixtures/carrier_egf_bundle")


def _egf():
    for p in BUNDLE.glob("E*.json"):
        d = json.loads(p.read_text())
        if d.get("spec_version") == "egf-doc/0.1":
            return d
    raise AssertionError("no EGF doc in bundle")


def test_issuer_pin_matches_egf_authority():
    egf = _egf()
    regulator = next(a for a in egf["authorities"] if a["role_id"] == "regulator")
    assert DOI_ISSUER_AID == regulator["aid"]
    assert len(DOI_ISSUER_AID) == 44 and DOI_ISSUER_AID.endswith("-")


def test_license_schema_pin_matches_egf_catalog():
    egf = _egf()
    lic = next(c for c in egf["credentials"] if c["id"] == "carrier_license")
    assert CARRIER_LICENSE_SCHEMA_SAID == lic["schema_said"]
