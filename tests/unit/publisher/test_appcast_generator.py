"""Tests for the publisher-side appcast generator."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from locksmith_publisher.appcast import (
    GeneratorConfig,
    generate_and_upload_appcasts,
)


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "update"


def _real_anchors() -> dict[str, bytes]:
    """Pull the fixture-generated CESR anchor events for each version."""
    return {
        v: (FIXTURES / "anchor" / f"{v}.cesr").read_bytes()
        for v in ("1.0.0", "1.0.1", "1.1.0")
    }


def _build_s3_mock(anchors: dict[str, bytes]) -> MagicMock:
    s3 = MagicMock()
    s3.list_release_versions.return_value = sorted(anchors.keys())
    s3.get_object.side_effect = lambda Bucket, Key: anchors[Key.split("/")[1]]
    return s3


def test_generator_writes_per_platform_appcasts():
    anchors = _real_anchors()
    s3 = _build_s3_mock(anchors)
    captured: dict[str, bytes] = {}
    s3.put_object.side_effect = (
        lambda Bucket, Key, Body, **kw: captured.update({Key: Body})
    )
    cfg = GeneratorConfig(
        bucket="releases.example.com",
        publisher_aid="EAaa",
        publisher_kel_url="https://releases.example.com/publisher/v1/publisher-kel.cesr",
    )
    generate_and_upload_appcasts(s3=s3, config=cfg)

    assert "appcast/v1/macos.json" in captured
    assert "appcast/v1/windows.json" in captured
    # At least one archive entry per platform.
    assert any(k.startswith("appcast/archive/") for k in captured)


def test_generator_retains_full_history_no_pruning():
    anchors = _real_anchors()
    s3 = _build_s3_mock(anchors)
    captured: dict[str, bytes] = {}
    s3.put_object.side_effect = (
        lambda Bucket, Key, Body, **kw: captured.update({Key: Body})
    )
    cfg = GeneratorConfig(
        bucket="releases.example.com",
        publisher_aid="EAaa",
        publisher_kel_url="https://releases.example.com/publisher/v1/publisher-kel.cesr",
    )
    generate_and_upload_appcasts(s3=s3, config=cfg)

    macos = json.loads(captured["appcast/v1/macos.json"])
    assert len(macos["releases"]) == 3
    assert macos["current_version"] == "1.1.0"
    assert [r["version"] for r in macos["releases"]] == ["1.0.0", "1.0.1", "1.1.0"]


def test_generator_current_version_is_highest_semver():
    anchors = _real_anchors()
    s3 = MagicMock()
    s3.list_release_versions.return_value = ["1.1.0", "1.0.1", "1.0.0"]
    s3.get_object.side_effect = lambda Bucket, Key: anchors[Key.split("/")[1]]
    captured: dict[str, bytes] = {}
    s3.put_object.side_effect = (
        lambda Bucket, Key, Body, **kw: captured.update({Key: Body})
    )
    cfg = GeneratorConfig(
        bucket="releases.example.com",
        publisher_aid="EAaa",
        publisher_kel_url="https://releases.example.com/publisher/v1/publisher-kel.cesr",
    )
    generate_and_upload_appcasts(s3=s3, config=cfg)
    macos = json.loads(captured["appcast/v1/macos.json"])
    assert macos["current_version"] == "1.1.0"


def test_generator_no_releases_short_circuits():
    s3 = MagicMock()
    s3.list_release_versions.return_value = []
    cfg = GeneratorConfig(
        bucket="releases.example.com",
        publisher_aid="EAaa",
        publisher_kel_url="https://releases.example.com/publisher/v1/publisher-kel.cesr",
    )
    generate_and_upload_appcasts(s3=s3, config=cfg)
    s3.put_object.assert_not_called()


def test_generator_emits_appcast_compatible_with_parser():
    """The generated appcast must parse cleanly via locksmith.update.appcast."""
    from locksmith.update.appcast import parse_appcast

    anchors = _real_anchors()
    s3 = _build_s3_mock(anchors)
    captured: dict[str, bytes] = {}
    s3.put_object.side_effect = (
        lambda Bucket, Key, Body, **kw: captured.update({Key: Body})
    )
    cfg = GeneratorConfig(
        bucket="releases.example.com",
        publisher_aid="EAaa",
        publisher_kel_url="https://releases.example.com/publisher/v1/publisher-kel.cesr",
    )
    generate_and_upload_appcasts(s3=s3, config=cfg)
    # Round-trip through the verifier's parser — must succeed.
    ac = parse_appcast(captured["appcast/v1/macos.json"])
    assert ac.current_version == "1.1.0"
    assert len(ac.releases) == 3
