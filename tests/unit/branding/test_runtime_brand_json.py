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


def test_runtime_json_carries_brand_id():
    assert brandlib.runtime_brand_json(brandlib.load_brand_manifest("locksmith"))["id"] == "locksmith"
    assert brandlib.runtime_brand_json(brandlib.load_brand_manifest("usurance"))["id"] == "usurance"


def test_runtime_json_copies_bootstrap_table_verbatim():
    # None of the committed brand.toml fixtures carry a non-empty [bootstrap]
    # table, so exercise the copy with an in-memory manifest to prove the
    # HOA bootstrap section round-trips into brand.json unchanged (mirrors
    # how [theme] is copied a few lines above it).
    m = brandlib.load_brand_manifest("locksmith")
    m["bootstrap"] = {
        "peel_core_pages": True,
        "default_vault_name": "Carrier",
        "default_passcode": "",
        "default_aid_alias": "carrier",
        "default_witnesses": ["BwitnessAID"],
        "default_toad": 1,
    }
    doc = brandlib.runtime_brand_json(m)
    assert doc["bootstrap"] == m["bootstrap"]
