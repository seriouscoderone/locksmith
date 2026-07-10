"""Task 4 tests: build_appcast embeds release_sad per release entry."""
import json

from locksmith_publisher.appcast import build_appcast


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
