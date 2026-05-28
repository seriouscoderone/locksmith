import pytest

from locksmith.db.basing import LocksmithBaser


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
