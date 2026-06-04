import logging

from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord


def _make_record(aid="EAID_BOB", label="Bob"):
    return PeerRecord(
        aid=aid,
        label=label,
        endpoint_url="tcp://10.0.0.2:5621",
        paired_at=datetime.now(timezone.utc).isoformat(),
    )


def test_add_then_contains(baser):
    al = PeerAllowlist(baser)
    al.add(_make_record())
    assert al.contains("EAID_BOB")


def test_contains_missing_returns_false(baser):
    al = PeerAllowlist(baser)
    assert al.contains("EAID_NOT_PAIRED") is False


def test_list_returns_all(baser):
    al = PeerAllowlist(baser)
    al.add(_make_record(aid="EAID_BOB"))
    al.add(_make_record(aid="EAID_CARL", label="Carl"))
    aids = {r.aid for r in al.list()}
    assert aids == {"EAID_BOB", "EAID_CARL"}


def test_remove(baser):
    al = PeerAllowlist(baser)
    al.add(_make_record())
    al.remove("EAID_BOB")
    assert al.contains("EAID_BOB") is False


def test_remove_missing_is_idempotent(baser):
    al = PeerAllowlist(baser)
    # should not raise
    al.remove("EAID_DOES_NOT_EXIST")


def test_get(baser):
    al = PeerAllowlist(baser)
    al.add(_make_record(label="Bob"))
    rec = al.get("EAID_BOB")
    assert rec is not None
    assert rec.label == "Bob"


def test_persists_across_reopen(tmp_path):
    from locksmith.db.basing import LocksmithBaser

    # temp=False so the LMDB file survives close() and the second open
    # reads the same data. Cleanup happens at end via clear=True.
    db1 = LocksmithBaser(name="persist", headDirPath=str(tmp_path), reopen=True)
    PeerAllowlist(db1).add(_make_record())
    db1.close()

    db2 = LocksmithBaser(name="persist", headDirPath=str(tmp_path), reopen=True)
    try:
        assert PeerAllowlist(db2).contains("EAID_BOB")
    finally:
        db2.close(clear=True)


def test_add_logs_pair_success(baser, caplog):
    al = PeerAllowlist(baser)
    with caplog.at_level(logging.INFO, logger="locksmith.peer.allowlist"):
        al.add(_make_record())
    assert any("peer.pair.success" in r.message for r in caplog.records)
