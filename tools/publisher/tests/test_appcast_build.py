"""Round-trip test: build_appcast(...) emits exactly what the verifier's
parse_appcast(...) consumes (locksmith.update.appcast), and the selected
release carries the version/anchor_said/artifact_sha256 the updater reads.

Runs from tools/publisher/ — both locksmith_publisher (src on pythonpath)
and locksmith.update.appcast (main install) import here.
"""
import json

from locksmith_publisher import appcast as appcast_mod
from locksmith_publisher.appcast import (
    GeneratorConfig,
    build_appcast,
    generate_and_upload_appcasts,
)
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


class _FakeGenS3:
    """Fake for generate_and_upload_appcasts' s3 adapter interface.

    Mirrors the (bucket, prefix)-aware list + get/put_object contract the
    generator uses; captures every put so tests can assert the emitted JSON.
    """

    def __init__(self, versions):
        self._versions = versions
        self.seen_prefix = None
        self.puts = {}

    def list_release_versions(self, *, bucket, prefix="releases"):
        self.seen_prefix = prefix
        return list(self._versions)

    def get_object(self, *, Bucket, Key):  # noqa: N803 — boto3-style
        # Content is irrelevant: _parse_anchor is monkeypatched in the test.
        return b"anchor-cesr"

    def put_object(self, *, Bucket, Key, Body, ContentType):  # noqa: N803
        self.puts[Key] = Body


def _canned_anchor(v):
    """A parsed anchor (as _parse_anchor returns) with both platforms."""
    return {
        "said": f"EAnch{v}",
        "seal": {"release": {
            "released_at": "2026-07-01T00:00:00Z",
            "minimum_system_versions": {"macos": "12.0", "windows": "10.0.19041"},
            "artifacts": [
                {"platform": "macos", "filename": f"Usurance-{v}.dmg",
                 "sha256": "ab" * 32, "size": 111},
                {"platform": "windows", "filename": f"Usurance-{v}.msi",
                 "sha256": "cd" * 32, "size": 222},
            ],
        }},
    }


def test_appcast_urls_use_brand_prefix(monkeypatch):
    """The rebuild path threads release_prefix + release_notes_base into every
    per-release URL — the load-bearing behavior Task 5 adds. Defaults are the
    locksmith values, so a branded config must flip all three URL families."""
    monkeypatch.setattr(appcast_mod, "_parse_anchor", lambda raw: _canned_anchor("0.3.0"))
    s3 = _FakeGenS3(["0.3.0"])
    config = GeneratorConfig(
        bucket="b",
        publisher_aid="EPub",
        publisher_kel_url="https://usurance.com/publisher/v1/kel.cesr",
        releases_cdn_base="https://cdn.usurance.com",
        release_prefix="usurance/releases",
        release_notes_base="https://usurance.com",
        brand_title="Usurance",
        appcast_prefix="usurance/appcast",
    )
    generate_and_upload_appcasts(s3=s3, config=config)

    # enumeration used the branded prefix
    assert s3.seen_prefix == "usurance/releases"

    # the appcast itself lands under the brand's namespace — NOT the shared
    # appcast/v1/ key — so Usurance's app polls its own feed and does not
    # clobber Locksmith's.
    macos = json.loads(s3.puts["usurance/appcast/v1/macos.json"].decode())
    assert "appcast/v1/macos.json" not in s3.puts  # never the shared locksmith key
    rel = macos["releases"][0]
    assert rel["artifact_url"].endswith("/usurance/releases/0.3.0/Usurance-0.3.0.dmg")
    assert rel["anchor_url"].endswith("/usurance/releases/0.3.0/release-anchor-0.3.0.cesr")
    # website info URL keeps the literal /releases/ segment, brand host swapped
    assert rel["release_notes_url"] == "https://usurance.com/releases/0.3.0"

    # XML feed title comes from the brand name, not the AID
    macos_xml = s3.puts["usurance/appcast/v1/macos.xml"].decode()
    assert "Usurance" in macos_xml and "EPub" not in macos_xml
    # archive is namespaced too (history stays per-brand)
    assert any(k.startswith("usurance/appcast/archive/") for k in s3.puts)


def test_appcast_urls_default_to_locksmith(monkeypatch):
    """With no brand fields set, the rebuild path stays byte-identical: the
    default `releases/` prefix, locksmith.app notes host, and the AID title."""
    monkeypatch.setattr(appcast_mod, "_parse_anchor", lambda raw: _canned_anchor("0.3.0"))
    s3 = _FakeGenS3(["0.3.0"])
    config = GeneratorConfig(
        bucket="b",
        publisher_aid="EPub",
        publisher_kel_url="https://locksmith.app/publisher/v1/kel.cesr",
        releases_cdn_base="https://releases.keri.host",
    )
    generate_and_upload_appcasts(s3=s3, config=config)

    assert s3.seen_prefix == "releases"
    macos = json.loads(s3.puts["appcast/v1/macos.json"].decode())
    rel = macos["releases"][0]
    assert rel["artifact_url"].endswith("/releases/0.3.0/Usurance-0.3.0.dmg")
    assert rel["anchor_url"].endswith("/releases/0.3.0/release-anchor-0.3.0.cesr")
    assert rel["release_notes_url"] == "https://locksmith.app/releases/0.3.0"
    # title falls back to the publisher AID
    assert "EPub" in s3.puts["appcast/v1/macos.xml"].decode()
