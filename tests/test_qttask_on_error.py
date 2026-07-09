"""QtTask must not silently leave a live-but-dead vault: on a doer exception it invokes
on_error (if set) instead of re-raising, so the host can tear down honestly."""
import pytest
from hio.base import doing
from PySide6.QtCore import QTimer

from locksmith.core.tasking import QtTask


def _boom_doer():
    def _boom(tymth=None, tock=0.0, **kwa):
        yield tock
        raise RuntimeError("boom")
    return doing.doify(_boom)


def test_on_error_called_and_not_reraised(qapp):
    doist = doing.Doist(doers=[_boom_doer()], tock=0.01, real=False)
    captured = {}
    qt = QtTask(doist, QTimer(), on_error=lambda e: captured.__setitem__("e", e))
    qt.run()  # recur -> doer raises -> except -> on_error, no re-raise
    assert isinstance(captured.get("e"), RuntimeError)


def test_reraises_without_on_error(qapp):
    doist = doing.Doist(doers=[_boom_doer()], tock=0.01, real=False)
    qt = QtTask(doist, QTimer())  # on_error defaults None -> preserve re-raise
    with pytest.raises(RuntimeError):
        qt.run()
