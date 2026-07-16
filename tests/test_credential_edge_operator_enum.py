# -*- encoding: utf-8 -*-
"""Regression coverage for GUI issuance of edge-operator credentials whose
operator is *required but not pinned*.

A companion to ``test_credential_edge_operator.py``. There the schema pins an
edge's operator via an ``o`` ``const``, so the GUI can propagate it silently.
Here the schema mandates ``o`` (``required: ["n","s","o"]``,
``additionalProperties: false``) but leaves the choice open as an ``enum``
(``["I2I","NI2I","DI2I"]``). Without a GUI affordance the issuer has no way to
supply an operator: ``build_edges_block`` drops ``o`` and ``Credentialer.create``
fails keripy schema validation.

These tests exercise the same seams: schema parsing surfaces the allowed
operator values, dropdown extraction propagates the chosen one, the edge-block
builder emits ``o``, and a real ``Credentialer.create`` validates the issued
ACDC against the enum-constrained schema.
"""
from types import SimpleNamespace

import pytest
from hio.base import doing
from keri.app import habbing, grouping
from keri.core import coring, eventing, scheming, serdering
from keri.core import signing as coresigning
from keri.kering import Kinds, Vrsn_1_0
from keri.vdr import credentialing, verifying

from locksmith.ui.vault.credentials.issued.issue import IssueCredentialDialog


EDGE_TARGET_SCHEMA_SAID = "ENbhxLlFINUDp1EU4mV5RVVL-CS6Ub72zXY89EcM7Ccb"
EDGE_NODE_SAID = "EBom-R9cX42xENIhMZdlSsMGOw7qMkE8VHcSS9RdEC1a"
OPERATOR_OPTIONS = ["I2I", "NI2I", "DI2I"]
CHOSEN_OPERATOR = "NI2I"


def _grant_schema():
    """A minimal v1 ACDC schema whose single edge mandates an operator but does
    not pin it: the ``application`` edge requires ``n``/``s``/``o`` with ``o``
    given as an ``enum`` (not a ``const``) and ``additionalProperties: false``.
    ``$id`` is left blank so ``Schemer`` fills the correct top-level SAID."""
    return {
        "$id": "",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Edge Operator Enum Grant",
        "type": "object",
        "credentialType": "EdgeOperatorEnumGrant",
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
                                "description": "Reference to the adjudicated application.",
                                "type": "object",
                                "properties": {
                                    "n": {"type": "string"},
                                    "s": {"type": "string", "const": EDGE_TARGET_SCHEMA_SAID},
                                    "o": {"type": "string", "enum": OPERATOR_OPTIONS},
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
    """Stands in for the credential QComboBox: index 0 is the placeholder,
    index 1 holds the selected edge credential SAID as userData."""

    def __init__(self, cred_said):
        self._cred_said = cred_said

    def currentIndex(self):
        return 1

    def itemData(self, index):
        return self._cred_said if index == 1 else None


class _FakeOperatorDropdown:
    """Stands in for the operator QComboBox: index 0 is the placeholder, later
    indices hold an operator string as userData."""

    def __init__(self, operator, index=1):
        self._operator = operator
        self._index = index

    def currentIndex(self):
        return self._index

    def itemData(self, index):
        return self._operator if index == self._index else None


def _dialog_for_schema(sed):
    dlg = IssueCredentialDialog.__new__(IssueCredentialDialog)
    dlg.app = SimpleNamespace(
        vault=SimpleNamespace(hby=SimpleNamespace(db=SimpleNamespace(schema=_FakeSchemaStore(sed))))
    )
    dlg.show_error = lambda message: None
    return dlg


# ---------------------------------------------------------------------------
# Seam 1: schema parsing surfaces the allowed operator values (no fixed value).
# ---------------------------------------------------------------------------

def test_parse_edge_requirements_reads_operator_options():
    dlg = _dialog_for_schema(_grant_schema())

    reqs = dlg._parse_edge_requirements("EanySchemaSaid")

    assert len(reqs) == 1
    application = reqs[0]
    assert application["name"] == "application"
    assert application["schema_said"] == EDGE_TARGET_SCHEMA_SAID
    # A required-but-unpinned operator surfaces its allowed values ...
    assert application["operator_options"] == OPERATOR_OPTIONS
    # ... and carries no fixed operator (nothing to pin).
    assert "operator" not in application


# ---------------------------------------------------------------------------
# Seam 2: dropdown extraction propagates the *chosen* operator.
# ---------------------------------------------------------------------------

def test_extract_edge_credentials_propagates_chosen_operator():
    dlg = IssueCredentialDialog.__new__(IssueCredentialDialog)
    dlg._edge_dropdowns = {
        "application": {
            "dropdown": _FakeDropdown(EDGE_NODE_SAID),
            "operator_dropdown": _FakeOperatorDropdown(CHOSEN_OPERATOR),
            "edge_req": {
                "name": "application",
                "schema_said": EDGE_TARGET_SCHEMA_SAID,
                "operator_options": OPERATOR_OPTIONS,
            },
        }
    }

    edges = dlg._extract_edge_credentials()

    assert edges["application"]["cred_said"] == EDGE_NODE_SAID
    assert edges["application"]["schema_said"] == EDGE_TARGET_SCHEMA_SAID
    assert edges["application"]["operator"] == CHOSEN_OPERATOR


def test_extract_edge_credentials_omits_operator_when_unselected():
    """If the operator dropdown is still on its placeholder, no ``o`` is
    propagated -- validation (not extraction) is responsible for blocking that
    case."""
    dlg = IssueCredentialDialog.__new__(IssueCredentialDialog)
    dlg._edge_dropdowns = {
        "application": {
            "dropdown": _FakeDropdown(EDGE_NODE_SAID),
            "operator_dropdown": _FakeOperatorDropdown(None, index=0),
            "edge_req": {
                "name": "application",
                "schema_said": EDGE_TARGET_SCHEMA_SAID,
                "operator_options": OPERATOR_OPTIONS,
            },
        }
    }

    edges = dlg._extract_edge_credentials()

    assert edges["application"]["cred_said"] == EDGE_NODE_SAID
    assert "operator" not in edges["application"]


# ---------------------------------------------------------------------------
# Seam 3: the edge-block builder emits the chosen operator as ``o``.
# ---------------------------------------------------------------------------

def test_build_edges_block_includes_chosen_operator():
    from locksmith.core.credentialing import build_edges_block

    block = build_edges_block(
        {
            "application": {
                "cred_said": EDGE_NODE_SAID,
                "schema_said": EDGE_TARGET_SCHEMA_SAID,
                "operator": CHOSEN_OPERATOR,
            }
        }
    )

    assert block is not None
    assert block["application"] == {
        "n": EDGE_NODE_SAID,
        "s": EDGE_TARGET_SCHEMA_SAID,
        "o": CHOSEN_OPERATOR,
    }


# ---------------------------------------------------------------------------
# End to end: a real Credentialer issues + validates an enum-operator ACDC.
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
    hby, hab, rgy = _make_party("edge-op-enum-issuer", salt=b"0123456789abcdef")
    schemer = scheming.Schemer(sed=_grant_schema(), kind=Kinds.json)
    hby.db.schema.pin(keys=(schemer.said,), val=schemer)
    _ensure_registry(hby, hab, rgy, schemer.said)
    try:
        yield hby, hab, rgy, schemer
    finally:
        rgy.close()
        hby.close(clear=True)


def test_issued_credential_with_chosen_operator_passes_schema_validation(issuer_party):
    from locksmith.core.credentialing import build_edges_block

    hby, hab, rgy, schemer = issuer_party
    verifier = verifying.Verifier(hby=hby, reger=rgy.reger)
    registrar = credentialing.Registrar(hby=hby, rgy=rgy,
                                         counselor=grouping.Counselor(hby=hby))
    credentialer = credentialing.Credentialer(hby=hby, rgy=rgy, registrar=registrar,
                                               verifier=verifier)

    source = build_edges_block(
        {
            "application": {
                "cred_said": EDGE_NODE_SAID,
                "schema_said": EDGE_TARGET_SCHEMA_SAID,
                "operator": CHOSEN_OPERATOR,
            }
        }
    )

    creder = credentialer.create(
        regname=schemer.said, recp=hab.pre, schema=schemer.said, source=source,
        rules=None, data={}, private=False, version=Vrsn_1_0)

    # The issued edge carries the chosen operator ...
    assert creder.sad["e"]["application"]["o"] == CHOSEN_OPERATOR
    assert creder.sad["e"]["application"]["s"] == EDGE_TARGET_SCHEMA_SAID
    # ... and the full ACDC validates against the enum-constrained schema.
    assert schemer.verify(creder.raw) is True


def test_edge_block_without_operator_is_rejected_by_enum_schema(issuer_party):
    """Guards the regression: an edge block missing ``o`` must fail issuance,
    proving the enum schema genuinely mandates the operator this fix supplies."""
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

    with pytest.raises((ConfigurationError, ValidationError)):
        credentialer.create(
            regname=schemer.said, recp=hab.pre, schema=schemer.said, source=source,
            rules=None, data={}, private=False, version=Vrsn_1_0)
