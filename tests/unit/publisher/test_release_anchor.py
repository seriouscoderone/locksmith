"""Tests for ``locksmith_publisher.release_anchor`` — release ixn pipeline."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from locksmith_publisher.release_anchor import (
    ArtifactInput,
    ReleaseAnchorRequest,
    build_release_anchor,
    write_release_anchor_files,
)


@pytest.fixture
def mac_artifact(tmp_path: Path) -> ArtifactInput:
    p = tmp_path / "Locksmith-1.2.3.dmg"
    p.write_bytes(b"FAKE_DMG_BYTES_FOR_TEST")
    return ArtifactInput.from_path(platform="macos", path=p)


@pytest.fixture
def win_artifact(tmp_path: Path) -> ArtifactInput:
    p = tmp_path / "Locksmith-1.2.3.msi"
    p.write_bytes(b"FAKE_MSI_BYTES_FOR_TEST")
    return ArtifactInput.from_path(platform="windows", path=p)


@pytest.fixture
def request_obj(mac_artifact, win_artifact) -> ReleaseAnchorRequest:
    return ReleaseAnchorRequest(
        version="1.2.3",
        channel="stable",
        released_at="2026-05-28T14:30:00Z",
        is_major=False,
        is_critical=False,
        previous_version="1.2.2",
        minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
        artifacts=(mac_artifact, win_artifact),
        release_notes_said="EHshReleaseNotesSAIDPlaceholderXXXXXXXXXXXX",
    )


def _make_publisher_hab(tmp_path: Path):
    """Spin up a single-sig publisher Hab (no witnesses for unit testing)."""
    from keri.app import habbing
    suffix = uuid.uuid4().hex[:8]
    hby = habbing.Habery(name=f"pub_anchor_{suffix}", base="", temp=True)
    hab = hby.makeHab(
        name="publisher",
        transferable=True,
        isith="1",
        icount=1,
        nsith="1",
        ncount=1,
        wits=[],
        toad=0,
    )
    return hab, hby


def test_artifact_input_computes_sha256_from_file(mac_artifact):
    import hashlib
    expected = hashlib.sha256(b"FAKE_DMG_BYTES_FOR_TEST").hexdigest()
    assert mac_artifact.sha256() == expected


def test_artifact_input_size_matches_filesystem(mac_artifact):
    assert mac_artifact.size == len(b"FAKE_DMG_BYTES_FOR_TEST")


def test_artifact_input_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        ArtifactInput.from_path(platform="macos", path=tmp_path / "nope.dmg")


def test_build_release_anchor_appends_ixn_with_seal(request_obj, tmp_path):
    hab, hby = _make_publisher_hab(tmp_path)
    try:
        before_sn = hab.kever.sner.num
        anchor = build_release_anchor(hab=hab, request=request_obj)
        assert anchor.serder.ked["t"] == "ixn"
        assert anchor.sn == before_sn + 1
        seal = anchor.serder.ked["a"][0]
        assert seal["release"]["v"] == "1.2.3"
        assert len(seal["release"]["artifacts"]) == 2
        # Hab's KEL advanced.
        assert hab.kever.sner.num == before_sn + 1
    finally:
        hby.close()


def test_build_release_anchor_artifact_sha256_matches_seal(request_obj, tmp_path):
    hab, hby = _make_publisher_hab(tmp_path)
    try:
        anchor = build_release_anchor(hab=hab, request=request_obj)
        seal_mac = next(
            a for a in anchor.serder.ked["a"][0]["release"]["artifacts"]
            if a["platform"] == "macos"
        )
        # Recompute mac sha from the test bytes and compare.
        import hashlib
        expected = hashlib.sha256(b"FAKE_DMG_BYTES_FOR_TEST").hexdigest()
        assert seal_mac["sha256"] == expected
    finally:
        hby.close()


def test_write_release_anchor_files_emits_three_files(request_obj, tmp_path):
    hab, hby = _make_publisher_hab(tmp_path)
    try:
        anchor = build_release_anchor(hab=hab, request=request_obj)
        out = tmp_path / "out"
        paths = write_release_anchor_files(
            anchor,
            out_dir=out,
            version="1.2.3",
            receipts_cesr=b"FAKE_RECEIPTS_CESR",
        )
        assert paths["event"].read_bytes() == anchor.raw
        assert paths["receipts"].read_bytes() == b"FAKE_RECEIPTS_CESR"
        meta = json.loads(paths["meta"].read_text())
        assert meta["version"] == "1.2.3"
        assert meta["said"] == anchor.said
        assert meta["ilk"] == "ixn"
        assert meta["seal"]["release"]["v"] == "1.2.3"
    finally:
        hby.close()


def test_write_release_anchor_files_without_receipts(request_obj, tmp_path):
    hab, hby = _make_publisher_hab(tmp_path)
    try:
        anchor = build_release_anchor(hab=hab, request=request_obj)
        out = tmp_path / "out"
        paths = write_release_anchor_files(anchor, out_dir=out, version="1.2.3")
        assert "event" in paths
        assert "meta" in paths
        assert "receipts" not in paths
    finally:
        hby.close()
