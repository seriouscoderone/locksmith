# -*- encoding: utf-8 -*-
"""Role-plugin trust pins vs the bundled usurance-internal EGF — pin drift
is caught structurally, not by prose review (HOA #2 §9.3 pattern)."""
import json
import pathlib

from locksmith.plugins.actuary.plugin import (ACTUARY_ROLE_SCHEMA_SAID,
                                              USURANCE_ADMIN_AID)
from locksmith.plugins.cuo.page import PRODUCT_MANDATE_SCHEMA_SAID
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


# --- the mandate schema, which is NOT a role credential ---------------------------
#
# `PRODUCT_MANDATE_SCHEMA_SAID` cannot join `test_schema_pins_match_egf_catalog`
# above: that test resolves `egf["credentials"]` by `id`, and the mandate has no
# entry there. The EGF catalog lists the three ROLE credentials; the mandate is
# declared by the CUO micro-app template, as the credential its
# `declare_product_mandate` command mints. Measured -- `egf["credentials"]` ids are
# exactly cuo_role, actuary_role, product_designer_role. So this walks the
# provenance chain the pin actually has, instead of asserting a literal against
# itself.


def test_the_mandate_schema_pin_is_the_one_the_egf_declares():
    """EGF doc -> cuo micro-app -> the minting command -> the exported credential.

    A wrong pin here fails SILENTLY in the direction that matters:
    `existing_mandates()` reads `reger.schms` with it, and a SAID nothing was
    filed under returns an empty list -- indistinguishable from a vault holding no
    mandates, so the overlap gate stops gating with nothing raising.
    """
    egf = _egf()
    said = next(m["said"] for m in egf["micro_apps"] if m["role_id"] == "cuo")
    template = json.loads((BUNDLE / f"{said}.json").read_text())

    command = next(c for c in template["commands"]
                   if c["id"] == "declare_product_mandate")
    export = next(e for e in template["credentials"]["exports"]
                  if e["id"] == command["mints_credential_id"])

    assert PRODUCT_MANDATE_SCHEMA_SAID == export["schema"]["schema_said"], (
        "the CUO page pins a schema the EGF's own minting declaration does not "
        "name; existing_mandates() would read an empty registry and the overlap "
        "gate would pass everything")
    assert PRODUCT_MANDATE_SCHEMA_SAID in egf["accepted_schema_saids"]


def test_the_bundled_mandate_schema_saidifies_to_the_pin():
    """The other end of the chain, computed rather than compared: the bundled file
    must actually hash to the pinned SAID. This is the same computation
    `CuoMandatePage._ensure_mandate_schema_pinned` performs at anchor time, so a
    re-SAIDed schema fails here in 2 seconds instead of at the demo."""
    from keri.core import scheming
    from keri.kering import Kinds

    path = BUNDLE / f"{PRODUCT_MANDATE_SCHEMA_SAID}.json"
    assert path.is_file(), f"the pinned mandate schema is not bundled at {path}"
    schemer = scheming.Schemer(sed=json.loads(path.read_text()), kind=Kinds.json)
    assert schemer.said == PRODUCT_MANDATE_SCHEMA_SAID
