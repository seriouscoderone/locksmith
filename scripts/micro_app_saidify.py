#!/usr/bin/env python3
"""CLI wrapper: compute or verify the SAID of a micro-app template.

The on-disk form uses canonical (sorted-keys) JSON, so SAID computation
must operate on the same sorted form to round-trip stably. We
recursively sort the document before delegating to the saidify library.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from locksmith.micro_app_template.canonical_json import canonicalize
from locksmith.micro_app_template.saidify import (
    compute_said,
    saidify_document,
    verify_said,
)


def _sort_recursive(obj: Any) -> Any:
    """Recursively sort dict keys so SAID computation matches canonical JSON."""
    if isinstance(obj, dict):
        return {k: _sort_recursive(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_sort_recursive(x) for x in obj]
    return obj


def main() -> int:
    p = argparse.ArgumentParser(description="Stamp or verify the SAID of a micro-app template.")
    p.add_argument("--input", required=True, type=Path, help="Path to micro-app-template.json")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--in-place", action="store_true", help="Stamp the SAID in place")
    g.add_argument("--verify", action="store_true", help="Verify the existing SAID; exit non-zero on mismatch")
    g.add_argument("--print", action="store_true", help="Print the computed SAID to stdout without modifying the file")
    args = p.parse_args()

    if not args.input.exists():
        print(f"error: file not found: {args.input}", file=sys.stderr)
        return 2

    doc = _sort_recursive(json.loads(args.input.read_text()))

    if args.in_place:
        stamped = saidify_document(doc)
        args.input.write_text(canonicalize(stamped))
        print(f"stamped {args.input} with SAID {stamped['d']}", file=sys.stderr)
        return 0

    if args.verify:
        ok = verify_said(doc)
        if ok:
            print(f"OK: SAID matches", file=sys.stderr)
            return 0
        print(f"FAIL: SAID mismatch in {args.input}", file=sys.stderr)
        return 1

    if args.print:
        print(compute_said(doc))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
