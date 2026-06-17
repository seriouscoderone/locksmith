"""Deploy-config loader: example template + gitignored real config resolution.

Privacy rule (see project notes): no real federation/CDN domains are committed.
The repo ships ``deploy_config.example.json`` with ``example.com`` placeholders;
the real config is gitignored at ``src/locksmith/release/deploy_config.json`` and
may be overridden via the ``LOCKSMITH_DEPLOY_CONFIG`` env var (a file path).

Unlike the publisher trust anchor, the example config is an ACCEPTABLE dev/test
fallback: the ``example.com`` URLs are harmless and the actual verify gate stays
dark without a real publisher anchor.

These tests target ``locksmith.release.deploy.load_deploy_config`` (re-exported
from ``locksmith.release``).
"""
import json
from pathlib import Path

import pytest

from locksmith.release import deploy

REQUIRED_KEYS = {
    "releases_cdn_base",
    "s3_bucket",
    "publisher_kel_url",
    "appcast_urls",
    "witnesses",
}

REQUIRED_WITNESS_KEYS = {"alias", "host", "aid"}

# Resolve the committed example relative to the repo, not the installed package,
# so the test is independent of how the package is installed.
EXAMPLE_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "locksmith"
    / "release"
    / "deploy_config.example.json"
)

# Every host/URL in the committed example must live under this placeholder
# domain; we assert that positively rather than embedding the real federation
# domains as literals (which would themselves be a privacy leak in the repo).
PLACEHOLDER_DOMAIN = "example.com"


def test_example_deploy_config_exists_and_is_committed():
    assert EXAMPLE_PATH.exists(), f"missing committed template: {EXAMPLE_PATH}"


def test_example_deploy_config_has_all_required_keys():
    body = json.loads(EXAMPLE_PATH.read_text())
    assert REQUIRED_KEYS.issubset(set(body.keys()))
    assert isinstance(body["releases_cdn_base"], str) and body["releases_cdn_base"]
    assert isinstance(body["s3_bucket"], str) and body["s3_bucket"]
    assert isinstance(body["publisher_kel_url"], str) and body["publisher_kel_url"]
    assert set(body["appcast_urls"]) >= {"macos", "windows"}
    assert isinstance(body["witnesses"], list) and len(body["witnesses"]) >= 3
    for w in body["witnesses"]:
        assert REQUIRED_WITNESS_KEYS.issubset(set(w.keys())), w


def test_example_deploy_config_uses_only_placeholder_values():
    """Every host/URL in the committed template lives under example.com.

    Asserted positively (every domain-bearing value contains the placeholder
    domain) so the test itself never names the real federation domains.
    """
    body = json.loads(EXAMPLE_PATH.read_text())
    url_values = [
        body["releases_cdn_base"],
        body["s3_bucket"],
        body["publisher_kel_url"],
        *body["appcast_urls"].values(),
    ]
    for val in url_values:
        assert PLACEHOLDER_DOMAIN in val, f"non-placeholder value: {val!r}"
    for w in body["witnesses"]:
        assert PLACEHOLDER_DOMAIN in w["host"], (
            f"non-placeholder witness host: {w['host']!r}"
        )


def test_loader_prefers_env_var_config(tmp_path, monkeypatch):
    """``$LOCKSMITH_DEPLOY_CONFIG`` (file) wins over everything else."""
    injected = tmp_path / "injected_deploy.json"
    injected.write_text(
        json.dumps(
            {
                "releases_cdn_base": "https://releases.injected.example.com",
                "s3_bucket": "releases.injected.example.com",
                "publisher_kel_url":
                    "https://releases.injected.example.com/publisher/v1/kel.cesr",
                "appcast_urls": {
                    "macos":
                        "https://releases.injected.example.com/appcast/v1/macos.json",
                    "windows":
                        "https://releases.injected.example.com/appcast/v1/windows.json",
                },
                "witnesses": [
                    {"alias": "wan", "host": "witness.injected.example.com",
                     "aid": "Binjected1"},
                ],
            }
        )
    )
    monkeypatch.setenv("LOCKSMITH_DEPLOY_CONFIG", str(injected))

    cfg = deploy.load_deploy_config()
    assert cfg["s3_bucket"] == "releases.injected.example.com"
    assert cfg["witnesses"][0]["host"] == "witness.injected.example.com"


def test_loader_env_var_missing_file_raises(tmp_path, monkeypatch):
    """An env var pointing at a missing file is a misconfiguration → raise."""
    monkeypatch.setenv(
        "LOCKSMITH_DEPLOY_CONFIG", str(tmp_path / "does-not-exist.json")
    )
    with pytest.raises(FileNotFoundError) as exc:
        deploy.load_deploy_config()
    assert "LOCKSMITH_DEPLOY_CONFIG" in str(exc.value)


def test_loader_falls_back_to_packaged_then_example(monkeypatch):
    """With no env var and no packaged real config, the example is the fallback."""
    monkeypatch.delenv("LOCKSMITH_DEPLOY_CONFIG", raising=False)

    # Force the packaged real-config probe to miss so we exercise the example
    # fallback deterministically regardless of local state.
    monkeypatch.setattr(deploy, "_packaged_deploy_config_path", lambda: None)

    cfg = deploy.load_deploy_config()
    assert REQUIRED_KEYS.issubset(set(cfg.keys()))
    # Fallback must be the harmless example.
    assert "example.com" in cfg["s3_bucket"]


def test_loader_prefers_packaged_real_over_example(tmp_path, monkeypatch):
    """A packaged real ``deploy_config.json`` wins over the example template."""
    monkeypatch.delenv("LOCKSMITH_DEPLOY_CONFIG", raising=False)
    real = tmp_path / "deploy_config.json"
    real.write_text(
        json.dumps(
            {
                "releases_cdn_base": "https://releases.real.example.net",
                "s3_bucket": "releases.real.example.net",
                "publisher_kel_url":
                    "https://releases.real.example.net/publisher/v1/kel.cesr",
                "appcast_urls": {
                    "macos":
                        "https://releases.real.example.net/appcast/v1/macos.json",
                    "windows":
                        "https://releases.real.example.net/appcast/v1/windows.json",
                },
                "witnesses": [
                    {"alias": "wan", "host": "witness.real.example.net",
                     "aid": "Breal1"},
                ],
            }
        )
    )
    monkeypatch.setattr(deploy, "_packaged_deploy_config_path", lambda: real)

    cfg = deploy.load_deploy_config()
    assert cfg["s3_bucket"] == "releases.real.example.net"
