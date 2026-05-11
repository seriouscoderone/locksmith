#!/usr/bin/env python3
"""CLI wrapper: validate a micro-app template against the meta-schema and cross-references."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from locksmith.micro_app_template.validate import validate_template


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA = REPO_ROOT / "docs/superpowers/specs/schemas/micro-app-template.schema.json"


def main() -> int:
    p = argparse.ArgumentParser(description="Validate a micro-app template.")
    p.add_argument("--input", required=True, type=Path, help="Path to micro-app-template.json")
    p.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Path to meta-schema (default: project meta-schema)")
    args = p.parse_args()

    if not args.input.exists():
        print(f"error: file not found: {args.input}", file=sys.stderr)
        return 2
    if not args.schema.exists():
        print(f"error: schema not found: {args.schema}", file=sys.stderr)
        return 2

    doc = json.loads(args.input.read_text())
    result = validate_template(doc, args.schema)

    if result.is_valid:
        print(f"OK: {args.input} validates against {args.schema.name}")
        return 0

    print(f"FAIL: {args.input}", file=sys.stderr)
    for e in result.errors:
        print(f"  {e.path}: {e.message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
