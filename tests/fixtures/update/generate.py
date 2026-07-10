"""Generate KERI fixtures for the update verifier test suite.

Architecture: single-signer publisher AID (kt=1, nt=1) witnessed by 3
non-transferable witnesses with toad=3. Matches Phase 1's production
publisher topology (5 witnesses there, 3 here to keep fixtures small;
verifier code is parameterized on the witness count).

Usage::

    python tests/fixtures/update/generate.py [--out DIR]

Idempotent: deletes and re-creates the output directory on each run.
Uses keripy directly so fixtures are real KERI events.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import uuid
from pathlib import Path

from keri.app import habbing
from keri.core import eventing, indexing, serdering
from keri.core.coring import Saider
from keri.core.counting import Vrsn_1_0
from keri.db import dbing


DEFAULT_OUT = Path(__file__).parent


def _new_unique_suffix() -> str:
    """Per-invocation suffix so re-running into existing keystores doesn't collide."""
    return uuid.uuid4().hex[:8]


def make_witnesses(suffix: str, count: int = 3) -> tuple[list[habbing.Hab], list[habbing.Habery], list[bytes]]:
    """Spin up `count` non-transferable witness Habs.

    Returns (hab_list, habery_list, kel_stream_list).
    The KEL stream for each witness is its serialized inception event ready
    to feed into a verifier's parser.
    """
    habs: list[habbing.Hab] = []
    hbys: list[habbing.Habery] = []
    streams: list[bytes] = []
    for i in range(count):
        # version=Vrsn_1_0 forces KERI10JSON... format so replay_kel (which
        # uses Parser(version=Vrsn_1_0)) can parse the fixture.
        hby = habbing.Habery(name=f"fixture_w{i}_{suffix}", base="", temp=True,
                             version=Vrsn_1_0)
        wh = hby.makeHab(name=f"witness{i}", transferable=False, isith="1", icount=1,
                         version=Vrsn_1_0)
        hbys.append(hby)
        habs.append(wh)
        stream = b"".join(bytes(e) for e in wh.db.clonePreIter(pre=wh.pre, fn=0))
        streams.append(stream)
    return habs, hbys, streams


def make_publisher(
    suffix: str,
    witness_prefixes: list[str],
    toad: int,
) -> tuple[habbing.Hab, habbing.Habery]:
    """Build the single-signer publisher AID witnessed by `witness_prefixes`.

    kt=1, nt=1, icount=1, ncount=1. Per Phase 4 user deviation #1.
    """
    hby = habbing.Habery(name=f"fixture_pub_{suffix}", base="", temp=True,
                         version=Vrsn_1_0)
    hab = hby.makeHab(
        name="publisher",
        transferable=True,
        isith="1",
        icount=1,
        nsith="1",
        ncount=1,
        wits=witness_prefixes,
        toad=toad,
        version=Vrsn_1_0,
    )
    return hab, hby


def attach_wigs(pub: habbing.Hab, witnesses: list[habbing.Hab], serder: serdering.SerderKERI) -> None:
    """Generate witness wigs for `serder` and persist them in `pub.db.wigs`.

    Each witness signs `serder.raw` (non-indexed cigar), and the resulting
    signature is re-wrapped as an indexed Siger (index = position in the
    publisher's wits list). The Parser's wig pipeline reconstitutes these
    indexed sigs against the publisher event's bound witnesses.

    NOTE: This is a FIXTURE GENERATOR, not a runtime/test helper. It is kept
    deliberately even though the bespoke KERI-event/receipt pipeline was
    retired in favor of the kli pipeline: the verifier unit tests in
    ``tests/unit/update/`` consume the COMMITTED fixtures this script emits
    (``anchor/``, ``kel/``, ``tampered/``, ``publisher_aid.json``), and those
    fixtures can only be regenerated (``python generate.py``) if ``attach_wigs``
    remains. The masking *test* (``tests/unit/publisher/test_round_trip_verify``)
    that faked receipts via ``db.wigs.put`` at TEST TIME was removed; the live
    round-trip is now pinned end-to-end by
    ``tests/integration/test_publisher_roundtrip.py`` against a real witness with
    real receipts. Regenerating fixtures here stays offline by construction.
    """
    dgkey = dbing.dgKey(pub.pre.encode(), serder.said.encode())
    wigers = []
    for idx, wh in enumerate(witnesses):
        cigars = wh.sign(ser=serder.raw, indexed=False)
        cig = cigars[0]
        siger = indexing.Siger(raw=cig.raw, code=indexing.IdrDex.Ed25519_Sig, index=idx)
        siger.verfer = cig.verfer
        wigers.append(siger)
    pub.db.wigs.put(keys=dgkey, vals=wigers)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_stub_artifact(out: Path, version: str, platform: str) -> tuple[Path, str]:
    """Write a small deterministic binary stub and return (path, sha256)."""
    ext = "dmg" if platform == "macos" else "msi"
    body = f"LOCKSMITH-STUB platform={platform} version={version}\n".encode()
    path = out / "artifacts" / f"Locksmith-{version}.{ext}.stub"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path, sha256(body)


def build_release_sad_and_seal(
    *,
    version: str,
    brand: str = "locksmith",
    artifacts: list[dict],
) -> tuple[dict, dict]:
    """Build the saidified release SAD and the corresponding digest seal.

    The release SAD shape is ``{"d", "brand", "ver", "artifacts": [{platform, sha256}]}``.
    It is saidified so that ``sad["d"]`` is the SAID of the SAD itself.

    The digest seal is ``{"d": sad["d"], "brand": ..., "ver": ...}`` — this is
    what gets anchored in the publisher's ixn event (Task 2 / Task 5 contract).

    Returns (release_sad, digest_seal).
    """
    sad_template = {
        "d": "",
        "brand": brand,
        "ver": version,
        "artifacts": [{"platform": a["platform"], "sha256": a["sha256"]}
                      for a in artifacts],
    }
    _, release_sad = Saider.saidify(sad=sad_template)
    digest_seal = {"d": release_sad["d"], "brand": brand, "ver": version}
    return release_sad, digest_seal


def anchor_release(pub: habbing.Hab, witnesses: list[habbing.Hab], seal: dict) -> serdering.SerderKERI:
    """Append an ixn event anchoring `seal`, attach witness wigs."""
    # Vrsn_1_0 + gvrsn=Vrsn_1_0 forces KERI10JSON... format so Parser(version=Vrsn_1_0)
    # in replay_kel can consume the event.
    msg = pub.interact(data=[seal], version=Vrsn_1_0, gvrsn=Vrsn_1_0)
    serder = serdering.SerderKERI(raw=bytearray(msg))
    attach_wigs(pub, witnesses, serder)
    return serder


def single_event_bytes(pub: habbing.Hab, sn: int) -> bytes:
    """Clone exactly one event (by fn index) from the publisher's KEL."""
    events = list(pub.db.clonePreIter(pre=pub.pre, fn=sn))
    if not events:
        raise RuntimeError(f"no event at fn={sn}")
    return bytes(events[0])


def generate_happy_path(out: Path) -> dict:
    """Emit publisher_aid.json, kel/, anchor/, artifacts/, appcast/.

    Returns the metadata manifest (also written to publisher_aid.json).
    """
    suffix = _new_unique_suffix()
    wit_habs, wit_hbys, wit_streams = make_witnesses(suffix, count=3)
    wit_prefixes = [w.pre for w in wit_habs]

    pub, pub_hby = make_publisher(suffix, wit_prefixes, toad=3)

    # Wigs for the inception event.
    attach_wigs(pub, wit_habs, pub.kever.serder)
    inception_said = pub.kever.serder.said

    # Three release anchors.
    versions = [
        ("1.0.0", False, False, None),
        ("1.0.1", False, False, "1.0.0"),
        ("1.1.0", True, False, "1.0.1"),
    ]

    anchor_dir = out / "anchor"
    anchor_dir.mkdir(parents=True, exist_ok=True)
    kel_dir = out / "kel"
    kel_dir.mkdir(parents=True, exist_ok=True)

    release_records: list[dict] = []
    sn = 1  # icp is sn 0
    for (v, is_major, is_critical, prev) in versions:
        mac_path, mac_sha = make_stub_artifact(out, v, "macos")
        win_path, win_sha = make_stub_artifact(out, v, "windows")
        # Per-seal artifact list: only platform + sha256 (no filenames — those
        # live in the appcast, not the KERI-anchored SAD).
        artifacts_for_sad = [
            {"platform": "macos", "sha256": mac_sha},
            {"platform": "windows", "sha256": win_sha},
        ]
        release_sad, digest_seal = build_release_sad_and_seal(
            version=v, artifacts=artifacts_for_sad,
        )
        serder = anchor_release(pub, wit_habs, digest_seal)

        # Persist this event's bytes (single-event CESR) to anchor/.
        evt_bytes = single_event_bytes(pub, sn=sn)
        (anchor_dir / f"{v}.cesr").write_bytes(evt_bytes)

        # Write the companion metadata JSON so generate_and_upload_appcasts can
        # look up full artifact details (filename, size, min_sys_ver, etc.) that
        # the digest seal no longer embeds.  The key mirrors what the publisher
        # CLI uploads alongside the anchor CESR in S3.
        anchor_meta = {
            "release_sad": release_sad,
            "artifacts": [
                {"platform": "macos", "filename": mac_path.name,
                 "sha256": mac_sha, "size": mac_path.stat().st_size},
                {"platform": "windows", "filename": win_path.name,
                 "sha256": win_sha, "size": win_path.stat().st_size},
            ],
            "released_at": "2026-05-28T00:00:00Z",
            "minimum_system_versions": {"macos": "13.0", "windows": "10.0.19041"},
            "is_major": is_major,
            "is_critical": is_critical,
        }
        # Key mirrors: releases/{v}/release-anchor-{v}-meta.json in S3.
        (anchor_dir / f"{v}-meta.json").write_text(
            json.dumps(anchor_meta, indent=2) + "\n"
        )

        release_records.append({
            "version": v,
            "sn": sn,
            "said": serder.said,
            "release_sad": release_sad,
            "artifacts": {
                "macos": {"path": str(mac_path), "sha256": mac_sha,
                          "size": mac_path.stat().st_size, "filename": mac_path.name},
                "windows": {"path": str(win_path), "sha256": win_sha,
                            "size": win_path.stat().st_size, "filename": win_path.name},
            },
            "released_at": "2026-05-28T00:00:00Z",
            "is_major": is_major,
            "is_critical": is_critical,
        })
        sn += 1

    # Full KEL stream: 3 witness inceptions + publisher inception + 3 release ixn.
    full_kel = b"".join(wit_streams)
    full_kel += b"".join(bytes(e) for e in pub.db.clonePreIter(pre=pub.pre, fn=0))
    (kel_dir / "publisher.cesr").write_bytes(full_kel)

    manifest = {
        "publisher_aid": pub.pre,
        "embedded_kel_hash": inception_said,
        "embedded_kel_sn": 0,
        "embedded_kel_said_at_tip": pub.kever.serder.said,
        "kel_tip_sn": pub.kever.sner.num,
        "witness_aids": wit_prefixes,
        "witness_oobis": [f"https://witness.fixture.local/oobi/{w}/witness" for w in wit_prefixes],
        "toad": 3,
        "_releases": release_records,
    }
    (out / "publisher_aid.json").write_text(json.dumps(manifest, indent=2) + "\n")

    write_appcasts(out, pub.pre, release_records)

    # Clean up Haberies. Important: close in reverse order to avoid LMDB conflicts.
    pub_hby.close()
    for hby in wit_hbys:
        hby.close()

    return manifest


def write_appcasts(out: Path, publisher_aid: str, releases: list[dict]) -> None:
    """Emit per-platform appcast JSON.

    Each release entry embeds the saidified ``release_sad`` (computed during
    fixture generation) whose ``d`` field equals the digest seal anchored in the
    KEL ixn event.  The appcast ``artifact_sha256`` must equal the per-platform
    sha256 found inside that SAD (downgrade-cross-check in the verifier).
    """
    appcast_dir = out / "appcast"
    appcast_dir.mkdir(parents=True, exist_ok=True)
    for platform, ext in [("macos", "dmg"), ("windows", "msi")]:
        current = releases[-1]["version"]
        rels: list[dict] = []
        for r in releases:
            a = r["artifacts"][platform]
            # The release SAD was already saidified during KEL construction;
            # it contains entries for ALL platforms so the verifier can find
            # the right one by platform name.
            release_sad = r["release_sad"]
            rels.append({
                "version": r["version"],
                "released_at": r["released_at"],
                "platform": platform,
                "minimum_system_version": "13.0" if platform == "macos" else "10.0.19041",
                "artifact_url":
                    f"https://releases.keri.host/releases/{r['version']}/{a['filename']}",
                "artifact_sha256": a["sha256"],
                "artifact_size": a["size"],
                "anchor_url":
                    f"https://releases.keri.host/releases/{r['version']}/release-anchor-{r['version']}.cesr",
                "anchor_said": r["said"],
                "release_notes_url": f"https://locksmith.app/releases/{r['version']}",
                "is_major": r["is_major"],
                "is_critical": r["is_critical"],
                "release_sad": release_sad,
            })
        appcast = {
            "schema_version": 1,
            "channel": "stable",
            "publisher_aid": publisher_aid,
            "publisher_kel_url":
                "https://releases.keri.host/publisher/v1/publisher-kel.cesr",
            "current_version": current,
            "releases": rels,
        }
        (appcast_dir / f"{platform}.json").write_text(
            json.dumps(appcast, indent=2) + "\n"
        )


def generate_tampered_variants(out: Path, manifest: dict) -> None:
    """Emit the tampered/ directory with adversarial cases."""
    tampered = out / "tampered"
    tampered.mkdir(parents=True, exist_ok=True)

    rel_101 = next(r for r in manifest["_releases"] if r["version"] == "1.0.1")
    rel_110 = next(r for r in manifest["_releases"] if r["version"] == "1.1.0")

    # (A) Tampered binary — same filename pattern, different bytes.
    (tampered / "tampered_binary_1.0.1.dmg.stub").write_bytes(b"MALICIOUS PAYLOAD\n")

    # (B) Tampered anchor event — flip a payload byte in the body.
    real_event = (out / "anchor" / "1.0.1.cesr").read_bytes()
    mutated = bytearray(real_event)
    # Flip a printable ASCII letter in the JSON body (skip the version-string prefix).
    for i in range(40, min(len(mutated), 300)):
        if 0x41 <= mutated[i] <= 0x7A:
            mutated[i] ^= 0x01
            break
    (tampered / "tampered_event_1.0.1.cesr").write_bytes(bytes(mutated))

    # (C) Insufficient receipts — strip the WitnessIdxSigs group from the bytes.
    # The CESR attachment for indexed witness sigs starts with the counter "-B"
    # (V1 WitnessIdxSigs code). We truncate the event right before that marker
    # if present; otherwise we keep only ~50% of the bytes after the JSON body.
    json_end = real_event.find(b"}-")  # } end of JSON + start of attachment counter
    if json_end == -1:
        truncated = real_event[: len(real_event) // 2]
    else:
        # Keep the JSON + ControllerIdxSigs (-A) + first sig only, drop WitnessIdxSigs.
        wig_marker = real_event.find(b"-B", json_end)
        if wig_marker > 0:
            truncated = real_event[:wig_marker]
        else:
            truncated = real_event[: json_end + 50]
    (tampered / "insufficient_receipts_1.0.1.cesr").write_bytes(truncated)

    # (D) Stale appcast — claims current_version=1.0.0 even though KEL is at 1.1.0.
    macos = json.loads((out / "appcast" / "macos.json").read_text())
    stale = dict(macos)
    stale["current_version"] = "1.0.0"
    stale["releases"] = [r for r in macos["releases"] if r["version"] == "1.0.0"]
    (tampered / "stale_appcast_macos.json").write_text(json.dumps(stale, indent=2) + "\n")

    # (E) Downgrade — claims 1.0.0 has 1.1.0's sha (serve old artifact as new).
    downgrade = json.loads((out / "appcast" / "macos.json").read_text())
    for r in downgrade["releases"]:
        if r["version"] == "1.0.0":
            r["artifact_sha256"] = rel_110["artifacts"]["macos"]["sha256"]
    (tampered / "downgrade_appcast_macos.json").write_text(
        json.dumps(downgrade, indent=2) + "\n"
    )

    # (F) Bad rotation — copy icp bytes but flip ilk "icp" -> "rot".
    full_kel = (out / "kel" / "publisher.cesr").read_bytes()
    # Find publisher icp (after witness icps); use embedded_kel_hash to locate.
    # Simpler: find `"t":"icp","d":"<embedded_kel_hash>"` in the stream.
    needle = f'"t":"icp","d":"{manifest["embedded_kel_hash"]}"'.encode()
    idx = full_kel.find(needle)
    if idx >= 0:
        # Extract from start-of-JSON to end of single event (find next message boundary).
        # Crude: take 800 bytes from the start of the version string before idx.
        start = full_kel.rfind(b'{"v":"KERI', 0, idx)
        end = full_kel.find(b'{"v":"KERI', idx + len(needle))
        if start < 0:
            start = idx - 50
        if end < 0:
            end = min(len(full_kel), idx + 1000)
        chunk = bytearray(full_kel[start:end])
        chunk = bytes(chunk).replace(b'"t":"icp"', b'"t":"rot"', 1)
        (tampered / "bad_rotation.cesr").write_bytes(chunk)
    else:
        # Fall back: just mutate the standalone anchor file.
        (tampered / "bad_rotation.cesr").write_bytes(
            (out / "anchor" / "1.0.0.cesr").read_bytes().replace(b'"t":"ixn"', b'"t":"rot"', 1)
        )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    # Idempotent: wipe everything except this script and README.
    keep = {"generate.py", "README.md", "__init__.py"}
    for entry in args.out.iterdir():
        if entry.name in keep:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    manifest = generate_happy_path(args.out)
    generate_tampered_variants(args.out, manifest)
    print(f"Fixtures written to {args.out}")
    print(f"  publisher AID: {manifest['publisher_aid']}")
    print(f"  KEL tip sn: {manifest['kel_tip_sn']}")
    print(f"  releases: {[r['version'] for r in manifest['_releases']]}")


if __name__ == "__main__":
    main()
