import xml.etree.ElementTree as ET

from locksmith_publisher.appcast import build_appcast_xml

_SPARKLE = "http://www.andymatuschak.org/xml-namespaces/sparkle"


def test_xml_has_enclosure_with_version_and_length():
    xml = build_appcast_xml(
        title="Locksmith",
        releases=[{
            "version": "0.2.0",
            "artifact_url": "https://releases.keri.host/releases/0.2.0/Locksmith-0.2.0.dmg",
            "artifact_size": 62567411,
            "released_at": "",
        }],
    )
    root = ET.fromstring(xml)
    enc = root.find(".//item/enclosure")
    assert enc is not None
    assert enc.get("url") == "https://releases.keri.host/releases/0.2.0/Locksmith-0.2.0.dmg"
    assert enc.get("length") == "62567411"
    assert enc.get(f"{{{_SPARKLE}}}version") == "0.2.0"
    assert enc.get(f"{{{_SPARKLE}}}shortVersionString") == "0.2.0"
    assert enc.get("type") == "application/octet-stream"
    # native signature verification stays OFF — no edSignature
    assert enc.get(f"{{{_SPARKLE}}}edSignature") is None


def test_xml_orders_newest_first():
    xml = build_appcast_xml(title="Locksmith", releases=[
        {"version": "0.1.7", "artifact_url": "u/0.1.7.dmg", "artifact_size": 1},
        {"version": "0.2.0", "artifact_url": "u/0.2.0.dmg", "artifact_size": 2},
    ])
    root = ET.fromstring(xml)
    versions = [e.get(f"{{{_SPARKLE}}}version")
                for e in root.findall(".//item/enclosure")]
    assert versions == ["0.2.0", "0.1.7"]


def test_xml_escapes_special_chars():
    xml = build_appcast_xml(title="Acme & Co <test>", releases=[{
        "version": "0.2.0",
        "artifact_url": "https://cdn.example.com/r?a=1&b=2",
        "artifact_size": 5, "released_at": "",
    }])
    # must be well-formed despite & and < in title and & in url
    root = ET.fromstring(xml)  # raises if malformed
    enc = root.find(".//item/enclosure")
    assert enc.get("url") == "https://cdn.example.com/r?a=1&b=2"  # round-trips unescaped
    assert "Acme & Co <test>" in root.find(".//item/title").text  # ET unescapes on read
