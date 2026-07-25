"""The in-app verify gate must replay the ACTIVE BRAND's appcast feed.

Regression: ``_appcast_url`` resolved from ``deploy_config.json``, which is
shared across brands and whose ``appcast_urls`` point at locksmith's feed. A
non-locksmith brand therefore verified against locksmith's appcast, read a
``locksmith`` seal, failed the brand check in ``_assert_current_for_brand``, and
rejected EVERY update ("update could not be verified") — while Sparkle, which
reads the brand's own XML feed, happily offered the update. Sparkle and the gate
must read the same brand's feed.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from locksmith.core import branding
from locksmith.update import cli

REPO_ROOT = Path(__file__).resolve().parents[3]
BRANDS = REPO_ROOT / "brands"


def _brand_from_manifest(brand_id: str) -> branding.Brand:
    """Build the runtime Brand exactly as a packaged brand.json would."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "packaging"))
    import brandlib  # noqa: PLC0415 — repo-local build helper

    manifest = tomllib.loads(
        (BRANDS / brand_id / "brand.toml").read_text(encoding="utf-8"))
    return branding._from_dict(brandlib.runtime_brand_json(manifest))


@pytest.mark.parametrize("brand_id", ["locksmith", "usurance"])
def test_gate_uses_the_brands_own_json_feed(brand_id, monkeypatch):
    b = _brand_from_manifest(brand_id)
    monkeypatch.setattr(cli, "brand", lambda: b)

    manifest = tomllib.loads(
        (BRANDS / brand_id / "brand.toml").read_text(encoding="utf-8"))
    assert cli._appcast_url("macos") == manifest["urls"]["appcast_macos"]
    assert cli._appcast_url("windows") == manifest["urls"]["appcast_windows"]


def test_non_default_brand_does_not_verify_against_locksmiths_feed(monkeypatch):
    """The precise failure mode: usurance must NOT get locksmith's feed."""
    usurance = _brand_from_manifest("usurance")
    locksmith = _brand_from_manifest("locksmith")
    monkeypatch.setattr(cli, "brand", lambda: usurance)

    for platform in ("macos", "windows"):
        got = cli._appcast_url(platform)
        locksmith_feed = (locksmith.appcast_macos if platform == "macos"
                          else locksmith.appcast_windows)
        assert got != locksmith_feed
        assert "usurance" in got


def test_runtime_brand_json_carries_the_json_feeds():
    """brand.json must carry the JSON feeds, not just the XML ones — the gate
    reads JSON, Sparkle reads XML, and both must come from the brand."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "packaging"))
    import brandlib  # noqa: PLC0415

    for brand_id in ("locksmith", "usurance"):
        manifest = tomllib.loads(
            (BRANDS / brand_id / "brand.toml").read_text(encoding="utf-8"))
        doc = brandlib.runtime_brand_json(manifest)
        for key in ("appcast_macos", "appcast_windows",
                    "appcast_macos_xml", "appcast_windows_xml"):
            assert doc.get(key), f"{brand_id} brand.json missing {key}"
