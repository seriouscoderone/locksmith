import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("LOCKSMITH_BRAND", raising=False)


def test_active_brand_defaults_to_locksmith():
    assert brandlib.active_brand_id() == "locksmith"


def test_active_brand_from_env(monkeypatch):
    monkeypatch.setenv("LOCKSMITH_BRAND", "example")
    assert brandlib.active_brand_id() == "example"


def test_load_locksmith_manifest():
    m = brandlib.load_brand_manifest("locksmith")
    assert m["brand"]["display_name"] == "Locksmith"
    assert m["brand"]["manufacturer"] == "KERI.host"
    assert m["identity"]["bundle_id"] == "host.keri.locksmith"
    assert m["identity"]["upgrade_code"] == "297BBF26-821C-4D56-8857-309C7B531E21"
    assert m["identity"]["artifact_prefix"] == "Locksmith"
    assert m["urls"]["website"] == "https://locksmith.app"
    assert m["theme"]["primary"] == "#F57B03"
    assert m["_dir"].name == "locksmith"


def test_unknown_brand_falls_back_to_example():
    m = brandlib.load_brand_manifest("does-not-exist")
    assert m["brand"]["id"] == "example"


def test_exe_name():
    assert brandlib.exe_name(brandlib.load_brand_manifest("locksmith")) == "Locksmith"


def test_macos_info_plist_sufeed_is_xml():
    m = brandlib.load_brand_manifest("locksmith")
    plist = brandlib.macos_info_plist(m, "0.2.1")
    assert plist["SUFeedURL"] == "https://releases.keri.host/appcast/v1/macos.xml"


def test_runtime_brand_json_carries_xml_feeds():
    doc = brandlib.runtime_brand_json(brandlib.load_brand_manifest("locksmith"))
    assert doc["appcast_macos_xml"] == "https://releases.keri.host/appcast/v1/macos.xml"
    assert doc["appcast_windows_xml"] == "https://releases.keri.host/appcast/v1/windows.xml"
