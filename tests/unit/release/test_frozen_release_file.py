"""``frozen_release_file`` — resolve bundled ``locksmith/release/*`` data files
from the filesystem in a PyInstaller frozen app.

Regression: in a frozen .app the ``locksmith`` package code lives in the
embedded PYZ, so ``importlib.resources.files("locksmith.release")`` could not
locate the bundled ``publisher_anchor.json`` / ``deploy_config.json`` even
though PyInstaller laid them down under ``sys._MEIPASS``. That left the in-app
KERI verify gate silently DARK in the shipped build. ``frozen_release_file``
resolves them from the filesystem instead.
"""
import sys
from pathlib import Path

from locksmith.release import deploy
from locksmith.update import cli as update_cli


def _seed_release_file(root: Path, name: str, body: str = "{}") -> Path:
    d = root / "locksmith" / "release"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body)
    return p


def test_returns_none_when_not_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    _seed_release_file(tmp_path, "publisher_anchor.json")
    # Not frozen: callers should use importlib.resources, not this helper.
    assert deploy.frozen_release_file("publisher_anchor.json") is None


def test_resolves_from_meipass_when_frozen(monkeypatch, tmp_path):
    seeded = _seed_release_file(tmp_path, "publisher_anchor.json", '{"a": 1}')
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    got = deploy.frozen_release_file("publisher_anchor.json")
    assert got == seeded
    assert got.is_file()


def test_returns_none_when_frozen_but_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    # Point the .app-relative roots somewhere empty too.
    monkeypatch.setattr(sys, "executable", str(tmp_path / "x" / "y" / "z"), raising=False)
    assert deploy.frozen_release_file("deploy_config.json") is None


def test_deploy_resource_path_prefers_frozen(monkeypatch, tmp_path):
    """``deploy._resource_path`` returns the frozen file before importlib."""
    seeded = _seed_release_file(tmp_path, "deploy_config.json", '{"x": 2}')
    monkeypatch.setattr(
        deploy, "frozen_release_file", lambda name: seeded if name == "deploy_config.json" else None
    )
    assert deploy._resource_path("deploy_config.json") == seeded


def test_packaged_anchor_prefers_frozen(monkeypatch, tmp_path):
    """``cli._packaged_publisher_anchor_path`` returns the frozen file first."""
    seeded = _seed_release_file(tmp_path, "publisher_anchor.json", '{"publisher_aid": "E1"}')
    monkeypatch.setattr(
        update_cli, "frozen_release_file",
        lambda name: seeded if name == "publisher_anchor.json" else None,
    )
    assert update_cli._packaged_publisher_anchor_path() == seeded
