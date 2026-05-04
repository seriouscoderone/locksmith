#!/usr/bin/env python3
"""Saidify an ACDC schema JSON file using `kli saidify`.

Walks the schema and saidifies every `$id` field bottom-up by shelling out
to keripy's `kli saidify`. This keeps SAID computation aligned with KERI's
canonical tooling — no parallel implementation to drift.

Usage:
    python scripts/saidify_schema.py <input.json> [<output.json>]

If <output.json> is omitted, the input file is rewritten in place.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def saidify_block_via_kli(block: dict) -> dict:
    """Saidify a single block by writing it to a temp file and invoking `kli saidify`.

    The block must have an `$id` field; it is reset to empty string before
    invocation so kli computes the SAID over a stable placeholder. Returns
    the block with its `$id` populated by kli.
    """
    block = {**block, "$id": ""}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(block, tmp)
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["kli", "saidify", "--file", tmp_path, "--label", "$id"],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(Path(tmp_path).read_text())
    except FileNotFoundError:
        raise SystemExit("error: `kli` not found on PATH. Activate the venv or install keripy.")
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"error: kli saidify failed: {e.stderr.strip()}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def saidify_schema(schema: dict) -> dict:
    """Saidify all `$id` fields in an ACDC schema, bottom-up.

    Handles the standard ACDC pattern where attribute/edge/rule sections
    appear as `oneOf` with two branches (compact SAID string + full block);
    only the full-block branch carries an `$id` to compute.
    """
    properties = schema.get("properties", {})
    for section_name in ("a", "e", "r"):
        section = properties.get(section_name)
        if not isinstance(section, dict):
            continue
        oneof = section.get("oneOf", [])
        for i, branch in enumerate(oneof):
            if isinstance(branch, dict) and "$id" in branch:
                oneof[i] = saidify_block_via_kli(branch)

    return saidify_block_via_kli(schema)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <schema.json> [<output.json>]", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path

    schema = json.loads(input_path.read_text())
    schema = saidify_schema(schema)
    output_path.write_text(json.dumps(schema, indent=2) + "\n")

    print(f"saidified {input_path} -> {output_path}")
    print(f"  schema SAID: {schema['$id']}")
    inner = schema.get("properties", {}).get("a", {}).get("oneOf", [None, None])[1]
    if isinstance(inner, dict) and inner.get("$id"):
        print(f"  attributes SAID: {inner['$id']}")


if __name__ == "__main__":
    main()
