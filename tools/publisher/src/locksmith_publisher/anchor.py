"""Trust anchor file emission + release ixn event construction.

The Phase 1 ``PublisherAnchor`` dataclass and writers live here; Phase 4 adds
``build_release_seal()`` and ``IxnAnchor`` for release-anchoring ``ixn`` event
construction. See ``release_anchor.py`` for the higher-level pipeline that
joins this with the witness client.

Produces:

1. ``publisher_anchor.json`` — committed inside ``src/locksmith/release/``.
   Embedded in every PyInstaller build. Bootstraps trust on first install.
2. ``publisher-aid.json`` — uploaded to S3 at ``publisher/v1/publisher-aid.json``.
   Restates the current AID + latest KEL state for clients pulling fresh trust.
3. Release seals + signed CESR ixn events that anchor each release into the
   publisher KEL (used by the verifier downstream).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, List

from keri.app import habbing
from keri.core import serdering


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PublisherAnchor:
    publisher_aid: str
    embedded_kel_hash: str
    embedded_kel_sn: int
    witness_oobis: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.witness_oobis) < 3:
            raise ValueError(
                f"publisher anchor requires at least 3 witnesses; got {len(self.witness_oobis)}"
            )


def write_publisher_anchor(anchor: PublisherAnchor, path: Path) -> None:
    """Write the embedded trust anchor JSON. Indented for readability in commits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = asdict(anchor)
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_publisher_summary(anchor: PublisherAnchor, path: Path, *, latest_kel_url: str) -> None:
    """Write the S3-bound publisher-aid.json summary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "publisher_aid": anchor.publisher_aid,
        "latest_kel_hash": anchor.embedded_kel_hash,
        "latest_kel_sn": anchor.embedded_kel_sn,
        "witnesses": list(anchor.witness_oobis),
        "kel_events_url": latest_kel_url,
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Phase 4: release ixn anchor construction
# ---------------------------------------------------------------------------


def build_release_seal(
    *,
    version: str,
    channel: str,
    released_at: str,
    is_major: bool,
    is_critical: bool,
    previous_version: str | None,
    minimum_system_versions: dict[str, str],
    artifacts: list[dict[str, Any]],
    release_notes_said: str,
) -> dict[str, Any]:
    """Build a release seal dict in canonical field order (spec §7.4).

    Validates artifact entries: SHA256 must be lowercase hex64, size > 0,
    platform must be one of {"macos", "windows"}.

    Raises ``ValueError`` for any structural violation. The returned dict is
    the payload anchored in the ixn event's ``a`` field.
    """
    if not artifacts:
        raise ValueError("artifacts must be non-empty")
    for a in artifacts:
        if not _SHA256_RE.match(a.get("sha256", "")):
            raise ValueError(
                f"artifact sha256 not lowercase hex64: {a.get('sha256')!r}"
            )
        if a.get("size", 0) <= 0:
            raise ValueError(f"artifact size must be > 0: {a}")
        if a.get("platform") not in ("macos", "windows"):
            raise ValueError(f"unknown platform: {a.get('platform')!r}")
    return {
        "release": {
            "v": version,
            "channel": channel,
            "released_at": released_at,
            "is_major": is_major,
            "is_critical": is_critical,
            "previous_version": previous_version,
            "minimum_system_versions": minimum_system_versions,
            "artifacts": artifacts,
            "release_notes_said": release_notes_said,
        }
    }


@dataclass
class Anchor:
    """A built (and possibly signed) release anchor.

    ``raw`` is the CESR-encoded ixn event with attached controller signatures
    and (post-submission) witness receipts. ``serder`` is the parsed event.
    """

    raw: bytes
    serder: serdering.SerderKERI

    @property
    def said(self) -> str:
        return self.serder.said

    @property
    def sn(self) -> int:
        return self.serder.sn


@dataclass
class IxnAnchor:
    """Builder for a release-anchoring ``ixn`` event.

    Wraps a publisher ``Hab`` so the underlying KEL advances exactly once
    per ``build()`` call. The seal dict is the payload anchored in ``a``.
    """

    hab: habbing.Hab
    seal: dict

    def build(self) -> Anchor:
        msg = self.hab.interact(data=[self.seal])
        serder = serdering.SerderKERI(raw=bytearray(msg))
        return Anchor(raw=bytes(msg), serder=serder)
