"""Assemble must not be clickable before it can succeed.

`designerPage.assemble` used to be enabled by row selection alone. But a
`product_bundle` carries an NI2I edge to the MANDATE, and the mandate is issued by
a DIFFERENT peer (the CUO) — so it has to be disclosed, indexed and TEL-verified
here first. Clicking early produced a raw keripy failure in the banner ("Failure
to verify credential ... chain mandate(...)", "TEL event ... did not complete")
that names nothing a user can act on, and the four-window arc had to paper over it
with a retry loop.

These tests drive `_mandate_blocker` against a REAL `Regery`/`Verifier` rather
than a mock, because the gate's authority is `Verifier.verifyChain` itself — the
very call the issuance makes. A mocked reger would let the gate and the issuance
drift apart, which is the whole failure mode being fixed.

The four states below are the four points `verifyChain` returns None at, in order
(`keripy vdr/verifying.py:336-380`).
"""
from types import SimpleNamespace

import pytest
from keri.app import habbing
from keri.core import coring
from keri.vdr import credentialing

from locksmith.plugins.product_designer.page import ProductDesignerPage

MANDATE_SCHEMA = "EFYdgrOvpXpxTkVSVl6dRs1lueELnH9cqxpctqwqpVr5"


class _Gate:
    """`_mandate_blocker` and its two collaborators, off the QWidget.

    The method only reads `self._app` and calls `self._designer_hab`, so binding it
    to a plain object exercises the real logic without a Qt page — and without
    stubbing any part of the keripy read path, which is the part that matters."""

    def __init__(self, app, hab):
        self._app = app
        self._hab = hab

    _mandate_blocker = ProductDesignerPage._mandate_blocker

    def _designer_hab(self, _vault):
        return self._hab


@pytest.fixture
def gate():
    # No `base=`: hio's Filer rejects an absolute base, and `temp=True` already
    # puts the whole keystore under its own throwaway directory.
    with habbing.openHby(name="designer-gate", temp=True) as hby:
        hab = hby.makeHab(name="designer", wits=[], toad="0")
        rgy = credentialing.Regery(hby=hby, name="designer-gate", temp=True)
        app = SimpleNamespace(vault=SimpleNamespace(hby=hby, rgy=rgy))
        yield _Gate(app, hab), rgy.reger


def test_an_unresolved_mandate_edge_blocks(gate):
    g, _ = gate
    blocker = g._mandate_blocker("")
    assert blocker is not None and "did not resolve" in blocker


def test_a_mandate_that_has_not_arrived_blocks_and_names_it(gate):
    """The state the four-window arc actually hits: the designer holds the rate
    program but the CUO's mandate has not been disclosed to it yet."""
    g, _ = gate
    said = "E" + "A" * 43
    blocker = g._mandate_blocker(said)
    assert blocker is not None
    assert "Waiting for mandate" in blocker and "CUO" in blocker
    assert said[:12] in blocker, "the user has to be told WHICH mandate"


def test_a_held_but_unindexed_mandate_blocks(gate, monkeypatch):
    """Body present, `reger.saved` empty — the exact gap `_index_disclosed` exists
    to close, and the one that made an attestation fail one second AFTER its
    mandate's TEL had landed."""
    g, reger = gate
    said = "E" + "B" * 43
    monkeypatch.setattr(type(reger.creds), "get",
                        lambda self, keys: object() if keys == (said,) else None)
    blocker = g._mandate_blocker(said)
    assert blocker is not None and "not yet usable as a chain node" in blocker


def test_a_mandate_without_its_tel_blocks_and_says_why(gate, monkeypatch):
    """Body and index present, no TEL. The ACDC spec allows the registry state
    proof attached OR out-of-band; this ecosystem chose out-of-band, so until
    peer_sync fetches the TEL, issued-vs-revoked is genuinely unknown here."""
    g, reger = gate
    said = "E" + "C" * 43
    monkeypatch.setattr(type(reger.creds), "get",
                        lambda self, keys: object() if keys == (said,) else None)
    monkeypatch.setattr(type(reger.saved), "get",
                        lambda self, keys: coring.Saider(qb64=g._hab.pre)
                        if keys == said else None)
    blocker = g._mandate_blocker(said)
    assert blocker is not None
    assert "registry state" in blocker and "TEL" in blocker


def test_the_gate_defers_to_verify_chain_not_to_its_own_checks(gate, monkeypatch):
    """All three granular checks satisfied, `verifyChain` still says no: the gate
    must stay closed. This is what keeps it from drifting away from the issuance —
    the granular checks only produce the MESSAGE, never the verdict."""
    g, reger = gate
    said = "E" + "D" * 43
    # Enough of a credential for verifyChain to RETURN None rather than raise:
    # under NI2I it skips the `attrib` checks and bails on `creder.regid not in
    # self.tevers`. A bare object() would raise on .regid and land in the gate's
    # except branch, which is a different code path and would not test this.
    creder = SimpleNamespace(regid="E" + "R" * 43, attrib={}, said=said)
    monkeypatch.setattr(type(reger.creds), "get",
                        lambda self, keys: creder
                        if keys in (said, (said,)) else None)
    monkeypatch.setattr(type(reger.saved), "get",
                        lambda self, keys: coring.Saider(qb64=g._hab.pre)
                        if keys == said else None)
    monkeypatch.setattr(type(reger.tels), "get",
                        lambda self, keys, on=0: b"present")
    blocker = g._mandate_blocker(said)
    assert blocker is not None, (
        "verifyChain returned None for this SAID, so issuance would fail — the "
        "gate must not open just because the three cheap checks passed")
    assert "not yet verifiable as a chain node" in blocker


def test_a_missing_vault_blocks_rather_than_raising(gate):
    """Fails toward BLOCKED: the gate never lets an unreadable state through."""
    g, _ = gate
    g._app = SimpleNamespace(vault=None)
    blocker = g._mandate_blocker("E" + "E" * 43)
    assert blocker is not None and "No open vault" in blocker
