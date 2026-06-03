import logging

import pytest

from locksmith.db.basing import LocksmithBaser


@pytest.fixture(autouse=True)
def _propagate_peer_loggers():
    """keri.help.ogler sets propagate=False on its loggers, which prevents
    caplog from seeing records. Re-enable propagation for the peer
    namespace so we can assert on log lines without forking the logger
    setup. Restore afterwards.
    """
    affected = []
    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith("locksmith.peer"):
            lg = logging.getLogger(name)
            if not lg.propagate:
                affected.append(lg)
                lg.propagate = True
    yield
    for lg in affected:
        lg.propagate = False


@pytest.fixture
def baser(tmp_path):
    db = LocksmithBaser(
        name="peertest",
        headDirPath=str(tmp_path),
        reopen=True,
        temp=True,
    )
    try:
        yield db
    finally:
        db.close(clear=True)
