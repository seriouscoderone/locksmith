"""Release-anchor build pipeline.

Joins the seal builder + ``IxnAnchor`` + the publisher's persisted KEL into
one operator-facing call: given a set of release artifacts (paths + hashes
already computed), append an ``ixn`` event to the publisher KEL with the
release seal anchored in its ``a`` field.

This module is signing-agnostic: it just produces the signed CESR event
bytes via the ``Hab.interact()`` path. The publisher's signing keys are
managed by the Hab (loaded from the software-key store via
``incept.run_inception_ceremony``'s ``--software-keys`` mode).

Per Phase 4 user deviation #2: signing runs on the operator's laptop after
CI has uploaded the artifacts to S3; the publisher private key never enters
CI infrastructure.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from keri.app import habbing

from .anchor import Anchor, IxnAnchor, build_release_seal


@dataclass(frozen=True)
class ArtifactInput:
    """Operator-supplied artifact descriptor for a single platform binary."""

    platform: str  # "macos" | "windows"
    filename: str
    path: Path
    size: int

    @classmethod
    def from_path(cls, *, platform: str, path: Path) -> "ArtifactInput":
        if not path.is_file():
            raise FileNotFoundError(f"artifact not found: {path}")
        return cls(
            platform=platform,
            filename=path.name,
            path=path,
            size=path.stat().st_size,
        )

    def sha256(self) -> str:
        h = hashlib.sha256()
        with self.path.open("rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()


@dataclass(frozen=True)
class ReleaseAnchorRequest:
    """Inputs needed to build one release-anchor event."""

    version: str
    channel: str
    released_at: str
    is_major: bool
    is_critical: bool
    previous_version: str | None
    minimum_system_versions: dict[str, str]
    artifacts: tuple[ArtifactInput, ...]
    release_notes_said: str


def build_release_anchor(
    *,
    hab: habbing.Hab,
    request: ReleaseAnchorRequest,
) -> Anchor:
    """Append a release-anchoring ixn event to ``hab``'s KEL and return it.

    The publisher Hab must already be incepted (sn 0) and reside in the
    operator's local keystore. The Hab's own signers are used to sign the
    event (single-sig per Phase 1 deviation; the Hab knows how many keys
    are required from its inception threshold).
    """
    artifact_dicts = []
    for a in request.artifacts:
        artifact_dicts.append({
            "platform": a.platform,
            "filename": a.filename,
            "sha256": a.sha256(),
            "size": a.size,
        })
    seal = build_release_seal(
        version=request.version,
        channel=request.channel,
        released_at=request.released_at,
        is_major=request.is_major,
        is_critical=request.is_critical,
        previous_version=request.previous_version,
        minimum_system_versions=request.minimum_system_versions,
        artifacts=artifact_dicts,
        release_notes_said=request.release_notes_said,
    )
    return IxnAnchor(hab=hab, seal=seal).build()


def write_release_anchor_files(
    anchor: Anchor,
    *,
    out_dir: Path,
    version: str,
    receipts_cesr: bytes | None = None,
) -> dict[str, Path]:
    """Persist the anchor event (and optional receipts) under ``out_dir``.

    Layout::

        out_dir/release-anchor-X.Y.Z.cesr            — signed event
        out_dir/release-anchor-X.Y.Z.receipts.cesr   — witness receipts (if any)
        out_dir/release-anchor-X.Y.Z.json            — convenience metadata

    Returns a dict of ``{tag: path}`` for the files written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    event_path = out_dir / f"release-anchor-{version}.cesr"
    event_path.write_bytes(anchor.raw)

    paths: dict[str, Path] = {"event": event_path}

    if receipts_cesr is not None:
        receipts_path = out_dir / f"release-anchor-{version}.receipts.cesr"
        receipts_path.write_bytes(receipts_cesr)
        paths["receipts"] = receipts_path

    meta = {
        "version": version,
        "said": anchor.said,
        "sn": anchor.sn,
        "ilk": anchor.serder.ked.get("t"),
        "seal": anchor.serder.ked.get("a", [])[0] if anchor.serder.ked.get("a") else None,
    }
    meta_path = out_dir / f"release-anchor-{version}.json"
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    paths["meta"] = meta_path

    return paths
