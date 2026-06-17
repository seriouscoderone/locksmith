"""Round-trip test: build_appcast(...) emits exactly what the verifier's
parse_appcast(...) consumes (locksmith.update.appcast), and the selected
release carries the version/anchor_said/artifact_sha256 the updater reads.

Runs from tools/publisher/ — both locksmith_publisher (src on pythonpath)
and locksmith.update.appcast (main install) import here.
"""
from locksmith_publisher.appcast import build_appcast
from locksmith.update.appcast import parse_appcast, select_latest_for_platform


def test_build_appcast_roundtrips_through_verifier_parser():
    raw = build_appcast(
        publisher_aid="EPub",
        publisher_kel_url="https://releases.example.com/publisher/v1/kel.cesr",
        releases=[dict(version="0.2.0", anchor_said="EAnch", platform="macos",
                       anchor_url="https://releases.example.com/publisher/v1/anchors/EAnch.cesr",
                       artifact_sha256="ab" * 32,
                       artifact_url="https://releases.example.com/0.2.0/Locksmith-macos.dmg")],
    )
    ac = parse_appcast(raw)
    assert ac.publisher_aid == "EPub"
    assert ac.publisher_kel_url.endswith("/publisher/v1/kel.cesr")
    rel = select_latest_for_platform(ac, "macos")
    assert rel.version == "0.2.0" and rel.anchor_said == "EAnch"
    assert rel.artifact_sha256 == "ab" * 32
