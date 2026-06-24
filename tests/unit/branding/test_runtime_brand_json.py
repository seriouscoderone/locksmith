import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")
branding = importlib.import_module("locksmith.core.branding")


def test_locksmith_runtime_json_round_trips_to_brand():
    m = brandlib.load_brand_manifest("locksmith")
    doc = brandlib.runtime_brand_json(m)
    assert doc["display_name"] == "Locksmith"
    assert doc["org_name"] == "keri.host"      # from [org].name
    assert doc["website"] == "https://locksmith.app"
    assert doc["theme"]["primary"] == "#F57B03"
    b = branding._from_dict(doc)
    assert b.display_name == "Locksmith"
    assert b.org_domain == "keri.host"


def test_example_org_name_falls_back_to_domain():
    m = brandlib.load_brand_manifest("example")
    doc = brandlib.runtime_brand_json(m)
    # example/brand.toml omits [org], so org_name falls back to org_domain
    assert doc["org_name"] == "example.com"
