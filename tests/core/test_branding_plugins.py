# -*- encoding: utf-8 -*-
"""[plugins] bundled brand surface + neutral bootstrap fallbacks (HOA #4).

Which bundled plugins a brand activates is brand config (``Brand.
bundled_plugins``, from brand.json ``{"plugins": {"bundled": [...]}}`` /
brand.toml ``[plugins] bundled``) instead of a framework-hardcoded heuristic.
Bootstrap naming falls back to neutral code defaults ("default"/"Default")
when a brand omits its own — never a domain string in framework code.
"""
import sys
from pathlib import Path

from locksmith.core.branding import Brand, _from_dict

# brandlib.py is a standalone build-time module living in the repo-root
# packaging/ dir (NOT locksmith.packaging — that package doesn't exist; see
# scripts/brand_apply.py and tests/packaging/test_usurance_brand_apply.py for
# the same sys.path pattern).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGING = _REPO_ROOT / "packaging"
if str(_PACKAGING) not in sys.path:
    sys.path.insert(0, str(_PACKAGING))


def test_bundled_plugins_default_empty():
    assert Brand().bundled_plugins == ()


def test_bundled_plugins_parsed_from_plugins_table():
    b = _from_dict({"plugins": {"bundled": ["hoa_shell", "actuary"]}})
    assert b.bundled_plugins == ("hoa_shell", "actuary")


def test_missing_plugins_table_is_empty():
    assert _from_dict({}).bundled_plugins == ()


def test_runtime_brand_json_passes_plugins_through():
    import brandlib
    manifest = {
        "brand": {"id": "test", "display_name": "Test", "tagline": "Test tagline"},
        "identity": {"org_domain": "example.com"},
        "urls": {
            "website": "https://example.com",
            "support": "https://example.com/support",
            # BOTH feed flavors are required: XML for Sparkle, JSON for the
            # in-app KERI verify gate. Every real brand.toml declares all four,
            # and runtime_brand_json requires them on purpose — a brand missing
            # its JSON feed used to silently verify against locksmith's.
            "appcast_macos": "https://example.com/appcast/macos.json",
            "appcast_windows": "https://example.com/appcast/windows.json",
            "appcast_macos_xml": "https://example.com/appcast/macos.xml",
            "appcast_windows_xml": "https://example.com/appcast/windows.xml",
        },
        "plugins": {"bundled": ["hoa_shell"]},
    }
    out = brandlib.runtime_brand_json(manifest)
    assert out["plugins"] == {"bundled": ["hoa_shell"]}


def test_setup_prefill_falls_back_to_neutral_default(monkeypatch):
    from locksmith.ui import window as window_mod
    from locksmith.core import branding
    monkeypatch.setattr(branding, "brand", lambda: Brand())  # empty vault name
    monkeypatch.setattr(window_mod, "brand", lambda: Brand())
    assert window_mod._setup_prefill_name() == "Default"
