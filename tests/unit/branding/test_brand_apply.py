import importlib, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brand_apply = importlib.import_module("brand_apply")


@pytest.fixture
def fake_repo(tmp_path):
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "assets" / "custom" / "settings.png").write_bytes(b"NEUTRAL")
    (tmp_path / "packaging" / "wix").mkdir(parents=True)
    (tmp_path / "packaging" / "wix" / "Locksmith.wxs.in").write_text(
        '<Package Name="@@NAME@@" UpgradeCode="@@UPGRADE_CODE@@" />')
    (tmp_path / "src" / "locksmith" / "release").mkdir(parents=True)
    # reference brand must exist for slot fallback
    lock = tmp_path / "brands" / "locksmith"; lock.mkdir(parents=True)
    for f in ["SplashScreen.png","SymbolLogo.svg","SymbolLogoWhite.svg","SymbolLogoBlack.svg",
              "NameLogo.svg","NameLogoBlack.svg","FullLogo.svg","FullLogoBlack.svg"]:
        (lock / f).write_bytes(b"LOCK-"+f.encode())
    (lock / "AppIcon.icns").write_bytes(b"LOCK-ICNS"); (lock / "AppIcon.ico").write_bytes(b"LOCK-ICO")
    # acme brand ships its own symbol + app icon
    acme = tmp_path / "brands" / "acme"; acme.mkdir(parents=True)
    (acme / "brand.toml").write_text((REPO_ROOT/"brands"/"example"/"brand.toml").read_text()
        .replace('id            = "example"','id            = "acme"').replace("Example Vault","Acme"))
    for f in ["SplashScreen.png","SymbolLogo.svg","SymbolLogoWhite.svg","SymbolLogoBlack.svg",
              "NameLogo.svg","NameLogoBlack.svg","FullLogo.svg","FullLogoBlack.svg"]:
        (acme / f).write_bytes(b"ACME-"+f.encode())
    (acme / "AppIcon.icns").write_bytes(b"ACME-ICNS"); (acme / "AppIcon.ico").write_bytes(b"ACME-ICO")
    (acme / "publisher_anchor.json").write_text('{"publisher_aid":"EAcme"}')
    (acme / "deploy_config.json").write_text('{"s3_bucket":"acme"}')
    return tmp_path


def test_apply_writes_bundle_to_out_and_leaves_tree_clean(fake_repo):
    out = fake_repo / "src" / "locksmith" / "release" / "acme"
    report = brand_apply.apply("acme", fake_repo, out=out, check=False)
    # compiled rcc exists and is non-empty
    rcc = out / "assets.rcc"
    assert rcc.is_file() and rcc.stat().st_size > 0
    # config + packaging outputs land in <out>
    assert json.loads((out / "brand.json").read_text())["display_name"] == "Acme"
    assert 'Name="Acme"' in (out / "Locksmith.wxs").read_text()
    assert json.loads((out / "dmg-layout.json").read_text())["volume_name"] == "Acme"
    # app-icons staged as files (not in the rcc)
    assert (out / "AppIcon.icns").read_bytes() == b"ACME-ICNS"
    # trust material injected into <out>
    assert (out / "publisher_anchor.json").is_file()
    # NOTHING tracked was mutated: the neutral pool + packaging template untouched
    assert (fake_repo / "assets" / "custom" / "settings.png").read_bytes() == b"NEUTRAL"
    assert "@@NAME@@" in (fake_repo / "packaging" / "wix" / "Locksmith.wxs.in").read_text()
    assert not (fake_repo / "packaging" / "wix" / "Locksmith.wxs").exists()
    assert report["out"] == str(out)


def test_registered_rcc_resolves_brand_logo(fake_repo):
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import QResource, QFile, QIODevice
    out = fake_repo / "src" / "locksmith" / "release" / "acme"
    brand_apply.apply("acme", fake_repo, out=out, check=False)
    app = QGuiApplication.instance() or QGuiApplication([])
    assert QResource.registerResource(str(out / "assets.rcc"))
    try:
        f = QFile(":/assets/custom/SymbolLogo.svg"); f.open(QIODevice.ReadOnly)
        data = bytes(f.readAll()); f.close()
        assert data == b"ACME-SymbolLogo.svg"          # came from brands/acme, atomically
    finally:
        QResource.unregisterResource(str(out / "assets.rcc"))


def test_missing_rcc_tool_fails_loud(fake_repo, monkeypatch):
    monkeypatch.setattr(brand_apply.shutil, "which", lambda _n: None)
    monkeypatch.setattr(brand_apply, "_find_rcc", lambda: None)
    out = fake_repo / "src" / "locksmith" / "release" / "acme"
    with pytest.raises((SystemExit, RuntimeError)):
        brand_apply.apply("acme", fake_repo, out=out, check=False)


def test_check_mode_writes_nothing(fake_repo):
    out = fake_repo / "src" / "locksmith" / "release" / "acme"
    brand_apply.apply("acme", fake_repo, out=out, check=True)
    assert not (out / "assets.rcc").exists()
    assert not (out / "brand.json").exists()
