import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")

TEMPLATE = (REPO_ROOT / "packaging" / "wix" / "Locksmith.wxs.in").read_text(encoding="utf-8")


def test_render_wxs_locksmith_matches_current_values():
    m = brandlib.load_brand_manifest("locksmith")
    out = brandlib.render_wxs(m, TEMPLATE)
    assert 'Name="Locksmith"' in out
    assert 'Manufacturer="KERI.host"' in out
    assert 'UpgradeCode="297BBF26-821C-4D56-8857-309C7B531E21"' in out
    assert 'Value="https://locksmith.app"' in out
    assert 'Value="https://locksmith.app/support"' in out
    assert r'Key="Software\KERI.host\Locksmith"' in out
    assert "@@" not in out  # every token resolved


def test_render_wxs_for_another_brand():
    m = brandlib.load_brand_manifest("example")
    out = brandlib.render_wxs(m, TEMPLATE)
    assert 'Name="Example Vault"' in out
    assert 'Manufacturer="Example, Inc."' in out
    assert 'UpgradeCode="00000000-0000-0000-0000-000000000000"' in out
    assert "@@" not in out


def test_render_dmg_layout():
    m = brandlib.load_brand_manifest("locksmith")
    layout = brandlib.render_dmg_layout(m)
    assert layout["volume_name"] == "Locksmith"
    assert layout["icons"][0]["name"] == "Locksmith.app"


def test_render_wxs_locksmith_matches_golden():
    # The rendered wxs is generated (untracked); assert it matches a checked-in
    # golden so template/manifest drift is caught without tracking the output.
    repo = Path(__file__).resolve().parents[3]
    template = (repo / "packaging" / "wix" / "Locksmith.wxs.in").read_text()
    golden = (repo / "tests" / "unit" / "branding" / "fixtures" / "locksmith.wxs.golden").read_text()
    rendered = brandlib.render_wxs(brandlib.load_brand_manifest("locksmith"), template)
    assert rendered == golden
