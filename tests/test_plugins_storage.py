"""Tests for the plugin storage layer (paths + atomic JSON writes)."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from locksmith.plugins import storage


def test_plugin_root_uses_tmp_path(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    assert storage.plugin_root() == tmp_path / ".locksmith" / "plugins"


def test_index_path_under_plugin_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    assert storage.index_path() == tmp_path / ".locksmith" / "plugins" / "index.json"


def test_plugin_clone_dir_under_plugin_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    assert storage.plugin_clone_dir("dev_control") == (
        tmp_path / ".locksmith" / "plugins" / "dev_control"
    )


def test_read_index_when_missing_returns_default(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    assert storage.read_index() == {"format": 1, "plugins": []}


def test_write_index_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    payload = {
        "format": 1,
        "plugins": [{"plugin_id": "x", "source": {"type": "local", "path": "/p"}}],
    }
    storage.write_index(payload)
    assert storage.read_index() == payload


def test_write_index_is_atomic(tmp_path, monkeypatch):
    """Two threads racing to write the index produce a valid file, not corruption."""
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    storage.write_index({"format": 1, "plugins": []})

    def writer(name):
        for _ in range(50):
            storage.write_index(
                {"format": 1, "plugins": [{"plugin_id": name}]}
            )

    threads = [threading.Thread(target=writer, args=(n,)) for n in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = storage.read_index()
    assert final["format"] == 1
    assert isinstance(final["plugins"], list)
    assert final["plugins"][0]["plugin_id"] in ("a", "b", "c")


def test_read_index_with_malformed_json_returns_default_and_logs(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    storage.plugin_root().mkdir(parents=True, exist_ok=True)
    storage.index_path().write_text("{ not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        result = storage.read_index()
    assert result == {"format": 1, "plugins": []}


def test_read_enable_list_when_missing_returns_default(tmp_path):
    keri_base = tmp_path / "keri-base"
    assert storage.read_enable_list(keri_base) == {"format": 1, "excluded": []}


def test_write_then_read_enable_list(tmp_path):
    keri_base = tmp_path / "keri-base"
    storage.write_enable_list(keri_base, {"format": 1, "excluded": ["dev_control"]})
    assert storage.read_enable_list(keri_base)["excluded"] == ["dev_control"]
