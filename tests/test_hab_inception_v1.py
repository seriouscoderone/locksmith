"""KERI v2 v1-hold (Task 2): every Locksmith-created hab must incept a v1 (KERI10)
inception while the transitional event-hold is in force.

`hby.makeHab` does NOT inherit `hby.version` (on the v2 keripy base it defaults to
v2 / `KERICAACAAJSON`), so each identifier-creation seam pins `version=Vrsn_1_0`
explicitly. This lifts as a unit with serviceaid when upstream ships v2
registry+IPEX (grep `TRANSITIONAL`).
"""
from types import SimpleNamespace

from keri import kering
from keri.app import habbing as keri_habbing

from locksmith.core import habbing


def _fake_incept_doer(captured):
    class FakeInceptDoer:
        def __init__(self, app, alias, proxy=None, signal_bridge=None, **kwargs):
            captured["kwargs"] = kwargs

    return FakeInceptDoer


def _min_app():
    return SimpleNamespace(
        vault=SimpleNamespace(
            signals=object(),
            hby=SimpleNamespace(habByName=lambda *a, **k: None),
            extend=lambda doers: None,
        )
    )


def test_create_identifier_threads_v1_version(monkeypatch):
    """The primary wallet inception path threads version=Vrsn_1_0 into makeHab."""
    captured = {}
    monkeypatch.setattr(habbing, "InceptDoer", _fake_incept_doer(captured))

    result = habbing.create_identifier(
        _min_app(), "probe", key_type="salty", salt="a" * 21, delegation_type="none"
    )

    assert result["success"] is True
    assert captured["kwargs"].get("version") == kering.Vrsn_1_0


def test_threaded_kwargs_emit_v1_icp(monkeypatch):
    """End-to-end: the exact creation_kwargs Locksmith builds, fed to a real Habery
    makeHab, emit a v1 (KERI10) icp — not the v2 default."""
    captured = {}
    monkeypatch.setattr(habbing, "InceptDoer", _fake_incept_doer(captured))

    habbing.create_identifier(
        _min_app(), "probe", key_type="salty", salt="a" * 21, delegation_type="none"
    )

    with keri_habbing.openHby(name="v1-icp-e2e", temp=True) as hby:
        hab = hby.makeHab(name="probe", **captured["kwargs"])
        vstring = hab.kever.serder.sad["v"]
        assert vstring.startswith("KERI10"), f"expected v1 icp, got {vstring}"
