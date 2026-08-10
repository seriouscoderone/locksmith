#!/usr/bin/env python3
"""Refuse a release whose BAKED publisher anchor cannot sign its own feed.

The publisher trust anchor is build-injected: CI writes the
``LOCKSMITH_PUBLISHER_ANCHOR`` secret into the app bundle. If that secret drifts
from the AID that actually signs the published appcast — as it did after a
publisher re-inception before v0.2.21 — then every client built from that
artifact bakes a trust root which CANNOT verify the feed. Sparkle finds the
update and the in-app KERI gate rejects it: "update could not be verified".

Checking the LOCAL ``src/locksmith/release/publisher_anchor.json`` does not
catch this, because that file can be perfectly correct while the CI secret is
stale. Only the bytes inside the artifact answer the question.

This is deliberately NARROWER than ``scripts/verify-release-artifact.py``: it
compares publisher AIDs and nothing else, so it can run BEFORE the feed carries
the new version. That ordering is the point — the full verifier can only run
after publishing, by which time a mismatched feed is already live.

Usage:
    scripts/check-baked-anchor.py --dmg dist/Usurance-0.4.0.dmg --brand usurance

Exits non-zero on mismatch, on a missing anchor, or if the feed cannot be read.
"""
from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _brand_feed_url(brand: str) -> str:
    """The macOS JSON appcast URL this brand's clients verify against.

    Read from the brand manifest, NOT from the shared deploy_config.json: that
    file names locksmith's feed for every brand, and a non-locksmith brand
    verifying against it reads a `locksmith` seal and fails its own brand check.
    """
    manifest = REPO / "brands" / brand / "brand.toml"
    if not manifest.is_file():
        raise SystemExit(f"check-baked-anchor: no brand manifest at {manifest}")
    doc = tomllib.loads(manifest.read_text(encoding="utf-8"))
    url = (doc.get("urls", {}) or {}).get("appcast_macos")
    if not url:
        raise SystemExit(
            f"check-baked-anchor: {brand} brand.toml states no [urls] appcast_macos")
    return url


def _mounted(dmg: Path):
    """Attach a DMG read-only and yield its mountpoint, always detaching."""
    out = subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-readonly", "-plist", str(dmg)],
        check=True, capture_output=True)
    plist = plistlib.loads(out.stdout)
    points = [e["mount-point"] for e in plist["system-entities"] if "mount-point" in e]
    if not points:
        raise SystemExit(f"check-baked-anchor: {dmg} attached but mounted nothing")
    return points[0]


def _baked_anchor(mountpoint: str) -> dict:
    """The publisher_anchor.json the app will actually use at runtime."""
    apps = list(Path(mountpoint).glob("*.app"))
    if not apps:
        raise SystemExit(f"check-baked-anchor: no .app in {mountpoint}")
    candidates = list(apps[0].rglob("locksmith/release/publisher_anchor.json"))
    if not candidates:
        raise SystemExit(
            f"check-baked-anchor: {apps[0].name} ships NO publisher_anchor.json — "
            "the update gate would be dark. CI did not inject the anchor.")
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dmg", required=True, type=Path)
    ap.add_argument("--brand", required=True)
    args = ap.parse_args(argv)

    feed_url = _brand_feed_url(args.brand)
    # Fetch under a DISTINCT cache key (a query param CloudFront varies on is
    # not needed — any unique query string yields its own edge object) so this
    # preflight cannot warm the canonical URL's edge cache with a copy that is
    # about to go stale. Without this, running the check immediately before
    # publishing left the edge serving the OLD appcast at the canonical URL while
    # S3 already had the new one, and the post-publish verification then failed
    # on a feed that was actually correct at origin. Observed on the v0.4.0
    # locksmith promote: macos stale (this check had fetched it), windows fresh.
    with urllib.request.urlopen(f"{feed_url}?preflight=1", timeout=30) as resp:
        feed = json.loads(resp.read().decode("utf-8"))
    feed_aid = feed.get("publisher_aid", "")
    if not feed_aid:
        raise SystemExit(f"check-baked-anchor: {feed_url} names no publisher_aid")

    mountpoint = _mounted(args.dmg)
    try:
        anchor = _baked_anchor(mountpoint)
    finally:
        subprocess.run(["hdiutil", "detach", mountpoint, "-quiet"], check=False)

    baked_aid = anchor.get("publisher_aid", "")
    print(f"    brand      : {args.brand}")
    print(f"    feed       : {feed_url}")
    print(f"    feed  aid  : {feed_aid}")
    print(f"    baked aid  : {baked_aid}")

    if not baked_aid or "Placeholder" in baked_aid:
        print("    MISMATCH: the artifact carries a placeholder/empty anchor",
              file=sys.stderr)
        return 1
    if baked_aid != feed_aid:
        print("    MISMATCH: baked anchor cannot verify this brand's feed",
              file=sys.stderr)
        return 1
    print("    OK: baked anchor matches the AID signing this brand's feed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
