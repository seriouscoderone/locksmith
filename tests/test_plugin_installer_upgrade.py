"""Tests for PluginInstaller.upgrade() — sidecar clone + atomic swap."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from locksmith.plugins import storage
from locksmith.plugins.installer import (
    InstallError,
    PluginInstaller,
    SourceDescriptor,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


@pytest.fixture
def installer(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return PluginInstaller()


def _install_at(installer, monkeypatch, sha):
    """Install the echo-app fixture as a github plugin, faking the clone."""
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            dest = Path(cmd[-1])
            shutil.copytree(FIXTURE_ROOT / "echo-app", dest)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def fake_check_output(cmd, **kwargs):
        return (sha + "\n").encode()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    return installer.install(
        SourceDescriptor(type="github", user_repo="acme/echo", ref=None),
    )


def test_upgrade_swaps_clone_and_updates_index(installer, monkeypatch, tmp_path):
    _install_at(installer, monkeypatch, "AAA")
    def fake_run_v2(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            dest = Path(cmd[-1])
            shutil.copytree(FIXTURE_ROOT / "echo-app", dest)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run_v2)
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"BBB\n")

    new_record = installer.upgrade("echo_app")
    assert new_record["commit"] == "BBB"
    assert new_record["previous_commit"] == "AAA"
    assert storage.plugin_previous_dir("echo_app").exists()
    assert not storage.plugin_staging_dir("echo_app").exists()
    idx = storage.read_index()
    rec = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    assert rec["commit"] == "BBB"
    assert rec["previous_commit"] == "AAA"


def test_upgrade_clears_cache_update_available(installer, monkeypatch):
    _install_at(installer, monkeypatch, "AAA")
    storage.write_update_cache({
        "format": 1, "interval_hours": 6,
        "plugins": {
            "echo_app": {
                "ref": "HEAD", "installed_commit": "AAA", "latest_commit": "BBB",
                "latest_checked_at": "x", "update_available": True, "last_error": None,
            }
        },
    })
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"BBB\n")
    installer.upgrade("echo_app")
    entry = storage.read_update_cache()["plugins"]["echo_app"]
    assert entry["installed_commit"] == "BBB"
    assert entry["latest_commit"] == "BBB"
    assert entry["update_available"] is False
    assert entry["last_error"] is None


def test_upgrade_rejects_local_path_source(installer, monkeypatch):
    """Local-path plugins have no remote; upgrade should error explicitly."""
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app"))
    installer.install(src)
    with pytest.raises(InstallError) as exc:
        installer.upgrade("echo_app")
    assert "local" in str(exc.value).lower()


def test_upgrade_rejects_unknown_plugin(installer):
    with pytest.raises(InstallError) as exc:
        installer.upgrade("not-installed")
    assert "not installed" in str(exc.value).lower()


def test_upgrade_failure_leaves_clone_dir_intact(installer, monkeypatch):
    _install_at(installer, monkeypatch, "AAA")
    def failing_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="boom")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", failing_run)
    with pytest.raises(InstallError):
        installer.upgrade("echo_app")
    assert storage.plugin_clone_dir("echo_app").exists()
    idx = storage.read_index()
    rec = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    assert rec["commit"] == "AAA"
    assert not storage.plugin_staging_dir("echo_app").exists()


def test_upgrade_rejects_changed_plugin_id(installer, monkeypatch, tmp_path):
    _install_at(installer, monkeypatch, "AAA")

    different_id_src = tmp_path / "different-id-src"
    shutil.copytree(FIXTURE_ROOT / "echo-app", different_id_src)
    toml_path = different_id_src / "locksmith-plugin.toml"
    toml_path.write_text(
        toml_path.read_text().replace('plugin_id = "echo_app"', 'plugin_id = "other_id"'),
        encoding="utf-8",
    )

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            dest = Path(cmd[-1])
            shutil.copytree(different_id_src, dest)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"BBB\n")
    with pytest.raises(InstallError) as exc:
        installer.upgrade("echo_app")
    assert "plugin_id" in str(exc.value)
    assert not storage.plugin_staging_dir("echo_app").exists()
    idx = storage.read_index()
    rec = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    assert rec["commit"] == "AAA"


def test_upgrade_overwrites_existing_previous_dir(installer, monkeypatch, tmp_path):
    _install_at(installer, monkeypatch, "AAA")
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"BBB\n")
    installer.upgrade("echo_app")
    assert storage.plugin_previous_dir("echo_app").exists()
    (storage.plugin_previous_dir("echo_app") / "MARKER_FROM_FIRST_UPGRADE").write_text("x")

    monkeypatch.setattr(subprocess, "check_output", lambda cmd, **kw: b"CCC\n")
    installer.upgrade("echo_app")
    assert not (storage.plugin_previous_dir("echo_app") / "MARKER_FROM_FIRST_UPGRADE").exists()
