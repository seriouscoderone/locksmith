import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brand_apply = importlib.import_module("brand_apply")


@pytest.fixture
def fake_repo(tmp_path):
    """A minimal repo tree: brands/, assets/custom/, packaging/, src/.../release/."""
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "assets" / "custom" / "AppIcon.icns").write_text("OLD-ICON")
    (tmp_path / "packaging" / "wix").mkdir(parents=True)
    (tmp_path / "packaging" / "dmg").mkdir(parents=True)
    (tmp_path / "packaging" / "wix" / "Locksmith.wxs.in").write_text(
        '<Package Name="@@NAME@@" UpgradeCode="@@UPGRADE_CODE@@" />')
    (tmp_path / "src" / "locksmith" / "release").mkdir(parents=True)
    acme = tmp_path / "brands" / "acme"
    acme.mkdir(parents=True)
    (acme / "brand.toml").write_text((REPO_ROOT / "brands" / "example" / "brand.toml")
                                     .read_text().replace('id            = "example"',
                                                          'id            = "acme"')
                                     .replace("Example Vault", "Acme"))
    (acme / "AppIcon.icns").write_text("ACME-ICON")
    (acme / "publisher_anchor.json").write_text('{"publisher_aid": "EAcme"}')
    (acme / "deploy_config.json").write_text('{"s3_bucket": "acme"}')
    return tmp_path


def test_apply_stages_assets_and_writes_outputs(fake_repo):
    report = brand_apply.apply("acme", fake_repo, check=False)
    # asset staged over assets/custom/
    assert (fake_repo / "assets" / "custom" / "AppIcon.icns").read_text() == "ACME-ICON"
    # runtime brand.json written
    doc = json.loads((fake_repo / "src" / "locksmith" / "release" / "brand.json").read_text())
    assert doc["display_name"] == "Acme"
    # wxs rendered
    wxs = (fake_repo / "packaging" / "wix" / "Locksmith.wxs").read_text()
    assert 'Name="Acme"' in wxs and "@@" not in wxs
    # dmg layout written
    layout = json.loads((fake_repo / "packaging" / "dmg" / "layout.json").read_text())
    assert layout["volume_name"] == "Acme"
    # trust material injected
    assert (fake_repo / "src" / "locksmith" / "release" / "publisher_anchor.json").exists()
    assert (fake_repo / "src" / "locksmith" / "release" / "deploy_config.json").exists()
    assert report["staged_assets"] == ["AppIcon.icns"]


def test_check_mode_writes_nothing(fake_repo):
    brand_apply.apply("acme", fake_repo, check=True)
    assert (fake_repo / "assets" / "custom" / "AppIcon.icns").read_text() == "OLD-ICON"
    assert not (fake_repo / "src" / "locksmith" / "release" / "brand.json").exists()
