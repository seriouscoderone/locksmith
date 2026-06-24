import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")


def test_locksmith_identity_unchanged():
    m = brandlib.load_brand_manifest("locksmith")
    i = m["identity"]
    assert m["brand"]["display_name"] == "Locksmith"
    assert m["brand"]["manufacturer"] == "KERI.host"
    assert i["bundle_id"] == "host.keri.locksmith"
    assert i["upgrade_code"] == "297BBF26-821C-4D56-8857-309C7B531E21"
    assert i["data_dir"] == "Locksmith"
    assert i["artifact_prefix"] == "Locksmith"


def test_locksmith_rendered_wxs_matches_today():
    m = brandlib.load_brand_manifest("locksmith")
    tmpl = (REPO_ROOT / "packaging" / "wix" / "Locksmith.wxs.in").read_text()
    out = brandlib.render_wxs(m, tmpl)
    assert 'Name="Locksmith"' in out
    assert 'Manufacturer="KERI.host"' in out
    assert 'UpgradeCode="297BBF26-821C-4D56-8857-309C7B531E21"' in out
    assert 'Value="https://locksmith.app"' in out
    assert 'Value="https://locksmith.app/support"' in out
    assert r'Key="Software\KERI.host\Locksmith"' in out
    assert "@@" not in out


def test_locksmith_runtime_brand_json():
    m = brandlib.load_brand_manifest("locksmith")
    doc = brandlib.runtime_brand_json(m)
    assert doc["display_name"] == "Locksmith"
    assert doc["org_name"] == "keri.host"
    assert doc["theme"]["primary"] == "#F57B03"
    assert doc["theme"]["primary_hover"] == "#D66A02"
    assert doc["theme"]["primary_pressed"] == "#E67E00"
    assert doc["theme"]["toolbar_dark"] == "#1A252C"


def test_locksmith_dmg_layout():
    m = brandlib.load_brand_manifest("locksmith")
    layout = brandlib.render_dmg_layout(m)
    assert layout["volume_name"] == "Locksmith"
    assert layout["icons"][0]["name"] == "Locksmith.app"
