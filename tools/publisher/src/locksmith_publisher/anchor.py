"""Trust anchor file emission.

Produces two artifacts:

1. `publisher_anchor.json` — committed inside `src/locksmith/release/`.
   Embedded in every PyInstaller build. Bootstraps trust on first install.
2. `publisher-aid.json` — uploaded to S3 at `publisher/v1/publisher-aid.json`.
   Restates the current AID + latest KEL state for clients pulling fresh trust.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List


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
