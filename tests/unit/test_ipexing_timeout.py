# -*- encoding: utf-8 -*-
"""Regression: the IPEX doer timeouts must be wall-clock based, not a
``timer += self.tock`` accumulator.

``AdmitDoer.admitDo`` / ``SendGrantDoer.sendGrantDo`` run via ``doing.doify``,
which enters the generator with ``tock == 0.0`` (the doify default, forwarded by
``DoDoer.enter``). The old timeout guards accumulated ``timer += self.tock`` and
compared ``timer > timeout`` — with ``tock == 0.0`` the accumulator never
advanced, the guard was unreachable, and on a real save/coordination failure the
doer spun forever instead of emitting ``admit_failed`` / ``send_failed``.
Surfaced 2026-07-18 when a DOI admit hung ~5.5 min in the two-app demo.

These drive the shared wait helper directly with a controllable clock, so the
timeout is proven reachable *with ``tock == 0.0``* — the exact condition the
doified doers run under.
"""
from locksmith.core import ipexing
from locksmith.core.ipexing import _wait_for


def _run(gen):
    """Exhaust a return-valued generator; return (return_value, yield_count)."""
    yields = 0
    try:
        while True:
            gen.send(None)
            yields += 1
    except StopIteration as exc:
        return exc.value, yields


def test_returns_true_without_yielding_when_predicate_already_true():
    result, yields = _run(_wait_for(lambda: True, timeout=10.0, clock=lambda: 0.0))
    assert result is True
    assert yields == 0


def test_returns_true_when_predicate_becomes_true_before_timeout():
    checks = {"n": 0}

    def predicate():
        checks["n"] += 1
        return checks["n"] >= 3  # truthy on the 3rd check

    result, yields = _run(_wait_for(predicate, timeout=10.0, clock=lambda: 0.0))
    assert result is True
    assert yields == 2  # yielded after checks 1 and 2, exited on check 3


def test_times_out_when_predicate_never_true_even_with_zero_tock():
    """The load-bearing regression. ``tock=0.0`` mimics the doified doer; the
    old ``timer += tock`` guard would never fire here and this would hang."""
    now = {"t": 0.0}

    def clock():
        now["t"] += 1.0
        return now["t"]

    result, yields = _run(_wait_for(lambda: False, timeout=3.0, tock=0.0, clock=clock))
    assert result is False
    assert yields >= 1  # it actually waited, then gave up — it did not hang


def test_timeout_is_wall_clock_independent_of_tock():
    """Elapsed is measured on the clock, not by summing yielded tocks: a huge
    tock does not shorten the wait, a zero tock does not lengthen it."""
    now = {"t": 0.0}

    def clock():
        now["t"] += 2.0
        return now["t"]

    # timeout 5.0, clock jumps 2.0 per read: start=2; checks at 4 (elapsed 2),
    # 6 (elapsed 4), 8 (elapsed 6 > 5) -> stops after yielding twice.
    result, yields = _run(_wait_for(lambda: False, timeout=5.0, tock=999.0, clock=clock))
    assert result is False
    assert yields == 2


def test_default_clock_is_resolved_at_call_time(monkeypatch):
    """The default clock must be looked up at call time (not captured as a
    def-time default), so the production wall-clock is ``time.monotonic`` yet
    remains monkeypatchable for driving doer timeouts deterministically in
    tests."""
    now = {"t": 0.0, "calls": 0}

    def fake_monotonic():
        now["calls"] += 1
        now["t"] += 1.0
        return now["t"]

    monkeypatch.setattr(ipexing.time, "monotonic", fake_monotonic)
    # no explicit clock -> must use the (patched) module-level time.monotonic
    result, yields = _run(_wait_for(lambda: False, timeout=3.0, tock=0.0))
    assert result is False
    # proves the patched clock was actually used (not a def-time-captured
    # reference to the real monotonic, which would leave calls == 0)
    assert now["calls"] >= 1


def test_admitdo_emits_admit_failed_on_save_timeout_instead_of_hanging(monkeypatch):
    """End-to-end regression for the 2026-07-18 demo hang.

    When the admitted credential never lands in the reger ``saved`` index,
    ``AdmitDoer.admitDo`` must emit ``admit_failed`` and terminate — the demo
    saw it spin ~5.5 min because the ``timer += self.tock`` guard (tock == 0.0
    under doify) was unreachable. Driven with a fast fake ``monotonic`` clock and
    a step cap so a re-introduced hang FAILS the test rather than hanging it.
    """
    import types

    from hio.base import tyming
    from keri.app import grouping
    from keri.app.notifying import Notifier
    from keri.core import serdering
    from keri.peer import exchanging
    from keri.vc import protocoling

    from locksmith.core.ipexing import AdmitDoer, Granter
    from tests.unit.test_ipexing_admit import _issuer_with_saved_credential

    with _issuer_with_saved_credential() as (hby, hab, rgy, creder):
        # a genuine grant, persisted so admitDo's cloneMessage can find it
        grant_msg = Granter(hby=hby, hab=hab, rgy=rgy).grant(said=creder.said,
                                                             recp=hab.pre)
        grant_said = serdering.SerderKERI(raw=bytes(grant_msg)).said

        # an exchanger with handlers loaded, mirroring the vault's exc
        notifier = Notifier(hby)
        mux = grouping.Multiplexor(hby, notifier=notifier)
        exc = exchanging.Exchanger(hby=hby, handlers=[])
        grouping.loadHandlers(exc, mux)
        protocoling.loadHandlers(hby, exc=exc, notifier=notifier)

        vault = types.SimpleNamespace(hby=hby, exc=exc, db=hby.db)
        app = types.SimpleNamespace(vault=vault, rgy=rgy)

        events = []
        bridge = types.SimpleNamespace(
            emit_doer_event=lambda **kw: events.append(kw))

        doer = AdmitDoer(app=app, hab_pre=hab.pre, grant_said=grant_said,
                         signal_bridge=bridge)

        # force the save-wait to never observe the credential -> timeout branch
        monkeypatch.setattr(rgy.reger.saved, "get", lambda *a, **k: None)
        # fast wall-clock so the 10s timeout fires in a couple of steps
        clk = {"t": 0.0}

        def fast_monotonic():
            clk["t"] += 100.0
            return clk["t"]

        monkeypatch.setattr(ipexing.time, "monotonic", fast_monotonic)

        gen = doer.admitDo(tymth=tyming.Tymist().tymen(), tock=0.0)

        terminated = False
        try:
            for _ in range(5000):  # cap: a hang regression fails here, not hangs
                gen.send(None)
        except StopIteration:
            terminated = True

        assert terminated, "admitDo did not terminate — the tock-accumulator hang regressed"
        failed = [e for e in events if e.get("event_type") == "admit_failed"]
        assert failed, f"expected an admit_failed event; got {[e.get('event_type') for e in events]}"
        assert failed[0]["data"]["error"] == "Timeout processing credential"
