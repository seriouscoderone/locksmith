# -*- encoding: utf-8 -*-
"""
locksmith.plugins.manifest module

Parser + validator for ``locksmith-plugin.toml``.

Pure-function module. No I/O beyond reading the manifest path; no Qt;
no PluginManager dependency. Returns a Manifest dataclass that captures
exactly the fields the spec defines. Unknown keys are preserved in
``extra`` so future fields don't trip on this parser.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ENTRY_POINT_RE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")


class ManifestError(ValueError):
    """Raised when a manifest is missing, malformed, or fails validation."""


@dataclass(frozen=True)
class Manifest:
    plugin_id: str
    entry_point: str
    manifest_version: int
    name: str
    version: str
    description: str
    author: str = ""
    homepage: str = ""
    license: str = ""
    requires_locksmith: str = ""
    capabilities: list[str] = field(default_factory=list)
    capabilities_detail: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable snapshot. Stored in index.json at install time."""
        return asdict(self)


REQUIRED_FIELDS = ("plugin_id", "entry_point", "manifest_version")
TRUST_DIALOG_FIELDS = ("name", "version", "description")
KNOWN_FIELDS = {
    *REQUIRED_FIELDS,
    *TRUST_DIALOG_FIELDS,
    "author", "homepage", "license", "requires_locksmith",
    "capabilities", "capabilities_detail",
}


def parse_manifest(path: Path | str) -> Manifest:
    """Read and parse a manifest file. Raises ManifestError on failure."""
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"manifest file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ManifestError(f"could not read manifest {path}: {e}") from e
    return parse_manifest_text(text, source=str(path))


def parse_manifest_text(text: str, *, source: str) -> Manifest:
    """Parse manifest text. `source` is only used for error messages."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(f"invalid TOML in {source}: {e}") from e

    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ManifestError(
            f"manifest at {source} is missing required field(s): "
            f"{', '.join(missing)}"
        )

    missing_trust = [f for f in TRUST_DIALOG_FIELDS if not data.get(f)]
    if missing_trust:
        raise ManifestError(
            f"manifest at {source} is missing required trust-dialog field(s): "
            f"{', '.join(missing_trust)}"
        )

    if not isinstance(data["plugin_id"], str) or not PLUGIN_ID_RE.match(data["plugin_id"]):
        raise ManifestError(
            f"manifest at {source}: plugin_id must match {PLUGIN_ID_RE.pattern!r}, "
            f"got {data['plugin_id']!r}"
        )

    if not isinstance(data["entry_point"], str) or not ENTRY_POINT_RE.match(data["entry_point"]):
        raise ManifestError(
            f"manifest at {source}: entry_point must be 'module:Class', "
            f"got {data['entry_point']!r}"
        )

    if data["manifest_version"] != 1:
        raise ManifestError(
            f"manifest at {source}: unsupported manifest_version "
            f"{data['manifest_version']} (this wallet supports 1)"
        )

    extra = {k: v for k, v in data.items() if k not in KNOWN_FIELDS}
    return Manifest(
        plugin_id=data["plugin_id"],
        entry_point=data["entry_point"],
        manifest_version=int(data["manifest_version"]),
        name=data["name"],
        version=data["version"],
        description=data["description"],
        author=str(data.get("author", "")),
        homepage=str(data.get("homepage", "")),
        license=str(data.get("license", "")),
        requires_locksmith=str(data.get("requires_locksmith", "")),
        capabilities=list(data.get("capabilities", []) or []),
        capabilities_detail=dict(data.get("capabilities_detail", {}) or {}),
        extra=extra,
    )
