import itertools
import types
import pytest
from locksmith_publisher import publish


def _fake_hby_hab(counts):
    """counts: iterable of wig-counts returned on successive polls."""
    seq = iter(counts)
    class _Wigs:
        def get(self, *, keys):
            return ["w"] * next(seq)
    hby = types.SimpleNamespace(db=types.SimpleNamespace(wigs=_Wigs()))
    hab = types.SimpleNamespace(
        pre="Epre",
        kever=types.SimpleNamespace(
            sn=1,
            serder=types.SimpleNamespace(said="Esaid"),
        ),
    )
    return hby, hab


def test_wait_returns_once_toad_met(monkeypatch):
    monkeypatch.setattr(publish.time, "sleep", lambda *a, **k: None)
    hby, hab = _fake_hby_hab([1, 2, 3])           # third poll meets toad=3
    calls = []
    n = publish._wait_for_receipts(hby, hab, toad=3, timeout_s=5.0,
                                   recollect=lambda: calls.append(1))
    assert n >= 3
    assert len(calls) >= 1                          # re-collected while short


def test_wait_raises_on_timeout(monkeypatch):
    monkeypatch.setattr(publish.time, "sleep", lambda *a, **k: None)
    # Use itertools.repeat so the iterator never exhausts regardless of loop count
    hby, hab = _fake_hby_hab(itertools.repeat(1))    # never reaches toad=3
    with pytest.raises(TimeoutError):
        publish._wait_for_receipts(hby, hab, toad=3, timeout_s=0.3,
                                   recollect=lambda: None)
