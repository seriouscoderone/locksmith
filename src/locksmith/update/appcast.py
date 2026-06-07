"""Appcast JSON parser per spec §6.3.

Pure-data module — no network IO. ``parse_appcast(raw_json)`` validates
schema and returns an ``Appcast`` aggregate. Phase 5's UI calls
``select_latest_for_platform`` to pick the candidate to verify.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from locksmith.update.errors import SchemaError

CURRENT_SCHEMA_VERSION = 1
REQUIRED_TOP = (
    "schema_version",
    "channel",
    "publisher_aid",
    "publisher_kel_url",
    "current_version",
    "releases",
)
REQUIRED_REL = (
    "version",
    "released_at",
    "platform",
    "minimum_system_version",
    "artifact_url",
    "artifact_sha256",
    "artifact_size",
    "anchor_url",
    "anchor_said",
    "release_notes_url",
    "is_major",
    "is_critical",
)


@dataclass(frozen=True)
class Release:
    version: str
    released_at: str
    platform: str
    minimum_system_version: str
    artifact_url: str
    artifact_sha256: str
    artifact_size: int
    anchor_url: str
    anchor_said: str
    release_notes_url: str
    is_major: bool
    is_critical: bool


@dataclass(frozen=True)
class Appcast:
    schema_version: int
    channel: str
    publisher_aid: str
    publisher_kel_url: str
    current_version: str
    releases: tuple[Release, ...] = field(default_factory=tuple)


def _semver_key(v: str) -> tuple[int, int, int]:
    try:
        parts = v.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError) as ex:
        raise SchemaError(
            f"invalid semver: {v!r}",
            log_fields={"version": v},
        ) from ex


def parse_appcast(raw: str | bytes) -> Appcast:
    """Parse a raw appcast payload into an ``Appcast`` aggregate.

    Raises ``SchemaError`` on missing fields, wrong types, or invalid semver.
    """
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as ex:
        raise SchemaError(
            f"appcast not valid JSON: {ex}",
            log_fields={"raw_prefix": str(raw)[:80]},
        ) from ex

    if not isinstance(data, dict):
        raise SchemaError("appcast must be a JSON object")

    for key in REQUIRED_TOP:
        if key not in data:
            raise SchemaError(
                f"missing required appcast field: {key}",
                log_fields={"missing": key},
            )

    if data["schema_version"] != CURRENT_SCHEMA_VERSION:
        raise SchemaError(
            f"unsupported schema_version: {data['schema_version']} "
            f"(expected {CURRENT_SCHEMA_VERSION})",
            log_fields={"schema_version": data["schema_version"]},
        )

    releases_raw = data["releases"]
    if not isinstance(releases_raw, list) or not releases_raw:
        raise SchemaError("releases must be a non-empty list")

    releases: list[Release] = []
    for r in releases_raw:
        if not isinstance(r, dict):
            raise SchemaError(
                "each release must be a JSON object",
                log_fields={"release_type": type(r).__name__},
            )
        for k in REQUIRED_REL:
            if k not in r:
                raise SchemaError(
                    f"missing required release field: {k}",
                    log_fields={"missing": k, "version": r.get("version")},
                )
        releases.append(
            Release(
                version=r["version"],
                released_at=r["released_at"],
                platform=r["platform"],
                minimum_system_version=r["minimum_system_version"],
                artifact_url=r["artifact_url"],
                artifact_sha256=r["artifact_sha256"],
                artifact_size=int(r["artifact_size"]),
                anchor_url=r["anchor_url"],
                anchor_said=r["anchor_said"],
                release_notes_url=r["release_notes_url"],
                is_major=bool(r["is_major"]),
                is_critical=bool(r["is_critical"]),
            )
        )

    releases.sort(key=lambda r: _semver_key(r.version))

    return Appcast(
        schema_version=int(data["schema_version"]),
        channel=str(data["channel"]),
        publisher_aid=str(data["publisher_aid"]),
        publisher_kel_url=str(data["publisher_kel_url"]),
        current_version=str(data["current_version"]),
        releases=tuple(releases),
    )


def select_latest_for_platform(ac: Appcast, platform: str) -> Release:
    """Return the ``current_version`` release for ``platform``.

    Raises ``SchemaError`` if no release matches the appcast's
    ``current_version`` + platform combination.
    """
    for r in ac.releases:
        if r.version == ac.current_version and r.platform == platform:
            return r
    raise SchemaError(
        f"no release matches current_version={ac.current_version} platform={platform}",
        log_fields={
            "current_version": ac.current_version,
            "platform": platform,
        },
    )
