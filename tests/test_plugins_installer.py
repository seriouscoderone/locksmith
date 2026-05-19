"""Tests for the plugin installer (local + git sources, install, uninstall)."""
from __future__ import annotations

import json
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


def test_install_from_local_path_happy(installer, tmp_path):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app"))
    record = installer.install(src)
    assert record["plugin_id"] == "echo_app"
    assert record["source"]["type"] == "local"
    clone = storage.plugin_clone_dir("echo_app")
    assert (clone / "locksmith-plugin.toml").exists()
    assert (clone / "echo_app" / "plugin.py").exists()
    idx = storage.read_index()
    assert len(idx["plugins"]) == 1
    assert idx["plugins"][0]["plugin_id"] == "echo_app"
    snap = idx["plugins"][0]["manifest_snapshot"]
    assert snap["plugin_id"] == "echo_app"
    assert snap["entry_point"] == "echo_app.plugin:EchoAppPlugin"


def test_install_rejects_malformed_manifest(installer):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "malformed-toml"))
    with pytest.raises(InstallError) as exc:
        installer.install(src)
    assert "invalid toml" in str(exc.value).lower() or "parse" in str(exc.value).lower()
    assert storage.read_index()["plugins"] == []


def test_install_rejects_missing_required_fields(installer):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "missing-required-fields"))
    with pytest.raises(InstallError):
        installer.install(src)
    assert storage.read_index()["plugins"] == []


def test_install_rejects_local_path_without_manifest(installer, tmp_path):
    bad = tmp_path / "no-manifest"
    bad.mkdir()
    with pytest.raises(InstallError) as exc:
        installer.install(SourceDescriptor(type="local", path=str(bad)))
    assert "locksmith-plugin.toml" in str(exc.value)


def test_install_rejects_duplicate_plugin_id(installer):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app"))
    installer.install(src)
    with pytest.raises(InstallError) as exc:
        installer.install(src)
    assert "already installed" in str(exc.value).lower()


def test_uninstall_removes_clone_and_index_entry(installer):
    src = SourceDescriptor(type="local", path=str(FIXTURE_ROOT / "echo-app"))
    installer.install(src)
    installer.uninstall("echo_app")
    assert not storage.plugin_clone_dir("echo_app").exists()
    assert storage.read_index()["plugins"] == []


def test_uninstall_unknown_plugin_raises(installer):
    with pytest.raises(InstallError) as exc:
        installer.uninstall("nope")
    assert "not installed" in str(exc.value).lower()


def test_install_github_invokes_git_clone(installer, monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        dest = Path(cmd[-1])
        shutil.copytree(FIXTURE_ROOT / "echo-app", dest)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def fake_check_output(cmd, **kwargs):
        return b"a3f9c1dabe7c0f5e8b7a2b9d0c4e1f2a3b4c5d6e\n"

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    src = SourceDescriptor(type="github", user_repo="acme/echo", ref=None)
    record = installer.install(src)

    assert captured["cmd"][:3] == ["git", "clone", "--depth"]
    assert "https://github.com/acme/echo.git" in captured["cmd"]
    assert record["commit"].startswith("a3f9c1d")
    assert record["source"] == {"type": "github", "user_repo": "acme/echo", "ref": None}


def test_install_github_clone_failure_surfaces(installer, monkeypatch):
    def failing_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: repo not found")

    monkeypatch.setattr(subprocess, "run", failing_run)
    src = SourceDescriptor(type="github", user_repo="acme/missing", ref=None)
    with pytest.raises(InstallError) as exc:
        installer.install(src)
    assert "git clone" in str(exc.value).lower()
    assert "repo not found" in str(exc.value)
