#!/usr/bin/env python3
"""Re-bake a brand's bundled authority OOBI from a wallet export.

``brands/<brand>/egf/oobis/<aid>.cesr`` is the artifact every install pairs
the ecosystem authority from. Inside it is a ``/loc/scheme`` rpy **signed by
the authority's own AID** carrying the tcp address peers dial. That signature
is why the file cannot be corrected by hand: change one byte of the URL and
``parse_oobi_cesr`` rejects the whole blob. The endpoint can only be changed
by re-publishing the rpy from the authority's vault and re-exporting.

Producing the input (on the authority's machine, in the authority's vault):

  1. Vault → Settings → Direct peer connections. Set **Advertise as** to an
     address the other machines can actually reach (LAN IP, or the overlay
     address once Tailscale/WireGuard is up) and Save & restart. The
     reachability self-test under the button must come back green.
  2. Identifiers → the authority AID → toggle **Expose over peer mode** on
     (this republishes /end/role/add + /loc/scheme with the new address).
  3. Same page, OOBI role dropdown → **Peer (offline)** → copy the
     ``locksmith-peer-oobi:v1:…`` token.

Then, in this repo:

    python scripts/bake_authority_oobi.py --brand usurance \\
        --aid EGjm-X1JMz-yKFeumEZ9meSVNvnV8VTXmjJMlyBVMMTO --stdin

    python scripts/bake_authority_oobi.py --brand usurance --aid E… \\
        --inspect-only --stdin     # print the endpoint, write nothing

The script re-parses the export into a throwaway Habery, so a blob whose
signatures do not verify never reaches the brand directory. It refuses to
write a loopback or wildcard endpoint — that bad bake is the whole reason
this exists (backlog/2026-07-28-hoa-direct-endpoint-loopback-only.md), and
``tests/core/test_brand_oobi_endpoints.py`` is the committed guard.
"""
from __future__ import annotations

import argparse
import base64
import ipaddress
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

BLOB_PREFIX = "locksmith-peer-oobi:v1:"


class BakeError(Exception):
    """Refusal to write an artifact — the message is user-facing."""


def decode_input(text: str) -> bytes:
    """Accept either a wallet blob token or a raw CESR stream."""
    text = text.strip()
    if text.startswith(BLOB_PREFIX):
        try:
            return base64.b64decode(text[len(BLOB_PREFIX):], validate=True)
        except (ValueError, base64.binascii.Error) as e:
            raise BakeError(f"couldn't base64-decode the blob token: {e}")
    return text.encode("utf-8")


def _is_routable(host: str) -> bool:
    if not host or host.lower() in ("localhost", "localhost.localdomain", "*"):
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return True          # a DNS name — can't judge here, allow it
    return not (addr.is_loopback or addr.is_unspecified)


def inspect(cesr: bytes, aid: str) -> str:
    """Verify the export and return the tcp endpoint it carries for `aid`.

    Parses into a temp Habery via the same code path the wallet uses, so a
    tampered or unsigned blob fails here rather than in the field.
    """
    from keri import kering
    from keri.app import habbing
    from locksmith.peer.cesr_blob import PeerBlobError
    from locksmith.peer.oobi_import import parse_oobi_cesr

    with habbing.openHby(name="bake-verify", temp=True) as hby:
        try:
            parse_oobi_cesr(hby, cesr)
        except PeerBlobError as e:
            raise BakeError(f"the export did not verify: {e}")
        loc = hby.db.locs.get(keys=(aid, kering.Schemes.tcp))
        if loc is None or not loc.url:
            raise BakeError(
                f"the export does not carry a tcp peer endpoint for {aid} — "
                f"expected the authority AID pinned by the brand's EGF. Check "
                f"you exported from the right identifier, with 'Expose over "
                f"peer mode' on.")
        return loc.url


def bake(cesr: bytes, aid: str, out_dir: Path) -> Path:
    """Validate `cesr` and write it to ``<out_dir>/<aid>.cesr``."""
    url = inspect(cesr, aid)
    host = urlparse(url).hostname or ""
    if not _is_routable(host):
        raise BakeError(
            f"refusing to bake {url!r}: {host} is not reachable from another "
            f"machine. Set 'Advertise as' in the authority wallet's peer "
            f"settings to a routable address and re-export.")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{aid}.cesr"
    out.write_bytes(cesr)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--brand", required=True, help="brand id under brands/")
    ap.add_argument("--aid", required=True, help="authority AID pinned by the EGF")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--stdin", action="store_true", help="read the export from stdin")
    src.add_argument("--file", type=Path, help="read the export from a file")
    ap.add_argument("--inspect-only", action="store_true",
                    help="print the endpoint the export carries; write nothing")
    args = ap.parse_args(argv)

    text = sys.stdin.read() if args.stdin else args.file.read_text(encoding="utf-8")
    try:
        cesr = decode_input(text)
        url = inspect(cesr, args.aid)
        if args.inspect_only:
            print(url)
            return 0
        out = bake(cesr, args.aid,
                   REPO / "brands" / args.brand / "egf" / "oobis")
    except BakeError as e:
        print(f"bake_authority_oobi: {e}", file=sys.stderr)
        return 2
    print(f"wrote {out.relative_to(REPO)} ({url})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
