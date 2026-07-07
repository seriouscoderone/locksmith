import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")


def test_macos_info_plist_from_locksmith():
    m = brandlib.load_brand_manifest("locksmith")
    plist = brandlib.macos_info_plist(m, "0.1.8")
    assert plist["CFBundleName"] == "Locksmith"
    assert plist["CFBundleIdentifier"] == "host.keri.locksmith"
    assert plist["CFBundleExecutable"] == "Locksmith"
    assert plist["CFBundleShortVersionString"] == "0.1.8"
    assert plist["SUFeedURL"] == "https://releases.keri.host/appcast/v1/macos.xml"
    # KERI is sole trust: Sparkle's EdDSA key must NOT be present
    assert "SUPublicEDKey" not in plist


def test_exe_name_locksmith():
    assert brandlib.exe_name(brandlib.load_brand_manifest("locksmith")) == "Locksmith"


def test_specs_bundle_the_runtime_release_triad():
    """Both PyInstaller specs MUST bundle all three build-generated files from
    locksmith/release/ — publisher_anchor.json, deploy_config.json, AND
    brand.json. If brand.json is missing, branding.load_brand() finds no
    packaged file at runtime and falls back to the baked-in Locksmith default,
    so a non-locksmith brand renders as "Locksmith" in the window title,
    toolbar, and theme (the v0.2.19 Usurance bug)."""
    for name in ("Locksmith.macos.spec", "Locksmith.windows.spec"):
        text = (REPO_ROOT / "packaging" / name).read_text(encoding="utf-8")
        for fname in ("publisher_anchor.json", "deploy_config.json", "brand.json"):
            assert fname in text, f"{name} datas is missing {fname}"
        assert '"locksmith/release"' in text, f"{name} missing locksmith/release datas dest"
