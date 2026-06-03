#!/usr/bin/env python3
"""CI preflight: assert git tag matches pyproject version, is semver, and is signed.

Usage:
    scripts/check-version.py --tag v1.2.3 [--pyproject pyproject.toml] [--skip-tag-signature]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def die(msg: str) -> None:
    print(f"check-version: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="git tag, e.g. v1.2.3")
    ap.add_argument(
        "--pyproject",
        default="pyproject.toml",
        help="path to pyproject.toml (default: ./pyproject.toml)",
    )
    ap.add_argument(
        "--skip-tag-signature",
        action="store_true",
        help="skip git verify-tag (for local/dev use only; CI must NOT pass this)",
    )
    args = ap.parse_args()

    tag = args.tag
    if not tag.startswith("v"):
        die(f"tag {tag!r} must start with 'v' (e.g. v1.2.3)")

    version = tag[1:]
    if not SEMVER.match(version):
        die(f"version {version!r} is not valid semver")

    pyproject_path = Path(args.pyproject)
    if not pyproject_path.exists():
        die(f"pyproject not found: {pyproject_path}")

    with pyproject_path.open("rb") as fh:
        data = tomllib.load(fh)
    pyver = data.get("project", {}).get("version")
    if pyver != version:
        die(f"tag {tag} does not match pyproject version {pyver}")

    if not args.skip_tag_signature:
        try:
            subprocess.run(
                ["git", "verify-tag", tag],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            die(
                f"git verify-tag failed for {tag}: tag signature missing or invalid.\n"
                f"stderr: {exc.stderr.strip()}"
            )
        except FileNotFoundError:
            die("git not found in PATH; cannot verify tag signature")

    print(f"check-version: OK — {tag} matches pyproject {pyver}, semver-valid, signed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
