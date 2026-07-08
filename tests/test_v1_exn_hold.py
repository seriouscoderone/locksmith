"""KERI v2 v1-hold (Task 5): Locksmith's outbound exns are emitted v1.

Two mechanisms, verified here:

  * The hab-based IPEX builders (``ipexGrantExn``/``ipexAdmitExn``/``ipexApplyExn``)
    INHERIT the hab's version, so with Locksmith's v1 habs they emit v1 with no
    explicit pin.
  * ``exchange()`` used for the challenge-response exn takes ``sender=<pre>`` (not
    the hab), so it does NOT inherit — it defaults to v2 CESR-native on the v2
    keripy base and must be pinned v1 (remoting.py). This test drives the real
    ``ChallengeVerificationDoer`` and asserts the emitted exn is v1.
"""
from types import SimpleNamespace

from hio.base import doing
from keri.app import habbing
from keri.kering import Vrsn_1_0
from keri.vc import protocoling

from locksmith.core import remoting


def test_hab_based_ipex_exn_inherits_v1():
    """ipex builders follow the hab; a v1 hab yields a v1 exn without a pin."""
    with habbing.openHby(name="ipexv1", temp=True, version=Vrsn_1_0) as hby:
        hab = hby.makeHab(name="me", transferable=True, version=Vrsn_1_0)
        exn, _atc = protocoling.ipexApplyExn(hab=hab, recp=hab.pre, message="",
                                             schema="E" + "A" * 43, attrs={})
        assert exn.sad["v"].startswith("KERI10"), \
            f"hab-based ipex exn must inherit v1, got {exn.sad['v']}"


def test_challenge_response_exn_is_v1(monkeypatch):
    """The real ChallengeVerificationDoer emits a v1 challenge-response exn."""
    captured = {}

    class FakePoster:
        def __init__(self, **kwa):
            pass

        def send(self, serder=None, attachment=None):
            captured["serder"] = serder

        def deliver(self):
            return []

    monkeypatch.setattr(remoting, "StreamPoster", FakePoster)

    with habbing.openHby(name="chalv1", temp=True, version=Vrsn_1_0) as hby:
        hab = hby.makeHab(name="me", transferable=True, version=Vrsn_1_0)
        app = SimpleNamespace(vault=SimpleNamespace(hby=hby))
        doer = remoting.ChallengeVerificationDoer(
            app=app, hab_pre=hab.pre, remote_id_pre=hab.pre,
            challenge_words=["one", "two"],
        )
        doing.Doist(limit=2.0, tock=0.03125, doers=[doer]).do(limit=2.0)

    exn = captured.get("serder")
    assert exn is not None, "challenge exn was never emitted"
    assert exn.sad["v"].startswith("KERI10"), \
        f"challenge-response exn must be v1, got {exn.sad['v']}"
