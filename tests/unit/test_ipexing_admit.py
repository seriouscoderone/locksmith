# -*- encoding: utf-8 -*-
"""Regression: ``Admitter.admit`` must admit a real IPEX grant that carries no
``reg`` embed.

``protocoling.ipexGrantExn`` builds the grant's ``e`` block with only ``acdc``
plus optional ``iss``/``anc`` — it never emits a ``reg`` embed. ``Admitter.admit``
used to iterate ``("anc", "reg", "iss", "acdc")`` and hard-index
``embeds[label]``, so every real grant raised ``KeyError: 'reg'`` before any
credential was parsed. ``AdmitDoer.admitDo`` (the UI path) already skips ``reg``
and uses ``.get`` guards, which is why the app worked and only the standalone
method was broken.

This drives the real ``Granter.grant`` -> ``Admitter.admit`` round-trip on a
genuinely issued+saved v1 credential (both halves share one ``hby``/``rgy``),
and asserts the admit completes.
"""
import contextlib

import pytest
from keri.app import habbing, signing
from keri.core import coring, eventing as ke, parsing, scheming, serdering
from keri.kering import Kinds, Vrsn_1_0
from keri.peer import exchanging
from keri.vdr import credentialing, verifying
from keri.vdr.credentialing import Registrar

from locksmith.core.ipexing import Admitter, Granter, _embed_serder

_DATA = {"dt": "2026-07-08T00:00:00.000000+00:00", "score": 1}

# Minimal ACDC schema that admits _DATA; `$id` is filled with the SAID by Schemer.
_SCHEMA_SED = {
    "$id": "",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Test Credential",
    "type": "object",
    "properties": {
        "v": {"type": "string"}, "d": {"type": "string"}, "i": {"type": "string"},
        "ri": {"type": "string"}, "s": {"type": "string"},
        "a": {"oneOf": [
            {"type": "string"},
            {"type": "object",
             "properties": {"d": {"type": "string"}, "i": {"type": "string"},
                            "dt": {"type": "string", "format": "date-time"},
                            "score": {"type": "number"}},
             "additionalProperties": False,
             "required": ["d", "i", "dt", "score"]}]},
    },
    "additionalProperties": False,
    "required": ["v", "d", "i", "ri", "s", "a"],
}


@contextlib.contextmanager
def _issuer_with_saved_credential():
    """Yield (hby, hab, rgy, creder) with one fully-issued, saved v1 credential."""
    with habbing.openHby(name="admit_reg", temp=True, version=Vrsn_1_0) as hby:
        hab = hby.makeHab(name="issuer", transferable=True, version=Vrsn_1_0)
        rgy = credentialing.Regery(hby=hby, name=hby.name, temp=True)
        verifier = verifying.Verifier(hby=hby, reger=rgy.reger)
        # Registrar only needed to construct Credentialer; create() does not use
        # its receipt machinery, so counselor=None is fine for a witnessless hab.
        registrar = Registrar(hby=hby, rgy=rgy, counselor=None)
        credentialer = credentialing.Credentialer(hby=hby, rgy=rgy, registrar=registrar,
                                                   verifier=verifier)
        # Register the schema so the real Verifier can resolve it during admit.
        schemer = scheming.Schemer(sed=dict(_SCHEMA_SED), kind=Kinds.json)
        hby.db.schema.pin(keys=(schemer.said,), val=schemer)

        # Incept the registry witnesslessly: anchor the vcp seal into the KEL and
        # process escrows directly (no receipt wait) so a Tever exists.
        registry = rgy.makeRegistry(name="reg", prefix=hab.pre, noBackers=True)
        rseal = ke.SealEvent(registry.regk, "0", registry.regd)
        hab.interact(data=[dict(i=rseal.i, s=rseal.s, d=rseal.d)], version=Vrsn_1_0)
        registry.anchorMsg(pre=registry.regk, regd=registry.regd,
                           seqner=coring.Seqner(sn=hab.kever.sn),
                           saider=coring.Diger(qb64=hab.kever.serder.said))
        rgy.processEscrows()
        assert registry.regk in rgy.reger.tevers, "registry Tever must exist"

        # Self-issue (issuer == issuee) so the credential lands in this reger,
        # anchoring the TEL iss into the KEL the same witnessless way.
        creder = credentialer.create(regname="reg", recp=hab.pre, schema=schemer.said,
                                     source=None, rules=None, data=_DATA,
                                     version=Vrsn_1_0)
        iss = registry.issue(said=creder.said, dt=creder.attrib["dt"])
        iseal = ke.SealEvent(iss.pre, iss.snh, iss.said)
        hab.interact(data=[dict(i=iseal.i, s=iseal.s, d=iseal.d)], version=Vrsn_1_0)
        registry.anchorMsg(pre=iss.pre, regd=iss.said,
                           seqner=coring.Seqner(sn=hab.kever.sn),
                           saider=coring.Diger(qb64=hab.kever.serder.said))
        rgy.processEscrows()

        # Verify the ACDC into the reger `saved` index (precondition for granting).
        acdc = signing.serialize(creder, coring.Prefixer(qb64=iss.pre),
                                 coring.Seqner(sn=iss.sn), coring.Saider(qb64=iss.said))
        parsing.Parser(version=Vrsn_1_0).parseOne(ims=bytes(acdc), vry=verifier)

        assert rgy.reger.saved.get(keys=(creder.said,)) is not None, \
            "precondition: credential must be saved before granting"
        yield hby, hab, rgy, creder


def test_admit_grant_without_reg_embed_does_not_keyerror():
    with _issuer_with_saved_credential() as (hby, hab, rgy, creder):
        # A real grant: ipexGrantExn emits acdc/iss/anc only — never `reg`.
        granter = Granter(hby=hby, hab=hab, rgy=rgy)
        grant_msg = granter.grant(said=creder.said, recp=hab.pre)
        grant_said = serdering.SerderKERI(raw=bytes(grant_msg)).said

        # sanity: the grant genuinely carries no `reg` embed (the whole point)
        grant = hby.db.exns.get(keys=(grant_said,))
        assert grant is not None, "grant exn should be persisted for cloneMessage"
        assert "reg" not in grant.ked["e"]

        # the bug: this raised KeyError: 'reg' on the ("anc", "reg", ...) loop,
        # then ValueError: Unsupported version = 1.0 on coring.Sadder(v1 embed).
        admitter = Admitter(hby=hby, hab=hab, rgy=rgy)
        admit_said, admit_msg = admitter.admit(said=grant_said)

        assert admit_said
        assert bytes(admit_msg)


def test_embed_serder_is_version_agnostic_for_v1_grant():
    """The shared re-serialization helper (used by both Admitter.admit and
    AdmitDoer.admitDo) must handle the v1 embeds real grants carry, where the
    old coring.Sadder path raised ``Unsupported version = 1.0``."""
    with _issuer_with_saved_credential() as (hby, hab, rgy, creder):
        granter = Granter(hby=hby, hab=hab, rgy=rgy)
        grant_msg = granter.grant(said=creder.said, recp=hab.pre)
        grant_said = serdering.SerderKERI(raw=bytes(grant_msg)).said
        grant, _pathed = exchanging.cloneMessage(hby, grant_said)
        embeds = grant.ked["e"]

        for label in ("anc", "iss", "acdc"):
            ked = embeds[label]
            assert ked["v"].endswith("_") and "10JSON" in ked["v"]  # a v1 embed

            # the old path is what broke: coring.Sadder rejects v1 outright
            with pytest.raises(ValueError, match="Unsupported version"):
                coring.Sadder(ked=ked)

            # the fix round-trips it, preserving version and SAID
            sadder = _embed_serder(label, ked)
            assert ked["v"].encode() in bytes(sadder.raw)
            assert sadder.said == ked["d"]
