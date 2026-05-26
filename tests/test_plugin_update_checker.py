"""Tests for PluginUpdateChecker (cache logic + ls-remote seam)."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from locksmith.plugins import storage
from locksmith.plugins.updates import PluginUpdateChecker


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return tmp_path


def _seed_index(plugins):
    storage.write_index({"format": 1, "plugins": plugins})


def test_check_all_marks_update_available_when_remote_sha_differs(home, monkeypatch):
    _seed_index([{
        "plugin_id": "ui_tester",
        "source": {"type": "github", "user_repo": "x/y", "ref": None},
        "commit": "AAA",
        "installed_at": "2026-05-25T00:00:00Z",
        "manifest_snapshot": {},
    }])
    monkeypatch.setattr(
        "locksmith.plugins.updates._ls_remote",
        lambda url, ref: "BBB",
    )
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    cache = checker.cache()
    entry = cache["plugins"]["ui_tester"]
    assert entry["installed_commit"] == "AAA"
    assert entry["latest_commit"] == "BBB"
    assert entry["update_available"] is True
    assert entry["last_error"] is None


def test_check_all_clears_update_available_when_remote_matches(home, monkeypatch):
    _seed_index([{
        "plugin_id": "ui_tester",
        "source": {"type": "github", "user_repo": "x/y", "ref": None},
        "commit": "AAA",
        "installed_at": "2026-05-25T00:00:00Z",
        "manifest_snapshot": {},
    }])
    monkeypatch.setattr(
        "locksmith.plugins.updates._ls_remote",
        lambda url, ref: "AAA",
    )
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    assert checker.cache()["plugins"]["ui_tester"]["update_available"] is False


def test_check_all_skips_local_path_plugins(home, monkeypatch):
    _seed_index([{
        "plugin_id": "echo_app",
        "source": {"type": "local", "path": "/tmp/echo"},
        "commit": "local:2026-05-25T00:00:00",
        "installed_at": "2026-05-25T00:00:00Z",
        "manifest_snapshot": {},
    }])
    called = []
    monkeypatch.setattr(
        "locksmith.plugins.updates._ls_remote",
        lambda url, ref: called.append((url, ref)) or "BBB",
    )
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    assert called == []
    assert "echo_app" not in checker.cache()["plugins"]


def test_check_all_records_last_error_on_subprocess_failure(home, monkeypatch):
    _seed_index([{
        "plugin_id": "ui_tester",
        "source": {"type": "github", "user_repo": "x/y", "ref": None},
        "commit": "AAA",
        "installed_at": "2026-05-25T00:00:00Z",
        "manifest_snapshot": {},
    }])

    def boom(url, ref):
        raise subprocess.CalledProcessError(128, "git ls-remote", stderr="repo not found")

    monkeypatch.setattr("locksmith.plugins.updates._ls_remote", boom)
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    entry = checker.cache()["plugins"]["ui_tester"]
    assert entry["last_error"] is not None
    assert "repo not found" in entry["last_error"] or "exit 128" in entry["last_error"]


def test_check_all_one_plugin_failure_does_not_block_others(home, monkeypatch):
    _seed_index([
        {
            "plugin_id": "broken",
            "source": {"type": "github", "user_repo": "x/broken", "ref": None},
            "commit": "AAA", "installed_at": "0", "manifest_snapshot": {},
        },
        {
            "plugin_id": "fine",
            "source": {"type": "github", "user_repo": "x/fine", "ref": None},
            "commit": "AAA", "installed_at": "0", "manifest_snapshot": {},
        },
    ])

    def selective(url, ref):
        if "broken" in url:
            raise subprocess.CalledProcessError(128, "git", stderr="boom")
        return "BBB"

    monkeypatch.setattr("locksmith.plugins.updates._ls_remote", selective)
    checker = PluginUpdateChecker(manager=None)
    checker.check_all_plugins()
    cache = checker.cache()
    assert cache["plugins"]["broken"]["last_error"] is not None
    assert cache["plugins"]["fine"]["update_available"] is True


def test_subscribe_returns_unsubscribe_function(home):
    checker = PluginUpdateChecker(manager=None)
    callback = MagicMock()
    unsubscribe = checker.subscribe(callback)
    checker._notify_subscribers()
    callback.assert_called_once()
    unsubscribe()
    checker._notify_subscribers()
    callback.assert_called_once()  # not called again after unsubscribe


def test_check_all_notifies_subscribers(home, monkeypatch):
    _seed_index([{
        "plugin_id": "ui_tester",
        "source": {"type": "github", "user_repo": "x/y", "ref": None},
        "commit": "AAA", "installed_at": "0", "manifest_snapshot": {},
    }])
    monkeypatch.setattr("locksmith.plugins.updates._ls_remote", lambda u, r: "BBB")
    checker = PluginUpdateChecker(manager=None)
    callback = MagicMock()
    checker.subscribe(callback)
    checker.check_all_plugins()
    callback.assert_called()


def test_ls_remote_returns_first_sha(monkeypatch):
    """Direct unit test for the seam: parses git ls-remote stdout correctly."""
    from locksmith.plugins import updates

    sample_stdout = "a3f9c1dabe7c0f5e8b7a2b9d0c4e1f2a3b4c5d6e\tHEAD\n"
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=sample_stdout, stderr=""),
    )
    assert updates._ls_remote("https://github.com/x/y.git", "HEAD").startswith("a3f9c1d")


def test_ls_remote_raises_on_nonzero_exit(monkeypatch):
    from locksmith.plugins import updates

    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=128, stdout="", stderr="not found"),
    )
    with pytest.raises(subprocess.CalledProcessError):
        updates._ls_remote("https://github.com/x/missing.git", "HEAD")


def _iso_minus_seconds(seconds: int) -> str:
    import datetime
    t = datetime.datetime.utcnow() - datetime.timedelta(seconds=seconds)
    return t.isoformat(timespec="seconds") + "Z"


def test_should_check_now_true_when_cache_missing(home):
    checker = PluginUpdateChecker(manager=None, interval_hours=6)
    assert checker.should_check_now() is True


def test_should_check_now_true_when_cache_stale(home):
    storage.write_update_cache({
        "format": 1, "interval_hours": 6,
        "checked_at": _iso_minus_seconds(7 * 3600),  # 7h ago, > 6h interval
        "plugins": {},
    })
    checker = PluginUpdateChecker(manager=None, interval_hours=6)
    assert checker.should_check_now() is True


def test_should_check_now_false_when_cache_fresh(home):
    storage.write_update_cache({
        "format": 1, "interval_hours": 6,
        "checked_at": _iso_minus_seconds(60),  # 1m ago, well within 6h
        "plugins": {},
    })
    checker = PluginUpdateChecker(manager=None, interval_hours=6)
    assert checker.should_check_now() is False


def test_should_check_now_true_when_checked_at_unparseable(home):
    storage.write_update_cache({
        "format": 1, "interval_hours": 6,
        "checked_at": "not-an-iso-timestamp",
        "plugins": {},
    })
    checker = PluginUpdateChecker(manager=None, interval_hours=6)
    assert checker.should_check_now() is True
