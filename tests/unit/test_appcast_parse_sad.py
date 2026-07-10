"""Task 4 verifier-side test: parse_appcast carries release_sad through to Release."""
import json
from locksmith.update.appcast import parse_appcast


def _appcast_with_sad(sad):
    return json.dumps({
        "schema_version": 1, "channel": "stable",
        "publisher_aid": "Epub", "publisher_kel_url": "https://x/kel.cesr",
        "current_version": "0.2.20",
        "releases": [{
            "version": "0.2.20", "released_at": "2026-07-09T00:00:00+00:00",
            "platform": "macos", "minimum_system_version": "12.0",
            "artifact_url": "u", "artifact_sha256": "a"*64, "artifact_size": 1,
            "anchor_url": "au", "anchor_said": sad["d"],
            "release_notes_url": "rn", "is_major": False, "is_critical": False,
            "release_sad": sad}]})


def test_parse_appcast_carries_release_sad():
    sad = {"d": "E"+"A"*43, "brand": "locksmith", "ver": "0.2.20",
           "artifacts": [{"platform": "macos", "sha256": "a"*64}]}
    ac = parse_appcast(_appcast_with_sad(sad))
    assert ac.releases[0].release_sad == sad
