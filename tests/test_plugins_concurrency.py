"""Two PluginInstaller instances writing the index concurrently never corrupt it."""
from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest

from locksmith.plugins import storage
from locksmith.plugins.installer import PluginInstaller, SourceDescriptor


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "plugins"


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "_user_home", lambda: tmp_path)
    yield tmp_path


def _make_variant(tmp_path: Path, name: str) -> Path:
    """Clone the echo fixture under a new plugin_id."""
    dst = tmp_path / name
    shutil.copytree(FIXTURE_ROOT / "echo-app", dst)
    manifest = dst / "locksmith-plugin.toml"
    content = manifest.read_text(encoding="utf-8")
    content = content.replace('plugin_id = "echo_app"', f'plugin_id = "{name}"')
    manifest.write_text(content, encoding="utf-8")
    return dst


def test_two_concurrent_installs_both_appear(isolated_root, tmp_path):
    variant_a = _make_variant(tmp_path / "src", "echo_a")
    variant_b = _make_variant(tmp_path / "src", "echo_b")

    errors: list[Exception] = []

    def install(src: SourceDescriptor):
        try:
            PluginInstaller().install(src)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=install,
                         args=(SourceDescriptor(type="local", path=str(variant_a)),)),
        threading.Thread(target=install,
                         args=(SourceDescriptor(type="local", path=str(variant_b)),)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"installer raised: {errors}"
    idx = storage.read_index()
    pids = {p["plugin_id"] for p in idx["plugins"]}
    assert pids == {"echo_a", "echo_b"}
    # Index is well-formed JSON
    import json
    raw = storage.index_path().read_text(encoding="utf-8")
    json.loads(raw)
