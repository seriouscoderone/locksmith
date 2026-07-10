#!/usr/bin/env python3
"""Release gate: verify a BUILT artifact end-to-end using the trust anchor and
feed URL *baked into that artifact* — not the local source anchor.

Why this exists
---------------
The publisher anchor + feed URL are build-injected (CI writes the
``LOCKSMITH_PUBLISHER_ANCHOR`` secret into the app; ``brand_apply`` writes
``brand.json``). If the injected anchor drifts from the AID that actually signs
the published feed (e.g. the secret was not updated after a publisher
re-inception), every shipped client bakes a trust root that CANNOT verify the
feed — Sparkle finds the update but the in-app KERI gate rejects it. Verifying
against the *local* ``src/.../publisher_anchor.json`` hides this, because that
file can be correct while the CI secret is stale.

This gate mounts the DMG, reads the anchor + brand that the app will actually
use at runtime, and runs the real ``verify_artifact`` pipeline against the live
feed for both platforms. The baked anchor is identical across a brand's DMG and
MSI (same CI injection), so the DMG is the anchor source for both legs.

Run it after the build and BEFORE promoting a release to latest:

    scripts/verify-release-artifact.py \
        --dmg /tmp/promote-X/Usurance-X.dmg \
        --msi /tmp/promote-X/Usurance-X.msi

Exits non-zero if any (platform) leg fails.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# The repo ships a top-level packaging/ dir that shadows the installed
# `packaging` library when '' / repo-root is on sys.path (see CLAUDE.md).
# Drop those entries so `import packaging.version` (pulled in by keri) resolves
# to site-packages regardless of the caller's CWD.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path[:] = [p for p in sys.path if p not in ("", ".", _REPO_ROOT)]


def _mount_dmg(dmg: Path):
    mp = tempfile.mkdtemp(prefix="verifyrel.")
    subprocess.run(
        ["hdiutil", "attach", str(dmg), "-mountpoint", mp,
         "-nobrowse", "-readonly", "-quiet"],
        check=True,
    )
    return mp


def _detach(mp: str) -> None:
    subprocess.run(["hdiutil", "detach", mp, "-quiet"], check=False)


def _read_baked(app: Path) -> tuple[dict, dict]:
    rel = app / "Contents" / "Resources" / "locksmith" / "release"
    anchor = json.loads((rel / "publisher_anchor.json").read_text())
    brand = json.loads((rel / "brand.json").read_text())
    return anchor, brand


def _json_feed(xml_url: str) -> str:
    if not xml_url.endswith(".xml"):
        raise ValueError(f"unexpected appcast url (not .xml): {xml_url}")
    return xml_url[:-4] + ".json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dmg", required=True, type=Path,
                    help="macOS DMG — anchor/brand source AND the macos artifact")
    ap.add_argument("--msi", type=Path, default=None,
                    help="Windows MSI — verified with the same baked anchor")
    args = ap.parse_args()

    from locksmith.update.verify import verify_artifact, _fetch_url  # noqa: E402

    if not args.dmg.is_file():
        print(f"[ERR] DMG not found: {args.dmg}", file=sys.stderr)
        return 2

    mp = _mount_dmg(args.dmg)
    try:
        apps = list(Path(mp).glob("*.app"))
        if not apps:
            print(f"[ERR] no .app in {args.dmg}", file=sys.stderr)
            return 2
        anchor, brand = _read_baked(apps[0])
    finally:
        _detach(mp)

    pub = anchor["publisher_aid"]
    brand_id = brand["id"]
    print(f"baked anchor publisher_aid = {pub}")
    print(f"baked brand id             = {brand_id}")

    legs: list[tuple[str, Path, str]] = [
        ("macos", args.dmg, _json_feed(brand["appcast_macos_xml"])),
    ]
    if args.msi is not None:
        legs.append(("windows", args.msi, _json_feed(brand["appcast_windows_xml"])))

    failures = 0
    for platform, artifact, feed in legs:
        if not artifact.is_file():
            print(f"[FAIL] {brand_id} {platform}: artifact missing {artifact}")
            failures += 1
            continue
        try:
            res = verify_artifact(
                artifact_path=artifact,
                appcast_raw=_fetch_url(feed),
                platform=platform,
                embedded_publisher_aid=pub,
                embedded_kel_sn=anchor["embedded_kel_sn"],
                embedded_kel_said=anchor["embedded_kel_hash"],
                toad=anchor["toad"],
                embedded_brand=brand_id,
            )
            print(f"[PASS] {brand_id} {platform}: ok={res.ok} "
                  f"version=v{getattr(res, 'version', '?')} feed={feed}")
        except Exception as ex:  # noqa: BLE001
            print(f"[FAIL] {brand_id} {platform}: {type(ex).__name__}: {ex}")
            failures += 1

    print("RESULT:", "ALL VERIFIED" if failures == 0 else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
