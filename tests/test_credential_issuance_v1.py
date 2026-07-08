"""KERI v2 v1-hold (Task 6): credential issuance yields a v1 ACDC carrying the
v1 `ri` registry field.

keripy's v2 ACDC issuance is stubbed upstream — ``proving.credential`` still
hardcodes the v1 ``ri`` field, which the v2 ``SerderACDC`` rejects. Locksmith
issues via the fork's additive ``Credentialer.create(version=Vrsn_1_0)`` seam,
producing a valid v1 ``ACDC10JSON`` credential. The registry ``vcp``/``iss`` are
already v1 (the VDR stack is v1-pinned upstream), so only the ACDC needs the pin.

This exercises the real keripy ``Credentialer.create`` (the seam Locksmith calls
at credentialing.py) with a real registry; ``validate`` is stubbed because schema
resolution is orthogonal to the version behavior under test.
"""
import contextlib

import pytest
from keri.app import habbing
from keri.core import eventing as ke
from keri.kering import Vrsn_1_0, SerializeError
from keri.vdr import credentialing, verifying
from keri.vdr.credentialing import Registrar

_DATA = {"dt": "2026-07-08T00:00:00.000000+00:00", "score": 1}
_SCHEMA = "E" + "A" * 43


@contextlib.contextmanager
def _issuer_with_registry():
    with habbing.openHby(name="cred_v1_hold", temp=True, version=Vrsn_1_0) as hby:
        hab = hby.makeHab(name="issuer", transferable=True, version=Vrsn_1_0)
        rgy = credentialing.Regery(hby=hby, name=hby.name, temp=True)
        registry = rgy.makeRegistry(name="reg", prefix=hab.pre, noBackers=True)
        # anchor the registry inception in the issuer KEL
        rseal = ke.SealEvent(registry.regk, "0", registry.regd)
        hab.interact(data=[dict(i=rseal.i, s=rseal.s, d=rseal.d)])
        rgy.processEscrows()
        verifier = verifying.Verifier(hby=hby, reger=rgy.reger)
        registrar = Registrar(hby=hby, rgy=rgy, counselor=None)
        credentialer = credentialing.Credentialer(hby=hby, rgy=rgy, registrar=registrar,
                                                  verifier=verifier)
        credentialer.validate = lambda creder: True  # schema resolution is orthogonal
        yield hab, registry, credentialer


def test_registry_vcp_is_v1():
    with _issuer_with_registry() as (_hab, registry, _credentialer):
        assert registry.vcp.sad["v"].startswith("KERI10"), \
            f"registry vcp must be v1, got {registry.vcp.sad['v']}"


def test_credential_create_default_rejects_ri_on_v2():
    """Without the v1 pin the v2 SerderACDC rejects the hardcoded `ri` field."""
    with _issuer_with_registry() as (hab, _registry, credentialer):
        with pytest.raises(SerializeError):
            credentialer.create(regname="reg", recp=hab.pre, schema=_SCHEMA,
                                 source=None, rules=None, data=_DATA)


def test_credential_create_v1_pin_yields_v1_acdc_with_ri():
    with _issuer_with_registry() as (hab, registry, credentialer):
        creder = credentialer.create(regname="reg", recp=hab.pre, schema=_SCHEMA,
                                     source=None, rules=None, data=_DATA,
                                     version=Vrsn_1_0)
        assert creder.sad["v"].startswith("ACDC10"), \
            f"credential must be v1 ACDC, got {creder.sad['v']}"
        assert "ri" in creder.sad, "v1 ACDC must carry the `ri` registry field"
        assert creder.sad["ri"] == registry.regk
