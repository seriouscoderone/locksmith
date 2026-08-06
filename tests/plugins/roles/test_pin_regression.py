# -*- encoding: utf-8 -*-
"""Role-plugin trust pins vs the bundled usurance-internal EGF — pin drift
is caught structurally, not by prose review (HOA #2 §9.3 pattern)."""
import json
import pathlib

from locksmith.plugins.actuary.plugin import (ACTUARY_ROLE_SCHEMA_SAID,
                                              USURANCE_ADMIN_AID)
from locksmith.plugins.cuo.plugin import CUO_ROLE_SCHEMA_SAID
from locksmith.plugins.product_designer.plugin import PD_ROLE_SCHEMA_SAID

BUNDLE = pathlib.Path("brands/usurance/egf")


def _egf():
    for p in BUNDLE.glob("E*.json"):
        d = json.loads(p.read_text())
        if d.get("spec_version") == "egf-doc/0.1":
            return d
    raise AssertionError("no EGF doc in bundle")


def test_admin_pin_matches_egf_authority():
    egf = _egf()
    admin = next(a for a in egf["authorities"] if a["role_id"] == "admin")
    assert USURANCE_ADMIN_AID == admin["aid"]
    assert admin["phase"] == "production"


def test_schema_pins_match_egf_catalog():
    egf = _egf()
    by_id = {c["id"]: c["schema_said"] for c in egf["credentials"]}
    assert ACTUARY_ROLE_SCHEMA_SAID == by_id["actuary_role"]
    assert PD_ROLE_SCHEMA_SAID == by_id["product_designer_role"]
    assert CUO_ROLE_SCHEMA_SAID == by_id["cuo_role"]


def test_accepted_schema_saids_cover_both_roles():
    egf = _egf()
    assert {ACTUARY_ROLE_SCHEMA_SAID, PD_ROLE_SCHEMA_SAID, CUO_ROLE_SCHEMA_SAID} \
        <= set(egf["accepted_schema_saids"])
