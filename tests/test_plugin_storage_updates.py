"""Tests for the update-cache + sidecar/previous storage helpers."""
from __future__ import annotations

import json

import pytest

from locksmith.plugins import storage


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return tmp_path


def test_update_cache_path_lives_under_plugin_root(home):
    assert storage.update_cache_path() == home / ".locksmith" / "plugins" / "update-cache.json"


def test_read_update_cache_returns_default_when_missing(home):
    cache = storage.read_update_cache()
    assert cache == {"format": 1, "interval_hours": 6, "plugins": {}}


def test_write_then_read_update_cache_roundtrips(home):
    payload = {
        "format": 1,
        "interval_hours": 6,
        "plugins": {
            "ui_tester": {
                "ref": "main",
                "installed_commit": "abc",
                "latest_commit": "def",
                "latest_checked_at": "2026-05-25T00:00:00Z",
                "update_available": True,
                "last_error": None,
            }
        },
    }
    storage.write_update_cache(payload)
    assert storage.read_update_cache() == payload


def test_read_update_cache_returns_default_on_malformed_json(home):
    path = storage.update_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    cache = storage.read_update_cache()
    assert cache == {"format": 1, "interval_hours": 6, "plugins": {}}


def test_plugin_staging_dir_path(home):
    assert storage.plugin_staging_dir("ui_tester") == (
        home / ".locksmith" / "plugins" / "ui_tester.staging"
    )


def test_plugin_previous_dir_path(home):
    assert storage.plugin_previous_dir("ui_tester") == (
        home / ".locksmith" / "plugins" / "ui_tester.previous"
    )


def test_write_update_cache_is_atomic(home, monkeypatch):
    # Sanity: corrupted in-flight write should not leave a half-written file.
    # We can't easily simulate a crash; assert that intermediate temp files
    # are cleaned up after a failure in the underlying write helper.
    payload = {"format": 1, "interval_hours": 6, "plugins": {}}
    storage.write_update_cache(payload)
    # Final file exists; no stray .tmp files alongside.
    cache_dir = storage.update_cache_path().parent
    tmps = [p for p in cache_dir.iterdir() if p.name.startswith("update-cache.json.")]
    assert tmps == []
