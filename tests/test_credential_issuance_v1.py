"""KERI v2 v1-hold (Task 6): credential issuance yields a v1 ACDC carrying the
v1 `ri` registry field.

Locksmith issues via the fork's additive ``Credentialer.create(version=Vrsn_1_0)``
seam, producing a valid v1 ``ACDC10JSON`` credential to match the registry
``vcp``/``iss``, which are still v1 (the VDR stack is v1-pinned upstream).

The pin's ORIGINAL justification was that v2 ACDC issuance was stubbed upstream:
``proving.credential`` hardcoded ``ri`` and the v2 ``SerderACDC`` rejected it
with ``SerializeError``. That is no longer the case — the current keri pin
issues a real v2 ACDC (``rd``) when unpinned, which
``test_unpinned_create_now_yields_a_v2_acdc`` characterizes. The v1 hold remains
because a v2 ACDC in a v1 registry is incoherent, not because v2 issuance is
broken. See
``backlog/2026-08-10-v2-acdc-issuance-is-live-revisit-the-v1-hold.md``.

This exercises the real keripy ``Credentialer.create`` (the seam Locksmith calls
at credentialing.py) with a real registry; ``validate`` is stubbed because schema
resolution is orthogonal to the version behavior under test.
"""
import contextlib

from keri.app import habbing
from keri.core import eventing as ke
from keri.kering import Vrsn_1_0
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


def test_unpinned_create_now_yields_a_v2_acdc():
    """Without the v1 pin, issuance produces a v2 ACDC with `rd`, not `ri`.

    This is what makes the pin load-bearing rather than a workaround: the
    unpinned default is a perfectly valid credential that simply does not match
    the v1 registry it would be issued into. It used to raise ``SerializeError``
    instead; if this ever starts raising again, the keri pin has moved backwards.
    """
    with _issuer_with_registry() as (hab, _registry, credentialer):
        creder = credentialer.create(regname="reg", recp=hab.pre, schema=_SCHEMA,
                                     source=None, rules=None, data=_DATA)
        assert not creder.sad["v"].startswith("ACDC10"), \
            f"unpinned create produced a v1 ACDC ({creder.sad['v']}) — the pin " \
            "is now redundant and the v1 hold should be re-examined"
        assert "rd" in creder.sad and "ri" not in creder.sad, \
            f"expected a v2 registry field `rd`, got keys {sorted(creder.sad)}"


def test_credential_create_v1_pin_yields_v1_acdc_with_ri():
    with _issuer_with_registry() as (hab, registry, credentialer):
        creder = credentialer.create(regname="reg", recp=hab.pre, schema=_SCHEMA,
                                     source=None, rules=None, data=_DATA,
                                     version=Vrsn_1_0)
        assert creder.sad["v"].startswith("ACDC10"), \
            f"credential must be v1 ACDC, got {creder.sad['v']}"
        assert "ri" in creder.sad, "v1 ACDC must carry the `ri` registry field"
        assert creder.sad["ri"] == registry.regk
