# -*- encoding: utf-8 -*-
"""Offscreen-safe, pure-filesystem tests for legacy-vault discovery/adoption.

Run: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
        tests/test_apping_environments.py -q --import-mode=importlib
"""
from pathlib import Path
from types import SimpleNamespace

from keri.db.dbing import LMDBer

from locksmith.core import apping


def _mk(root: Path, store: str, name: str, base: str = "") -> Path:
    """Create root/store/base/name as a directory and return it."""
    d = root / store / base / name if base else root / store / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_environments_reads_rt_via_seam(tmp_path, monkeypatch):
    # A vault is "listed" iff it has an rt/ entry.
    _mk(tmp_path, "rt", "Alpha")
    _mk(tmp_path, "rt", "Beta")
    monkeypatch.setattr(apping, "_vault_head_dirs", lambda: [tmp_path])

    stub = SimpleNamespace(config=SimpleNamespace(base=""))
    names = apping.LocksmithApplication.environments(stub)

    assert names == ["Alpha", "Beta"]


def test_environments_empty_when_no_rt(tmp_path, monkeypatch):
    monkeypatch.setattr(apping, "_vault_head_dirs", lambda: [tmp_path])
    stub = SimpleNamespace(config=SimpleNamespace(base=""))
    assert apping.LocksmithApplication.environments(stub) == []


def _patch_head_roots(monkeypatch, tmp_path):
    """Point LMDBer's preferred/fallback head roots at tmp_path subdirs.

    Returns (preferred_root, fallback_root) — the full, un-created candidate
    paths _vault_head_dirs() would build from those heads, using
    LocksmithBaser's tail parents ("keri" / ".keri") the same way the real
    function does.
    """
    sys_head = tmp_path / "sys"
    home_head = tmp_path / "home"
    monkeypatch.setattr(LMDBer, "HeadDirPath", str(sys_head))
    monkeypatch.setattr(LMDBer, "AltHeadDirPath", str(home_head))

    preferred_child = Path(apping.LocksmithBaser.TailDirPath).parent
    fallback_child = Path(apping.LocksmithBaser.AltTailDirPath).parent
    return sys_head / preferred_child, home_head / fallback_child


def test_vault_head_dirs_both_exist_preferred_then_fallback(tmp_path, monkeypatch):
    preferred, fallback = _patch_head_roots(monkeypatch, tmp_path)
    preferred.mkdir(parents=True)
    fallback.mkdir(parents=True)

    assert apping._vault_head_dirs() == [preferred, fallback]


def test_vault_head_dirs_only_fallback_exists(tmp_path, monkeypatch):
    preferred, fallback = _patch_head_roots(monkeypatch, tmp_path)
    fallback.mkdir(parents=True)

    assert apping._vault_head_dirs() == [fallback]


def test_vault_head_dirs_neither_exists(tmp_path, monkeypatch):
    _patch_head_roots(monkeypatch, tmp_path)

    assert apping._vault_head_dirs() == []


def test_find_detects_legacy_vault(tmp_path):
    # db + ks + mbx, no rt -> legacy vault.
    for store in ("db", "ks", "mbx"):
        _mk(tmp_path, store, "Utah State")
    assert apping.find_legacy_vaults(heads=[tmp_path]) == ["Utah State"]


def test_find_ignores_kli_junk(tmp_path):
    # db + ks only (no mbx) -> kli/test debris, never a vault.
    for store in ("db", "ks"):
        _mk(tmp_path, store, "anchoring-1774913659009")
    assert apping.find_legacy_vaults(heads=[tmp_path]) == []


def test_find_ignores_mailbox_only_orphan(tmp_path):
    _mk(tmp_path, "mbx", "stray")
    assert apping.find_legacy_vaults(heads=[tmp_path]) == []


def test_find_skips_already_adopted(tmp_path):
    for store in ("db", "ks", "mbx", "rt"):
        _mk(tmp_path, store, "Carrier")
    assert apping.find_legacy_vaults(heads=[tmp_path]) == []


def test_find_honors_base(tmp_path):
    for store in ("db", "ks", "mbx"):
        _mk(tmp_path, store, "Scoped", base="myorg")
    # A bare-root vault must NOT match when base is set.
    for store in ("db", "ks", "mbx"):
        _mk(tmp_path, store, "Bare")
    assert apping.find_legacy_vaults(base="myorg", heads=[tmp_path]) == ["Scoped"]
