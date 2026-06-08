"""Round-trip integration: publisher anchors a release → verifier accepts it.

Boots a single-sig publisher Hab + 3 witnesses, builds a real release ixn
via ``build_release_anchor``, attaches witness wigs, and feeds the whole
KEL through ``locksmith.update.verify.verify_artifact()`` (with the
network seam patched). End-to-end: same artifact bytes the publisher
hashed must verify.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from locksmith_publisher.appcast import (
    GeneratorConfig,
    generate_and_upload_appcasts,
)
from locksmith_publisher.release_anchor import (
    ArtifactInput,
    ReleaseAnchorRequest,
    build_release_anchor,
)


def _build_witnesses(suffix: str):
    from keri.app import habbing
    hbys, habs = [], []
    for i in range(3):
        hby = habbing.Habery(name=f"rt_w{i}_{suffix}", base="", temp=True)
        h = hby.makeHab(name=f"w{i}", transferable=False, isith="1", icount=1)
        hbys.append(hby)
        habs.append(h)
    return hbys, habs


def _attach_wigs(pub, witnesses, serder):
    from keri.core import indexing
    from keri.db import dbing
    dgkey = dbing.dgKey(pub.pre.encode(), serder.said.encode())
    wigers = []
    for idx, wh in enumerate(witnesses):
        cigars = wh.sign(ser=serder.raw, indexed=False)
        siger = indexing.Siger(
            raw=cigars[0].raw, code=indexing.IdrDex.Ed25519_Sig, index=idx
        )
        siger.verfer = cigars[0].verfer
        wigers.append(siger)
    pub.db.wigs.put(keys=dgkey, vals=wigers)


def test_publisher_to_verifier_round_trip(tmp_path):
    """End-to-end: real publisher signs a release; real verifier accepts it."""
    from keri.app import habbing
    from unittest.mock import MagicMock

    suffix = uuid.uuid4().hex[:8]
    wit_hbys, wit_habs = _build_witnesses(suffix)
    wit_prefixes = [w.pre for w in wit_habs]

    pub_hby = habbing.Habery(name=f"rt_pub_{suffix}", base="", temp=True)
    pub = pub_hby.makeHab(
        name="publisher",
        transferable=True,
        isith="1",
        icount=1,
        nsith="1",
        ncount=1,
        wits=wit_prefixes,
        toad=3,
    )
    # Attach wigs to the inception event so the verifier sees toad met.
    _attach_wigs(pub, wit_habs, pub.kever.serder)
    inception_said = pub.kever.serder.said

    # Build a real artifact.
    mac = tmp_path / "Locksmith-2.0.0.dmg"
    mac.write_bytes(b"BINARY_BYTES_FOR_ROUND_TRIP_TEST")
    win = tmp_path / "Locksmith-2.0.0.msi"
    win.write_bytes(b"WINDOWS_BYTES_FOR_ROUND_TRIP_TEST")

    request = ReleaseAnchorRequest(
        version="2.0.0",
        channel="stable",
        released_at="2026-06-01T00:00:00Z",
        is_major=True,
        is_critical=False,
        previous_version=None,
        minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
        artifacts=(
            ArtifactInput.from_path(platform="macos", path=mac),
            ArtifactInput.from_path(platform="windows", path=win),
        ),
        release_notes_said="EHshRoundTripTestSAIDPlaceholderXXXXXXXXXXXX",
    )

    # Build the release-anchor ixn event via the publisher pipeline.
    anchor = build_release_anchor(hab=pub, request=request)
    _attach_wigs(pub, wit_habs, anchor.serder)

    # Build the appcast via the same generator the operator would invoke.
    # Provide a fake S3 with our anchor and witness/publisher streams.
    real_event_bytes = next(
        bytes(e) for i, e in enumerate(pub.db.clonePreIter(pre=pub.pre, fn=0))
        if i == 1  # sn 1 is the release ixn
    )

    s3_fake = MagicMock()
    s3_fake.list_release_versions.return_value = ["2.0.0"]
    s3_fake.get_object.return_value = real_event_bytes
    captured: dict[str, bytes] = {}
    s3_fake.put_object.side_effect = (
        lambda Bucket, Key, Body, **kw: captured.update({Key: Body})
    )

    cfg = GeneratorConfig(
        bucket="releases.keri.host",
        publisher_aid=pub.pre,
        publisher_kel_url="https://releases.keri.host/publisher/v1/publisher-kel.cesr",
    )
    generate_and_upload_appcasts(s3=s3_fake, config=cfg)

    # Full KEL stream: witness icps + publisher icp + release ixn.
    wit_streams = []
    for wh in wit_habs:
        wit_streams.append(b"".join(bytes(e) for e in wh.db.clonePreIter(pre=wh.pre, fn=0)))
    pub_stream = b"".join(bytes(e) for e in pub.db.clonePreIter(pre=pub.pre, fn=0))
    full_kel = b"".join(wit_streams) + pub_stream

    # Run the verifier on the macOS artifact.
    from locksmith.update import verify as verify_mod
    from locksmith.update.verify import verify_artifact

    appcast_raw = captured["appcast/v1/macos.json"]

    def fake_fetch(url: str) -> bytes:
        if "publisher" in url or "kel" in url:
            return full_kel
        return real_event_bytes

    with patch.object(verify_mod, "_fetch_url", side_effect=fake_fetch):
        result = verify_artifact(
            artifact_path=mac,
            appcast_raw=appcast_raw,
            platform="macos",
            embedded_publisher_aid=pub.pre,
            embedded_kel_sn=0,
            embedded_kel_said=inception_said,
            toad=3,
        )

    assert result.ok is True
    assert result.version == "2.0.0"
    assert result.publisher_aid == pub.pre
    assert result.anchor_said == anchor.said
    assert result.witness_receipts >= 3

    # Cleanup.
    pub_hby.close()
    for h in wit_hbys:
        h.close()
