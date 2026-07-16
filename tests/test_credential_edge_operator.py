# -*- encoding: utf-8 -*-
"""Regression coverage for GUI issuance of edge-operator credentials.

An ACDC schema may pin an edge's operator via an ``o`` ``const`` and require
``o`` alongside ``n``/``s`` with ``additionalProperties: false`` (e.g. the
``carrier_license`` NI2I edge back to the adjudicated application). The GUI
"Issue Credential" path used to drop ``o`` at three points -- it parsed only
the edge ``s`` const, never propagated an operator, and hardcoded the issued
edge block to ``{n, s}`` -- so issuing any such credential failed keripy schema
validation.

These tests exercise the three seams end to end: schema parsing, dropdown
extraction, edge-block construction, and a real ``Credentialer.create`` that
validates the issued ACDC against the schema.
"""
from types import SimpleNamespace

import pytest
from hio.base import doing
from keri.app import habbing, grouping
from keri.core import coring, eventing, scheming, serdering
from keri.core import signing as coresigning
from keri.help import helping
from keri.kering import Kinds, Vrsn_1_0
from keri.vdr import credentialing, verifying

from locksmith.ui.vault.credentials.issued.issue import IssueCredentialDialog


# Arbitrary well-formed SAID used as the edge target schema. It only needs to
# be an opaque string the license schema pins via ``s`` const; no such schema
# is registered because JSON-schema validation treats ``n``/``s`` as strings.
EDGE_TARGET_SCHEMA_SAID = "EBSxJSWpGHcTyBYOreTj1NKBudwU5xHPA8pw003XCTDc"
# Any SAID-shaped string works as the edge node reference for schema validation.
EDGE_NODE_SAID = "EBom-R9cX42xENIhMZdlSsMGOw7qMkE8VHcSS9RdEC1a"


def _grant_schema():
    """A minimal v1 ACDC schema whose single edge mandates an operator: the
    ``application`` edge requires ``n``/``s``/``o`` with ``o`` pinned to NI2I
    and ``additionalProperties: false``. ``$id`` is left blank so ``Schemer``
    fills the correct top-level SAID."""
    return {
        "$id": "",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Edge Operator Grant",
        "type": "object",
        "credentialType": "EdgeOperatorGrant",
        "properties": {
            "v": {"type": "string"},
            "d": {"type": "string"},
            "i": {"type": "string"},
            "ri": {"type": "string"},
            "s": {"type": "string"},
            "a": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "d": {"type": "string"},
                            "i": {"type": "string"},
                            "dt": {"type": "string", "format": "date-time"},
                        },
                        "additionalProperties": False,
                        "required": ["d", "i", "dt"],
                    },
                ]
            },
            "e": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "d": {"type": "string"},
                            "application": {
                                "description": "NI2I reference to the adjudicated application.",
                                "type": "object",
                                "properties": {
                                    "n": {"type": "string"},
                                    "s": {"type": "string", "const": EDGE_TARGET_SCHEMA_SAID},
                                    "o": {"type": "string", "const": "NI2I"},
                                },
                                "additionalProperties": False,
                                "required": ["n", "s", "o"],
                            },
                        },
                        "additionalProperties": False,
                        "required": ["d", "application"],
                    },
                ]
            },
        },
        "additionalProperties": False,
        "required": ["v", "d", "i", "ri", "s", "a", "e"],
    }


class _FakeSchemaStore:
    def __init__(self, sed):
        self._schemer = SimpleNamespace(sed=sed)

    def get(self, keys):
        return self._schemer


class _FakeDropdown:
    """Stands in for the QComboBox: index 0 is the placeholder, index 1 holds
    the selected edge credential SAID as userData."""

    def __init__(self, cred_said):
        self._cred_said = cred_said

    def currentIndex(self):
        return 1

    def itemData(self, index):
        return self._cred_said if index == 1 else None


def _dialog_for_schema(sed):
    dlg = IssueCredentialDialog.__new__(IssueCredentialDialog)
    dlg.app = SimpleNamespace(
        vault=SimpleNamespace(hby=SimpleNamespace(db=SimpleNamespace(schema=_FakeSchemaStore(sed))))
    )
    dlg.show_error = lambda message: None
    return dlg


# ---------------------------------------------------------------------------
# Seam 1: schema parsing reads the pinned edge operator.
# ---------------------------------------------------------------------------

def test_parse_edge_requirements_reads_operator_const():
    dlg = _dialog_for_schema(_grant_schema())

    reqs = dlg._parse_edge_requirements("EanySchemaSaid")

    assert len(reqs) == 1
    application = reqs[0]
    assert application["name"] == "application"
    assert application["schema_said"] == EDGE_TARGET_SCHEMA_SAID
    assert application["operator"] == "NI2I"


# ---------------------------------------------------------------------------
# Seam 2: dropdown extraction propagates the operator to the doer's edges dict.
# ---------------------------------------------------------------------------

def test_extract_edge_credentials_propagates_operator():
    dlg = IssueCredentialDialog.__new__(IssueCredentialDialog)
    dlg._edge_dropdowns = {
        "application": {
            "dropdown": _FakeDropdown(EDGE_NODE_SAID),
            "edge_req": {
                "name": "application",
                "schema_said": EDGE_TARGET_SCHEMA_SAID,
                "operator": "NI2I",
            },
        }
    }

    edges = dlg._extract_edge_credentials()

    assert edges["application"]["cred_said"] == EDGE_NODE_SAID
    assert edges["application"]["schema_said"] == EDGE_TARGET_SCHEMA_SAID
    assert edges["application"]["operator"] == "NI2I"


# ---------------------------------------------------------------------------
# Seam 3: the edge-block builder emits n/s/o.
# ---------------------------------------------------------------------------

def test_build_edges_block_includes_operator():
    from locksmith.core.credentialing import build_edges_block

    block = build_edges_block(
        {
            "application": {
                "cred_said": EDGE_NODE_SAID,
                "schema_said": EDGE_TARGET_SCHEMA_SAID,
                "operator": "NI2I",
            }
        }
    )

    assert block is not None
    assert block["application"] == {
        "n": EDGE_NODE_SAID,
        "s": EDGE_TARGET_SCHEMA_SAID,
        "o": "NI2I",
    }


def test_build_edges_block_omits_operator_when_absent():
    from locksmith.core.credentialing import build_edges_block

    block = build_edges_block(
        {"application": {"cred_said": EDGE_NODE_SAID, "schema_said": EDGE_TARGET_SCHEMA_SAID}}
    )

    assert "o" not in block["application"]
    assert block["application"]["n"] == EDGE_NODE_SAID


def test_build_edges_block_returns_none_without_edges():
    from locksmith.core.credentialing import build_edges_block

    assert build_edges_block({}) is None
    assert build_edges_block(None) is None


# ---------------------------------------------------------------------------
# End to end: a real Credentialer issues + validates an edge-operator ACDC.
# ---------------------------------------------------------------------------

def _make_party(name, salt):
    hby = habbing.Habery(name=name, temp=True, salt=coresigning.Salter(raw=salt).qb64)
    hab = hby.makeHab(name=name, transferable=True, wits=[], toad=0, version=Vrsn_1_0)
    rgy = credentialing.Regery(hby=hby, name=name, temp=True)
    return hby, hab, rgy


def _ensure_registry(hby, hab, rgy, name):
    counselor = grouping.Counselor(hby=hby)
    registrar = credentialing.Registrar(hby=hby, rgy=rgy, counselor=counselor)
    registry = rgy.makeRegistry(name=name, prefix=hab.pre, noBackers=True,
                                nonce=coresigning.Salter().qb64)
    rseal = eventing.SealEvent(registry.regk, "0", registry.regd)
    rseal = dict(i=rseal.i, s=rseal.s, d=rseal.d)
    anc = hab.interact(data=[rseal], version=Vrsn_1_0)
    registrar.incept(iserder=registry.vcp,
                     anc=serdering.SerderKERI(raw=bytes(anc)))
    doist = doing.Doist(real=False, tock=1.0)
    deeds = doist.enter(doers=[registrar])
    try:
        for _ in range(64):
            if registrar.complete(pre=registry.regk, sn=0):
                return registry
            rgy.processEscrows()
            doist.recur(deeds=deeds)
        raise AssertionError("registry inception did not complete")
    finally:
        doist.exit(deeds=deeds)


@pytest.fixture
def issuer_party():
    hby, hab, rgy = _make_party("edge-op-issuer", salt=b"0123456789abcdef")
    schemer = scheming.Schemer(sed=_grant_schema(), kind=Kinds.json)
    hby.db.schema.pin(keys=(schemer.said,), val=schemer)
    _ensure_registry(hby, hab, rgy, schemer.said)
    try:
        yield hby, hab, rgy, schemer
    finally:
        rgy.close()
        hby.close(clear=True)


def test_issued_credential_with_edge_operator_passes_schema_validation(issuer_party):
    from locksmith.core.credentialing import build_edges_block

    hby, hab, rgy, schemer = issuer_party
    verifier = verifying.Verifier(hby=hby, reger=rgy.reger)
    registrar = credentialing.Registrar(hby=hby, rgy=rgy,
                                         counselor=grouping.Counselor(hby=hby))
    credentialer = credentialing.Credentialer(hby=hby, rgy=rgy, registrar=registrar,
                                               verifier=verifier)

    edges = {
        "application": {
            "cred_said": EDGE_NODE_SAID,
            "schema_said": EDGE_TARGET_SCHEMA_SAID,
            "operator": "NI2I",
        }
    }
    source = build_edges_block(edges)

    creder = credentialer.create(
        regname=schemer.said, recp=hab.pre, schema=schemer.said, source=source,
        rules=None, data={}, private=False, version=Vrsn_1_0)

    # The issued edge carries the pinned operator ...
    assert creder.sad["e"]["application"]["o"] == "NI2I"
    assert creder.sad["e"]["application"]["s"] == EDGE_TARGET_SCHEMA_SAID
    # ... and the full ACDC validates against the schema that mandates it.
    assert schemer.verify(creder.raw) is True


def test_edge_block_without_operator_is_rejected_by_schema(issuer_party):
    """Guards the regression: an edge block missing ``o`` must fail issuance,
    proving the schema genuinely mandates the operator this fix supplies."""
    from keri.kering import ConfigurationError, ValidationError

    from locksmith.core.credentialing import build_edges_block

    hby, hab, rgy, schemer = issuer_party
    verifier = verifying.Verifier(hby=hby, reger=rgy.reger)
    registrar = credentialing.Registrar(hby=hby, rgy=rgy,
                                         counselor=grouping.Counselor(hby=hby))
    credentialer = credentialing.Credentialer(hby=hby, rgy=rgy, registrar=registrar,
                                               verifier=verifier)

    source = build_edges_block(
        {"application": {"cred_said": EDGE_NODE_SAID, "schema_said": EDGE_TARGET_SCHEMA_SAID}}
    )

    # create() wraps the schema failure in ConfigurationError; accept the
    # underlying ValidationError too so a keripy bump that unwraps it does not
    # spuriously break this guard.
    with pytest.raises((ConfigurationError, ValidationError)):
        credentialer.create(
            regname=schemer.said, recp=hab.pre, schema=schemer.said, source=source,
            rules=None, data={}, private=False, version=Vrsn_1_0)
