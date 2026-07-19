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
