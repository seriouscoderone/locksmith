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
