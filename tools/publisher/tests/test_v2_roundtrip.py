"""Task 7: full end-to-end round-trip on the v2 base (no version pins).

Locks the entire publisher<->verifier contract in one test, exercising every
leg the individual Task 2-6/T6b tests cover in isolation:

    build_release_seal + build_release_sad            (publisher, Task 2)
      -> anchor the digest seal on a REAL v2 hab       (publisher, Task 3)
      -> export_kel  (genusified CESR stream)          (publisher, T6b)
      -> replay_kel  (verifier ingests the v2 KEL)     (verifier,  Task 5/6)
      -> extract_release_seal  ({d,brand,ver})         (verifier,  Task 5)
      -> resolve the SAD from a built appcast          (both,      Task 4)
      -> _verify_sad_against_anchor (saidify + bind)   (verifier,  Task 6)

The whole chain runs on the v2 default (the hab is v2 with NO version pin) and
proves the SAID-native seal serializes, anchors, exports, replays, and verifies
without any v1 hold on the publisher side.  A real ephemeral hab is used
(``temp=True``, ``toad=0`` — no witnesses / no live infra), mirroring
tests/test_publish_export.py.
"""
import hashlib

from keri.app import habbing

from locksmith_publisher.seal import build_release_seal, build_release_sad
from locksmith_publisher.appcast import build_appcast
from locksmith.update.kel_replay import replay_kel, extract_release_seal
from locksmith.update.appcast import parse_appcast
from locksmith.update.verify import _verify_sad_against_anchor


# A 21-character bran (Habery minimum).
_BRAN = "0123456789abcdefghijk"
_VERSION = "0.2.20"
_BRAND = "locksmith"


def test_v2_roundtrip(tmp_path):
    from locksmith_publisher.publish import export_kel

    macos_bytes = b"macos-artifact-bytes"
    artifact = tmp_path / "Locksmith.dmg"
    artifact.write_bytes(macos_bytes)
    expected_sha = hashlib.sha256(macos_bytes).hexdigest()

    seal = build_release_seal(version=_VERSION, brand=_BRAND,
                              artifacts=[("macos", artifact)])
    sad = build_release_sad(version=_VERSION, brand=_BRAND,
                            artifacts=[("macos", artifact)])
    # The digest seal references the SAD by its SAID.
    assert seal["d"] == sad["d"]
    assert seal == {"d": sad["d"], "brand": _BRAND, "ver": _VERSION}

    # --- publisher: anchor the digest seal on a REAL v2 hab, export the KEL ---
    with habbing.openHby(name="v2-roundtrip", temp=True, bran=_BRAN) as hby:
        hab = hby.makeHab("pub", icount=1, ncount=1, wits=[], toad=0)  # v2, no pin
        hab.interact(data=[seal])  # v2 ixn carrying the digest seal — must not error
        publisher_aid = hab.pre

        kel_bytes, anchor = export_kel(hby, hab, version=_VERSION, brand=_BRAND)
        assert anchor is not None, "export_kel must find the anchoring ixn"
        assert kel_bytes[:2] == b"-_", "export must be genusified (leading '-_' code)"

        # --- verifier: replay the v2 KEL and pull the digest seal back out ---
        state = replay_kel(
            kel_stream=kel_bytes,
            publisher_aid=publisher_aid,
            embedded_sn=anchor["sn"],
            embedded_said=anchor["said"],
            toad=0,
        )

    extracted = extract_release_seal(state, anchor_said=anchor["said"])
    assert extracted == seal, (
        f"seal read from the replayed KEL must equal the anchored seal; "
        f"got {extracted}, expected {seal}"
    )

    # --- resolve the SAD from a built appcast (the verifier's real source) ---
    raw = build_appcast(
        publisher_aid=publisher_aid,
        publisher_kel_url="https://releases.example.com/kel.cesr",
        releases=[{
            "version": _VERSION,
            "platform": "macos",
            "artifact_url": "https://releases.example.com/Locksmith.dmg",
            "artifact_sha256": expected_sha,
            "artifact_size": len(macos_bytes),
            "anchor_url": "https://releases.example.com/anchor.cesr",
            "anchor_said": extracted["d"],
            "released_at": "2026-07-09T00:00:00+00:00",
            "release_sad": sad,
        }],
    )
    appcast = parse_appcast(raw)
    resolved_sad = appcast.releases[0].release_sad
    assert resolved_sad == sad, "appcast must carry the SAD intact"

    # --- verifier: saidify(SAD) == seal.d, and bind the per-platform sha256 ---
    sha = _verify_sad_against_anchor(resolved_sad, anchor_d=extracted["d"],
                                     platform="macos")
    assert sha == expected_sha, (
        f"bound sha256 must match the artifact digest; got {sha}"
    )
