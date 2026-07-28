"""[peer] brand section — the advertised-host override for ambiguous hosts.

Auto-detection picks the interface that owns the default route. When a host
has BOTH a LAN interface and an overlay (Tailscale/WireGuard) interface, that
answer can be the wrong one for the deployment; a brand pins the right one
here rather than every install being fixed up by hand.
"""
from locksmith.core.branding import Brand, _from_dict


def test_brand_default_has_no_advertised_host_override():
    assert Brand().peer_advertised_host == ""


def test_from_dict_reads_peer_section():
    b = _from_dict({"id": "usurance", "peer": {"advertised_host": "100.64.0.7"}})
    assert b.peer_advertised_host == "100.64.0.7"


def test_from_dict_without_peer_section_stays_inert():
    assert _from_dict({"id": "locksmith"}).peer_advertised_host == ""


def test_runtime_brand_json_carries_the_peer_section():
    """brand.json is the ONLY brand surface the running app reads — an
    override that brandlib drops on the floor never reaches netaddr."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packaging"))
    import brandlib

    doc = brandlib.runtime_brand_json({
        "brand": {"id": "b", "display_name": "B", "tagline": "t"},
        "identity": {"org_domain": "b.example"},
        "urls": {"website": "w", "support": "s", "appcast_macos": "a",
                 "appcast_windows": "a", "appcast_macos_xml": "a",
                 "appcast_windows_xml": "a"},
        "peer": {"advertised_host": "100.64.0.7"},
    })
    assert doc["peer"] == {"advertised_host": "100.64.0.7"}
    assert _from_dict(doc).peer_advertised_host == "100.64.0.7"
