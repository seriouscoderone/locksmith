#!/usr/bin/env python3
"""Fail if the publisher anchor is missing or still a placeholder (CI guard:
a tagged release must ship with a real KERI trust anchor, never gate-dark)."""
import argparse
import json
import sys

_PLACEHOLDER = "Placeholder"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", required=True)
    args = ap.parse_args()
    try:
        doc = json.loads(open(args.anchor).read())
    except FileNotFoundError:
        print(f"ERROR: publisher anchor not found at {args.anchor}", file=sys.stderr)
        return 1
    aid = doc.get("publisher_aid", "")
    if not aid or _PLACEHOLDER in aid:
        print(f"ERROR: placeholder/empty publisher_aid ({aid!r})", file=sys.stderr)
        return 1
    if not doc.get("witness_oobis"):
        print("ERROR: no witness_oobis in anchor", file=sys.stderr)
        return 1
    print(f"anchor OK: publisher_aid={aid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
