"""An alias somebody else already minted is not a failure for an idempotent caller.

`create_identifier` is ASYNCHRONOUS: it does `vault.extend([incept_doer])` and
returns before the hab exists. So the `habByName` pre-check its two idempotent
callers perform — `bootstrapping.py` and `hoa_shell`'s
`_ensure_default_identifier` — cannot see an incept the other one already has in
flight. Both pass their check, both schedule a doer, and the loser's `makeHab`
raises keripy's `ValueError("AID already exists with that name")`
(`keripy habbing.py:1178`), which the doer's blanket handler turns into an
ERROR-with-traceback plus an `identifier_creation_failed` event — for a vault that
ends up with exactly the identifier it wanted.

The two USER-initiated callers (`ui/vault/identifiers/create.py`,
`groups/create.py`) must keep failing loudly: neither validates alias uniqueness
before calling, so that failure event is the only thing that tells a user the name
is taken.
"""
from types import SimpleNamespace

import pytest

from locksmith.core import habbing


class _Signals:
    def __init__(self):
        self.events = []

    def emit_doer_event(self, doer_name, event_type, data):
        self.events.append((doer_name, event_type, data))


def _app(existing_alias=None, existing_pre="EEXISTINGpre"):
    """A vault whose habByName knows about exactly one alias, and whose makeHab
    raises keripy's real message for it — the two facts the doer branches on."""
    def hab_by_name(name):
        if existing_alias is not None and name == existing_alias:
            return SimpleNamespace(pre=existing_pre, name=name)
        return None

    def make_hab(name, **kwargs):
        if existing_alias is not None and name == existing_alias:
            raise ValueError("AID already exists with that name")
        return SimpleNamespace(pre="ENEWpre", name=name,
                               kever=SimpleNamespace(delpre=None, wits=[]))

    signals = _Signals()
    return SimpleNamespace(
        vault=SimpleNamespace(
            signals=signals,
            hby=SimpleNamespace(habByName=hab_by_name, makeHab=make_hab),
            postman=None,
            receiptor=None,
            extend=lambda doers: None,
            remove=lambda doers: None,
        )
    ), signals


def _drive(doer):
    """Run the doer's generator far enough to reach its makeHab decision."""
    gen = doer.incept_do(tymth=lambda: 0.0, tock=0.0)
    next(gen)                      # past the initial `yield self.tock`
    with pytest.raises(StopIteration):
        next(gen)


def test_if_absent_reports_an_existing_alias_as_created(monkeypatch):
    """The idempotent path: no traceback, and the SAME success event a fresh mint
    emits, so a listener cannot tell the two apart."""
    app, signals = _app(existing_alias="default")
    monkeypatch.setattr(habbing.delegating, "Anchorer", lambda **kw: SimpleNamespace())

    doer = habbing.InceptDoer(app=app, alias="default",
                              signal_bridge=signals, if_absent=True)
    _drive(doer)

    assert [e[1] for e in signals.events] == ["identifier_created"]
    assert signals.events[0][2] == {"alias": "default", "pre": "EEXISTINGpre",
                                    "success": True}


def test_without_if_absent_an_existing_alias_still_fails_loudly(monkeypatch):
    """The user-initiated path is unchanged — this is what tells someone the name
    is taken, since neither creation dialog validates uniqueness first."""
    app, signals = _app(existing_alias="default")
    monkeypatch.setattr(habbing.delegating, "Anchorer", lambda **kw: SimpleNamespace())

    doer = habbing.InceptDoer(app=app, alias="default",
                              signal_bridge=signals, if_absent=False)
    _drive(doer)

    assert [e[1] for e in signals.events] == ["identifier_creation_failed"]
    assert "already exists" in signals.events[0][2]["error"]


def test_if_absent_still_mints_when_the_alias_is_free(monkeypatch):
    """if_absent must not turn into "never mint" — a vault with no default AID is
    the case both callers exist to fix."""
    app, signals = _app(existing_alias=None)
    monkeypatch.setattr(habbing.delegating, "Anchorer", lambda **kw: SimpleNamespace())

    doer = habbing.InceptDoer(app=app, alias="default",
                              signal_bridge=signals, if_absent=True)
    _drive(doer)

    assert [e[1] for e in signals.events] == ["identifier_created"]
    assert signals.events[0][2]["pre"] == "ENEWpre"


@pytest.mark.parametrize("module,symbol", [
    ("locksmith.core.bootstrapping", "bootstrap_default_environment"),
    ("locksmith.plugins.hoa_shell.plugin", "HoaShellPlugin"),
])
def test_both_idempotent_call_sites_pass_if_absent(module, symbol):
    """Source-level: the flag is worthless if the callers do not set it, and a
    future third default-AID minter is the same defect again. Asserts the two known
    idempotent call sites pass it — and, more usefully, that no create_identifier
    call in either module omits it."""
    import ast
    import importlib

    path = importlib.import_module(module).__file__
    tree = ast.parse(open(path).read())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", getattr(n.func, "attr", None)) == "create_identifier"]
    assert calls, f"{module} no longer calls create_identifier — retarget this guard"
    for call in calls:
        kwnames = {kw.arg for kw in call.keywords}
        assert "if_absent" in kwnames, (
            f"{module}:{call.lineno} calls create_identifier without if_absent. "
            "Both minters of a vault's DEFAULT AID must pass it, or the loser of "
            "the in-flight race logs an ERROR traceback for a healthy vault."
        )
