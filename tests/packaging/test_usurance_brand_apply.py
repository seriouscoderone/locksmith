"""Full brand_apply.apply() pipeline exercised for the real usurance brand.

Runs the actual Python entrypoint (not a shelled build) against a tmp_path
mirror of the repo tree, seeded with the REAL brands/usurance/brand.toml +
assets, so this proves the whole staging pipeline — not just
brandlib.runtime_brand_json() in isolation (already covered by
tests/unit/branding/test_runtime_brand_json.py) — produces a correct
runtime brand.json (id + bootstrap table) plus brand-parameterized wix/dmg
packaging config, without touching the real working tree.
"""
import importlib
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brand_apply = importlib.import_module("brand_apply")


def _fake_repo(tmp_path: Path) -> Path:
    """Minimal repo skeleton (assets/, packaging/, src/.../release/) with the
    REAL brands/usurance directory copied in verbatim."""
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "packaging" / "wix").mkdir(parents=True)
    (tmp_path / "packaging" / "dmg").mkdir(parents=True)
    (tmp_path / "packaging" / "wix" / "Locksmith.wxs.in").write_text(
        (REPO_ROOT / "packaging" / "wix" / "Locksmith.wxs.in")
        .read_text(encoding="utf-8"),
        encoding="utf-8")
    (tmp_path / "src" / "locksmith" / "release").mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "brands" / "usurance",
                     tmp_path / "brands" / "usurance")
    return tmp_path


def test_brand_apply_usurance_writes_runtime_brand_json(tmp_path):
    repo = _fake_repo(tmp_path)

    report = brand_apply.apply("usurance", repo, check=False)
    assert report["brand"] == "usurance"

    bj = json.loads(
        (repo / "src" / "locksmith" / "release" / "brand.json").read_text())
    assert bj["id"] == "usurance"
    assert bj["bootstrap"]["peel_core_pages"] is True
    assert bj["bootstrap"]["default_aid_alias"] == "carrier"
    assert bj["bootstrap"]["default_witnesses"] == []  # witnessless POC


def test_brand_apply_usurance_stages_real_assets(tmp_path):
    repo = _fake_repo(tmp_path)

    report = brand_apply.apply("usurance", repo, check=False)
    assert "AppIcon.icns" in report["staged_assets"]
    assert "SymbolLogo.svg" in report["staged_assets"]

    staged = repo / "assets" / "custom" / "AppIcon.icns"
    source = REPO_ROOT / "brands" / "usurance" / "AppIcon.icns"
    assert staged.read_bytes() == source.read_bytes()


def test_brand_apply_usurance_renders_wix_and_dmg_identity(tmp_path):
    repo = _fake_repo(tmp_path)

    brand_apply.apply("usurance", repo, check=False)

    wxs = (repo / "packaging" / "wix" / "Locksmith.wxs").read_text()
    assert 'Name="Usurance"' in wxs
    assert "@@" not in wxs  # every token substituted

    layout = json.loads(
        (repo / "packaging" / "dmg" / "layout.json").read_text())
    assert layout["volume_name"] == "Usurance"


def test_check_mode_does_not_write_usurance_outputs(tmp_path):
    repo = _fake_repo(tmp_path)

    brand_apply.apply("usurance", repo, check=True)
    assert not (repo / "src" / "locksmith" / "release" / "brand.json").exists()
    assert not (repo / "packaging" / "wix" / "Locksmith.wxs").exists()
