# -*- encoding: utf-8 -*-
"""Offscreen-safe, pure-filesystem tests for legacy-vault discovery/adoption.

Run: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
        tests/test_apping_environments.py -q --import-mode=importlib
"""
from pathlib import Path
from types import SimpleNamespace

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
