#!/usr/bin/env python3
"""Fail if the active brand is incomplete or still a placeholder (CI guard:
a tagged release must ship a fully-branded, real-trust build — never half
white-labeled or gate-dark). Mirrors scripts/check-anchor-present.py.

Importable as `check_brand_complete` (hyphen→underscore) for tests.
"""
import argparse
import json
import sys
import tomllib
from pathlib import Path

_LOCKSMITH_BUNDLE = "host.keri.locksmith"
_LOCKSMITH_UPGRADE = "297BBF26-821C-4D56-8857-309C7B531E21"
_REQUIRED_IDENTITY = ("bundle_id", "upgrade_code", "data_dir",
                      "artifact_prefix", "org_domain")
_ANCHOR_PLACEHOLDER = "Placeholder"


def validate(brand_id: str, brands_dir: Path) -> list[str]:
    problems = []
    bdir = Path(brands_dir) / brand_id
    toml_path = bdir / "brand.toml"
    if not toml_path.is_file():
        return [f"no brand.toml for brand {brand_id!r} at {toml_path}"]
    m = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    ident = m.get("identity", {})
    for field in _REQUIRED_IDENTITY:
        if not ident.get(field):
            problems.append(f"missing identity.{field}")

    is_example = brand_id == "example"
    is_locksmith = brand_id == "locksmith"

    if not is_example:
        for label, val in (("website", m.get("urls", {}).get("website", "")),
                           ("support", m.get("urls", {}).get("support", ""))):
            if "example.com" in val or not val:
                problems.append(f"placeholder/empty urls.{label} ({val!r})")
        uc = ident.get("upgrade_code", "")
        if set(uc) <= {"0", "-"}:
            problems.append(f"placeholder upgrade_code ({uc!r})")

    if not is_locksmith:
        if ident.get("bundle_id") == _LOCKSMITH_BUNDLE:
            problems.append("non-locksmith brand reuses Locksmith bundle_id "
                            f"({_LOCKSMITH_BUNDLE})")
        if ident.get("upgrade_code") == _LOCKSMITH_UPGRADE:
            problems.append("non-locksmith brand reuses Locksmith upgrade_code")
        if brand_id not in ("locksmith", "example"):
            for key, fname in m.get("assets", {}).items():
                if not (bdir / fname).is_file():
                    problems.append(f"missing asset file {fname} (assets.{key})")

    if not is_example:
        anchor_name = m.get("publisher", {}).get("anchor", "publisher_anchor.json")
        anchor_path = bdir / anchor_name
        if not anchor_path.is_file():
            problems.append(f"missing publisher anchor at {anchor_path}")
        else:
            doc = json.loads(anchor_path.read_text(encoding="utf-8"))
            aid = doc.get("publisher_aid", "")
            if not aid or _ANCHOR_PLACEHOLDER in aid:
                problems.append(f"placeholder/empty publisher_aid ({aid!r})")
            if not doc.get("witness_oobis"):
                problems.append("anchor has no witness_oobis")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    ap.add_argument("--brands-dir",
                    default=str(Path(__file__).resolve().parent.parent / "brands"))
    args = ap.parse_args()
    problems = validate(args.brand, Path(args.brands_dir))
    if problems:
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 1
    print(f"brand OK: {args.brand}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
