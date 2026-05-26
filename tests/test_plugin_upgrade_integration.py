"""End-to-end test: install → bump remote → check_now → row shows update →
click Upgrade → banner appears → index.json reflects new commit.

Uses a local bare-repo as the github remote. The fake URL passed into the
installer is monkeypatched at the storage layer (via the source's user_repo)
to point at file:// instead of github.com.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from locksmith.plugins import storage
from locksmith.plugins.installer import PluginInstaller, SourceDescriptor
from locksmith.plugins.updates import PluginUpdateChecker


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def fake_remote(tmp_path):
    """Build a bare git repo on disk that's reachable via file:// URL.
    Commit content from fixtures/plugins/echo-app at HEAD."""
    work = tmp_path / "work"
    shutil.copytree(FIXTURE_ROOT / "echo-app", work)
    subprocess.check_call(["git", "init", "-q", str(work)])
    subprocess.check_call(["git", "-C", str(work), "add", "."])
    subprocess.check_call(
        ["git", "-C", str(work), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "v1"],
    )
    bare = tmp_path / "remote.git"
    subprocess.check_call(["git", "clone", "-q", "--bare", str(work), str(bare)])
    # Discover the default branch name so we can push to the right ref later.
    result = subprocess.run(
        ["git", "-C", str(work), "symbolic-ref", "HEAD"],
        capture_output=True, text=True,
    )
    default_branch = result.stdout.strip().replace("refs/heads/", "") or "main"
    return work, bare, default_branch


def test_full_cycle_install_check_upgrade(home, fake_remote, monkeypatch):
    work, bare, default_branch = fake_remote

    fake_url = f"file://{bare}"

    _real_run = subprocess.run  # capture before monkeypatching to avoid recursion

    def fake_fetch_run(cmd, **kw):
        if cmd[:2] == ["git", "clone"]:
            cmd = [arg if not arg.startswith("https://github.com/") else fake_url for arg in cmd]
        return _real_run(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", fake_fetch_run)

    # 1) Install echo_app from the fake github source
    installer = PluginInstaller()
    installer.install(SourceDescriptor(type="github", user_repo="acme/echo", ref=None))
    idx = storage.read_index()
    rec = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    sha_v1 = rec["commit"]

    # 2) Bump the bare remote with a new commit
    (work / "BUMP").write_text("v2", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(work), "add", "BUMP"])
    subprocess.check_call(
        ["git", "-C", str(work), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "v2"],
    )
    subprocess.check_call(
        ["git", "-C", str(work), "push", "-q", str(bare), f"HEAD:{default_branch}"],
    )

    # 3) Drive ls-remote at the fake URL
    def fake_ls_remote(url, ref):
        if url.startswith("https://github.com/"):
            url = fake_url
        # Resolve HEAD or branch ref against the bare repo
        resolve_ref = "HEAD" if ref == "HEAD" else ref
        result = subprocess.run(
            ["git", "ls-remote", url, resolve_ref],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.splitlines()[0].split("\t")[0].strip()

    monkeypatch.setattr("locksmith.plugins.updates._ls_remote", fake_ls_remote)

    # 4) check_now → cache reflects update available
    checker = PluginUpdateChecker(manager=None)
    checker.check_now()
    entry = checker.cache()["plugins"]["echo_app"]
    assert entry["update_available"] is True
    assert entry["latest_commit"] != sha_v1

    # 5) Upgrade
    installer.upgrade("echo_app")
    idx = storage.read_index()
    rec2 = [p for p in idx["plugins"] if p["plugin_id"] == "echo_app"][0]
    assert rec2["commit"] != sha_v1
    assert rec2["previous_commit"] == sha_v1

    # 6) Cache reflects "all caught up"
    entry2 = storage.read_update_cache()["plugins"]["echo_app"]
    assert entry2["update_available"] is False
    assert entry2["installed_commit"] == rec2["commit"]

    # 7) .previous breadcrumb exists
    assert storage.plugin_previous_dir("echo_app").exists()
