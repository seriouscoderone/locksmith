"""Tests that InceptDoer drives vault.receiptor (not the deprecated vault.witDoer).

Regression test for issue #77. The legacy ``agenting.WitnessReceiptor`` over HTTP
silently drops witness receipts because its underlying ``HTTPMessenger`` has no
Parser wired. Locksmith must drive ``vault.receiptor`` (a ``Receiptor`` subclass
that parses inline) instead.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from hio.base import doing
from hio.help import decking


class _ReceiptorStub:
    """Stands in for vault.receiptor. Captures appended messages and lets
    the test simulate completion by pushing a cue."""

    def __init__(self):
        self.msgs = decking.Deck()
        self.cues = decking.Deck()
        self.observed = []

    def drain(self):
        """Simulate one receiptor cycle: pop the queued msg, push a completion cue."""
        if self.msgs:
            msg = self.msgs.popleft()
            self.observed.append(msg)
            self.cues.push({"pre": msg["pre"]})


class _WitDoerSentinel:
    """Stands in for the legacy ``vault.witDoer``. Any access fails the test —
    InceptDoer must not touch it after the migration to ``vault.receiptor``."""

    @property
    def msgs(self):
        raise AssertionError(
            "InceptDoer must not append to vault.witDoer.msgs; use "
            "vault.receiptor instead (see issue #77)."
        )

    @property
    def cues(self):
        raise AssertionError(
            "InceptDoer must not poll vault.witDoer.cues; use "
            "vault.receiptor.cues instead (see issue #77)."
        )


def _drive(gen, ticks):
    """Send None into a generator up to ``ticks`` times. Return early on StopIteration."""
    for _ in range(ticks):
        try:
            gen.send(None)
        except StopIteration:
            return


def test_incept_do_appends_msg_to_receiptor_with_correct_shape(monkeypatch):
    """When the inception has witnesses, InceptDoer must enqueue
    ``dict(pre=..., sn=...)`` on vault.receiptor.msgs and wait on
    vault.receiptor.cues — never touching vault.witDoer."""
    # Patch the Anchorer that InceptDoer instantiates in __init__ — we don't
    # exercise delegation here and don't want real delegation machinery.
    from locksmith.core import habbing

    class _AnchorerStub(doing.DoDoer):
        def __init__(self, *_a, **_kw):
            super().__init__(doers=[])

    monkeypatch.setattr(habbing.delegating, "Anchorer", _AnchorerStub)

    # Hab stub with the fields InceptDoer touches in the wits branch
    kever = SimpleNamespace(
        delpre="",                                            # no delegation
        wits=["BNbRfMPQQge6wKO0uof9Y0e_QYOfiF08k9drc6pOgzjt"],
        sner=SimpleNamespace(num=0),
        sn=0,
        prefixer=SimpleNamespace(),
    )
    hab = SimpleNamespace(
        pre="EFakeFakeFakeFakeFakeFakeFakeFakeFakeFakeFak",
        kever=kever,
    )

    receiptor = _ReceiptorStub()
    hby = SimpleNamespace(makeHab=lambda *_a, **_kw: hab)
    vault = SimpleNamespace(
        hby=hby,
        postman=SimpleNamespace(),
        receiptor=receiptor,
        witDoer=_WitDoerSentinel(),
        remove=lambda *_a, **_kw: None,   # InceptDoer cleanup calls vault.remove
    )
    app = SimpleNamespace(vault=vault)

    incepter = habbing.InceptDoer(app=app, alias="test", signal_bridge=None)

    # Drive incept_do as a bare generator. First .send pumps past the
    # initial `_ = (yield self.tock)` line.
    gen = incepter.incept_do(tymth=lambda: 0.0, tock=0.0)
    next(gen)               # advance past first yield

    # Continue: next tick should run makeHab + the wits branch + first wait yield
    _drive(gen, ticks=3)
    assert receiptor.msgs, (
        "InceptDoer didn't append to vault.receiptor.msgs within 3 ticks — "
        "regression to vault.witDoer (issue #77)?"
    )

    # Verify the message shape that Receiptor.witDo expects
    msg = receiptor.msgs[0]
    assert msg["pre"] == hab.pre
    assert "sn" in msg, "Receiptor.witDo expects sn in msg (see keripy agenting.py)"

    # Push a completion cue so the busy-wait loop can exit; drive again
    receiptor.drain()
    _drive(gen, ticks=10)

    # No assertion on outcome beyond not exploding — the key invariant is
    # already covered: receiptor saw the msg, witDoer was never touched
    # (else _WitDoerSentinel would have failed the test mid-drive).
    assert receiptor.observed[0]["pre"] == hab.pre
