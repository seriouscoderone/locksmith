"""Tests for the BridgeAdapter."""
from __future__ import annotations

import json
import sys

import pytest

from locksmith.update.bridge_adapter import (
    BridgeAdapter,
    DEFAULT_APPCAST_BASE,
    current_platform,
    default_appcast_url,
)


# ---- platform discovery + URL defaults -----------------------------------


def test_current_platform_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert current_platform() == "macos"


def test_current_platform_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert current_platform() == "windows"


def test_default_appcast_url_per_platform():
    assert default_appcast_url("macos") == f"{DEFAULT_APPCAST_BASE}/macos.json"
    assert default_appcast_url("windows") == f"{DEFAULT_APPCAST_BASE}/windows.json"


# ---- fetch + parse round-trip --------------------------------------------


def _release_dict(platform: str, ext: str, sha256: str, size: int) -> dict:
    return {
        "version": "0.0.16",
        "released_at": "2026-06-08T21:21:54Z",
        "platform": platform,
        "minimum_system_version": "13.0" if platform == "macos" else "10.0.19041",
        "artifact_url": f"https://releases.keri.host/releases/0.0.16/Locksmith-0.0.16.{ext}",
        "artifact_sha256": sha256,
        "artifact_size": size,
        "anchor_url": "https://releases.keri.host/releases/0.0.16/release-anchor-0.0.16.cesr",
        "anchor_said": "EKrzgtcKxXw3dsmn4UfYiBGgfu9BWTDjiRh9IkZZovUZ",
        "release_notes_url": "https://releases.keri.host/release-notes/0.0.16.html",
        "is_major": True,
        "is_critical": False,
    }


_VALID_APPCAST = json.dumps({
    "schema_version": 1,
    "channel": "stable",
    "publisher_aid": "ECnJ7jhAxjrduHkIKS_ml56bqPuIJIvSw-i0mpZR_P8p",
    "publisher_kel_url": "https://releases.keri.host/publisher/v1/kel.cesr",
    "current_version": "0.0.16",
    "releases": [
        _release_dict("macos", "dmg",
                      "8e83fa84e7c4a81ce2de210002799a7a3258a370c1f79f064eb73cb4e75d94dd",
                      60983347),
        _release_dict("windows", "msi",
                      "64377016347f4a45ef7fc4b816112243f198cb779b43c62d216b9eca27677044",
                      64688128),
    ],
}).encode()


def test_fetch_latest_release_returns_macos_release():
    adapter = BridgeAdapter(
        appcast_url="https://example.test/macos.json",
        platform="macos",
        fetcher=lambda url: _VALID_APPCAST,
    )
    release = adapter.fetch_latest_release()
    assert release is not None
    assert release.version == "0.0.16"
    assert release.platform == "macos"


def test_fetch_latest_release_returns_windows_release():
    adapter = BridgeAdapter(
        appcast_url="https://example.test/windows.json",
        platform="windows",
        fetcher=lambda url: _VALID_APPCAST,
    )
    release = adapter.fetch_latest_release()
    assert release is not None
    assert release.platform == "windows"


# ---- failure modes return None, not exceptions ---------------------------


def test_fetch_failure_returns_none():
    def broken(url):
        raise OSError("network down")

    adapter = BridgeAdapter(
        appcast_url="https://example.test/macos.json",
        platform="macos",
        fetcher=broken,
    )
    assert adapter.fetch_latest_release() is None


def test_parse_failure_returns_none():
    adapter = BridgeAdapter(
        appcast_url="https://example.test/macos.json",
        platform="macos",
        fetcher=lambda url: b"not json {",
    )
    assert adapter.fetch_latest_release() is None


def test_unknown_platform_returns_none():
    """Linux isn't in the appcast — adapter logs and returns None."""
    adapter = BridgeAdapter(
        appcast_url="https://example.test/linux.json",
        platform="linux",
        fetcher=lambda url: _VALID_APPCAST,
    )
    assert adapter.fetch_latest_release() is None


# ---- defaults flow through cleanly ---------------------------------------


def test_defaults_inferred_from_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    adapter = BridgeAdapter(fetcher=lambda url: _VALID_APPCAST)
    assert adapter.platform == "macos"
    assert adapter.appcast_url == f"{DEFAULT_APPCAST_BASE}/macos.json"
