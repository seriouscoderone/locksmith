"""KERI v2 v1-hold (Task 7): vault DB migrate-on-open, backed up first.

Old released Locksmith builds bundled ``keri==1.3.4``. A v2-based build opening a
user's 1.3.4-schema vault hits keripy's schema guard and bricks. ``ensure_migrated``
must detect the stale schema, back it up, run keripy's migrations, and leave the
vault openable with its AIDs intact — or restore the backup and re-raise on failure.

Fixture: ``tests/fixtures/keri_v1_3_4_vault.tar.gz`` — a GENUINE vault created by
``keri==1.3.4`` (DB version 1.3.4) holding two AIDs (``alice`` transferable, ``bob``
non-transferable). Not synthesizable on the v2 base, so captured from a 1.3.4 venv.

The tests pin keripy's default head dir (``LMDBer.HeadDirPath``) to a temp dir so the
Baser resolves the fixture consistently — keripy's ``reopen()`` checks ``exists()``
against the *class* head (ignoring any instance ``headDirPath``), so a headDirPath
shortcut would falsely auto-stamp and hide the brick. This mirrors the real vault
location (the default head) faithfully and stays hermetic.
"""
import tarfile
from pathlib import Path

import pytest
from keri.db import basing, dbing
from keri.kering import DatabaseError

from locksmith.core import migrating

_FIXTURE = Path(__file__).parent / "fixtures" / "keri_v1_3_4_vault.tar.gz"
_NAME = "v1fixture"
_ALICE = "EFQ2Qt_okgVSxVzzzFzFVhvz3pFmxLMehiyxyqJmTUBU"
_BOB = "BFqMOJ_Fsan_1E786Ep1jq8RCzN6bXfpm7WQteOpIROM"


@pytest.fixture
def v1_head(tmp_path, monkeypatch):
    """Extract the 1.3.4 fixture under a temp keri head and pin keripy to it."""
    head = tmp_path / "head"
    head.mkdir()
    with tarfile.open(_FIXTURE, "r:gz") as tar:
        tar.extractall(head)  # -> {head}/keri/db/v1fixture, {head}/keri/ks/v1fixture
    # keripy resolves paths as HeadDirPath + TailDirPath("keri/db") + name.
    monkeypatch.setattr(dbing.LMDBer, "HeadDirPath", str(head))
    monkeypatch.setattr(dbing.LMDBer, "AltHeadDirPath", str(head))
    monkeypatch.setattr(basing.Baser, "HeadDirPath", str(head))
    monkeypatch.setattr(basing.Baser, "AltHeadDirPath", str(head))
    return head


def _hab_keys(name):
    """Open the (post-migration) Baser and return the set of hab-record keys."""
    db = basing.Baser(name=name, base="", temp=False, reopen=False)
    db.reopen()  # must NOT raise once migrated
    try:
        return {k[0] for k, _ in db.habs.getTopItemIter()}, db.version
    finally:
        db.close()


def test_stale_1_3_4_vault_would_brick(v1_head):
    """A bare open of the un-migrated 1.3.4 vault raises the schema guard (the brick)."""
    db = basing.Baser(name=_NAME, base="", temp=False, reopen=False)
    with pytest.raises(DatabaseError, match="migrations must be run"):
        db.reopen()


def test_ensure_migrated_backs_up_and_migrates(v1_head):
    backup_root = v1_head.parent / "backups"

    backup = migrating.ensure_migrated(_NAME, "", backup_root=backup_root)

    assert backup is not None, "a stale vault must report a migration+backup"
    assert backup.exists(), "backup tarball must be written before migrating"
    # the backup captures the pre-migration vault (db + ks)
    with tarfile.open(backup, "r:gz") as tar:
        names = tar.getnames()
    assert any(f"db/{_NAME}" in n for n in names), "backup must include the KEL db"

    # the vault is now current and its AIDs survived
    keys, version = _hab_keys(_NAME)
    assert not version.startswith("1.3.4"), f"expected migrated version, got {version}"
    assert _ALICE in keys, "alice AID must survive migration"
    assert _BOB in keys, "bob AID must survive migration"


def test_ensure_migrated_is_noop_when_current(v1_head):
    # first call migrates; a second call sees a current vault and does nothing
    migrating.ensure_migrated(_NAME, "", backup_root=v1_head.parent / "b1")
    result = migrating.ensure_migrated(_NAME, "", backup_root=v1_head.parent / "b2")
    assert result is None, "an already-current vault must not be re-migrated"
