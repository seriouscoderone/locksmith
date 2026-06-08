"""Tests for ``locksmith_publisher.anchor`` — release ixn event construction.

Covers the Phase 4 additions: ``build_release_seal()`` and ``IxnAnchor``.
The Phase 1 ``PublisherAnchor`` dataclass + writers have separate coverage
in ``tools/publisher/tests/test_anchor.py``.
"""
from __future__ import annotations

import uuid

import pytest

from locksmith_publisher.anchor import (
    Anchor,
    IxnAnchor,
    build_release_seal,
)


@pytest.fixture
def sample_seal() -> dict:
    return build_release_seal(
        version="1.2.3",
        channel="stable",
        released_at="2026-05-28T14:30:00Z",
        is_major=False,
        is_critical=False,
        previous_version="1.2.2",
        minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
        artifacts=[
            {
                "platform": "macos",
                "filename": "Locksmith-1.2.3.dmg",
                "sha256": "a" * 64,
                "size": 87654321,
            },
            {
                "platform": "windows",
                "filename": "Locksmith-1.2.3.msi",
                "sha256": "b" * 64,
                "size": 92345678,
            },
        ],
        release_notes_said="EHshReleaseNotesSAIDPlaceholderXXXXXXXXXXXX",
    )


def test_build_release_seal_matches_spec_schema(sample_seal):
    assert sample_seal["release"]["v"] == "1.2.3"
    assert sample_seal["release"]["channel"] == "stable"
    assert len(sample_seal["release"]["artifacts"]) == 2
    assert sample_seal["release"]["is_major"] is False
    assert sample_seal["release"]["release_notes_said"].startswith("EHsh")


def test_seal_field_order_is_deterministic(sample_seal):
    keys = list(sample_seal["release"].keys())
    assert keys == [
        "v",
        "channel",
        "released_at",
        "is_major",
        "is_critical",
        "previous_version",
        "minimum_system_versions",
        "artifacts",
        "release_notes_said",
    ]


def test_ixn_anchor_builds_event_for_publisher(sample_seal):
    from keri.app import habbing

    suffix = uuid.uuid4().hex[:8]
    hby = habbing.Habery(name=f"anchor_test_{suffix}", base="", temp=True)
    try:
        hab = hby.makeHab(
            name="pub",
            transferable=True,
            wits=[],
            toad=0,
            icount=1,
            isith="1",
            ncount=1,
            nsith="1",
        )
        anchor = IxnAnchor(hab=hab, seal=sample_seal)
        event = anchor.build()
        assert isinstance(event, Anchor)
        assert event.serder.ked["t"] == "ixn"
        assert event.serder.ked["a"][0] == sample_seal
        assert event.said  # SAID computed
        assert event.sn == 1  # first ixn after icp
    finally:
        hby.close()


def test_invalid_seal_missing_artifacts_raises():
    with pytest.raises(ValueError) as e:
        build_release_seal(
            version="1.0.0",
            channel="stable",
            released_at="2026-05-28T00:00:00Z",
            is_major=False,
            is_critical=False,
            previous_version=None,
            minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
            artifacts=[],
            release_notes_said="E",
        )
    assert "artifacts" in str(e.value).lower()


def test_invalid_artifact_sha256_length_raises():
    with pytest.raises(ValueError):
        build_release_seal(
            version="1.0.0",
            channel="stable",
            released_at="2026-05-28T00:00:00Z",
            is_major=False,
            is_critical=False,
            previous_version=None,
            minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
            artifacts=[
                {
                    "platform": "macos",
                    "filename": "x.dmg",
                    "sha256": "tooshort",
                    "size": 1,
                }
            ],
            release_notes_said="E",
        )


def test_invalid_artifact_size_raises():
    with pytest.raises(ValueError):
        build_release_seal(
            version="1.0.0",
            channel="stable",
            released_at="2026-05-28T00:00:00Z",
            is_major=False,
            is_critical=False,
            previous_version=None,
            minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
            artifacts=[
                {
                    "platform": "macos",
                    "filename": "x.dmg",
                    "sha256": "a" * 64,
                    "size": 0,
                }
            ],
            release_notes_said="E",
        )


def test_unknown_platform_raises():
    with pytest.raises(ValueError):
        build_release_seal(
            version="1.0.0",
            channel="stable",
            released_at="2026-05-28T00:00:00Z",
            is_major=False,
            is_critical=False,
            previous_version=None,
            minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
            artifacts=[
                {
                    "platform": "linux",  # not in {"macos","windows"}
                    "filename": "x.AppImage",
                    "sha256": "a" * 64,
                    "size": 1,
                }
            ],
            release_notes_said="E",
        )
