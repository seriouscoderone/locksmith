"""Canonical JSON serialization for micro-app templates.

Produces a deterministic, sorted-keys, two-space-indented JSON form
used both for human-facing files on disk and as input to SAID
computation. Round-trip stable: parse(canonicalize(x)) -> canonicalize again
yields the same bytes.
"""
from __future__ import annotations

import json
from typing import Any


def canonicalize(obj: Any) -> str:
    """Render obj as canonical JSON.

    - Keys sorted lexicographically at every level
    - UTF-8 encoded (no ASCII escaping)
    - Two-space indent
    - Single trailing newline
    """
    return json.dumps(
        obj,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        separators=(",", ": "),
    ) + "\n"
