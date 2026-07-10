"""Task 4 tests: build_appcast embeds release_sad per release entry.
Plus T9(a): generate_and_upload_appcasts must FAIL LOUD, never silently drop an
anchored version from the regenerated appcast."""
import json

import pytest
from keri.app import habbing

from locksmith_publisher.appcast import build_appcast, generate_and_upload_appcasts, GeneratorConfig


def test_build_appcast_embeds_release_sad():
    from locksmith_publisher.appcast import build_appcast
    sad = {"d": "E" + "A"*43, "brand": "locksmith", "ver": "0.2.20",
           "artifacts": [{"platform": "macos", "sha256": "a"*64}]}
    ac = build_appcast(
        publisher_aid="Epub", publisher_kel_url="https://x/kel.cesr",
        releases=[{"version": "0.2.20", "platform": "macos",
                   "artifact_url": "u", "artifact_sha256": "a"*64, "artifact_size": 1,
                   "anchor_said": sad["d"], "anchor_url": "au",
                   "released_at": "2026-07-09T00:00:00+00:00",
                   "minimum_system_version": "12.0", "release_notes_url": "rn",
                   "is_major": False, "is_critical": False,
                   "release_sad": sad}])
    import json
    doc = json.loads(ac)
    assert doc["releases"][0]["release_sad"] == sad


def _new_shape_anchor_bytes():
    """Real v2 ixn carrying a NEW-shape digest seal; return its bare event bytes."""
    seal = {"d": "E" + "A" * 43, "brand": "locksmith", "ver": "0.2.20"}
    with habbing.openHby(name="regen-faillow", temp=True, bran="0123456789abcdefghijk") as hby:
        hab = hby.makeHab("h", icount=1, ncount=1, wits=[], toad=0)
        hab.interact(data=[seal])
        serder, _, _ = hab.getOwnEvent(sn=1)
        return bytes(serder.raw)


class _FakeS3:
    """Minimal S3 for generate_and_upload_appcasts: one anchored version, NO meta."""
    def __init__(self, anchor_bytes):
        self._anchor = anchor_bytes
        self.puts = []

    def list_release_versions(self, *, bucket, prefix="releases"):
        return ["0.2.20"]

    def get_object(self, *, Bucket, Key):  # noqa: N803 (boto3-style)
        if Key.endswith("release-anchor-0.2.20.cesr"):
            return self._anchor
        raise Exception("NoSuchKey")  # the companion meta.json is absent

    def put_object(self, *, Bucket, Key, Body, ContentType):  # noqa: N803
        self.puts.append(Key)


def test_generate_and_upload_appcasts_fails_loud_when_meta_missing():
    """A digest-seal (new-shape) anchor with no companion meta on S3 must make the
    regen RAISE — never silently drop the anchored version (omission/downgrade risk)
    — and must upload NOTHING."""
    s3 = _FakeS3(_new_shape_anchor_bytes())
    cfg = GeneratorConfig(
        bucket="b", publisher_aid="Epub", publisher_kel_url="https://x/kel.cesr",
        releases_cdn_base="https://cdn", channel="stable", release_prefix="releases",
        release_notes_base="https://site", brand_title="Locksmith",
        appcast_prefix="appcast", brand_id="locksmith")

    with pytest.raises(RuntimeError, match="meta|companion|diverged"):
        generate_and_upload_appcasts(s3=s3, config=cfg)
    assert s3.puts == [], "must not upload any appcast object when a version would be dropped"
