# -*- encoding: utf-8 -*-
"""Tests for locksmith.plugins.credential_gate — pure predicate, no I/O."""
from locksmith.plugins.credential_gate import RequiredCredential, gate_satisfied
from locksmith.plugins.manager import HeldCredential

REQ = RequiredCredential(
    schema_said="EOBjUL6H9FQdr_PlXVU_cv_iaXdK5Pg8L3M2YQrnHivI",
    issuer_aids=["EOtKW1M3PReijqHMu92uX5FG0fCPwIfH7plPQSifb34-"],
    required_state="active",
)


def _cred(**o):
    base = dict(
        schema_said=REQ.schema_said,
        issuer_aid=REQ.issuer_aids[0],
        state="active",
        chain_verified=True,
        said="E" + "I" * 43,
    )
    base.update(o)
    return HeldCredential(**base)


def test_satisfied_when_all_conditions_met():
    assert gate_satisfied([_cred()], REQ) is True


def test_schema_mismatch_fails():
    assert gate_satisfied([_cred(schema_said="EOther")], REQ) is False


def test_untrusted_issuer_fails():
    assert gate_satisfied([_cred(issuer_aid="EStranger")], REQ) is False


def test_wrong_state_fails():
    assert gate_satisfied([_cred(state="suspended")], REQ) is False
    assert gate_satisfied([_cred(state="revoked")], REQ) is False


def test_escrowed_unverified_chain_fails():
    assert gate_satisfied([_cred(chain_verified=False)], REQ) is False


def test_absent_credential_fails():
    assert gate_satisfied([], REQ) is False


def test_one_matching_among_several_satisfies():
    assert gate_satisfied([_cred(schema_said="EOther"), _cred()], REQ) is True


def test_heldcredential_said_roundtrips():
    said = "E" + "X" * 43
    cred = _cred(said=said)
    assert cred.said == said
