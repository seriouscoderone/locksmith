"""The KERI Foundation plugin icon must not be a brand-staged asset.

Regression: the plugin used :/assets/custom/SymbolLogo.svg, which brand_apply.py
overwrites per brand, so the KF entry showed the active brand's logo (the
Usurance eye in a Usurance build) instead of KERI Foundation's own mark.
"""
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_kf_icon_resource_is_not_brand_staged():
    from locksmith.plugins.kerifoundation import plugin

    # The plugin exposes a single source of truth for its icon path.
    assert plugin.KF_ICON_RESOURCE == ":/assets/kerifoundation/SymbolLogo.svg"
    # It must NOT live under assets/custom/ — that is the brand-staging dir.
    assert "assets/custom/" not in plugin.KF_ICON_RESOURCE


def test_kf_icon_asset_file_exists_outside_custom():
    asset = REPO_ROOT / "assets" / "kerifoundation" / "SymbolLogo.svg"
    assert asset.is_file(), "KF-owned icon asset missing"
    # Byte-identical to the committed Locksmith reference symbol.
    reference = REPO_ROOT / "brands" / "locksmith" / "SymbolLogo.svg"
    assert asset.read_bytes() == reference.read_bytes()


def test_brand_apply_never_stages_the_kf_asset(tmp_path):
    """Running brand_apply for a brand that ships a SymbolLogo never writes
    into assets/ at all (neutral pool, including the KF-owned mark) — the
    atomic-bundle contract writes everything into <out>, not into the
    tracked/neutral tree. The brand's own SymbolLogo is still resolvable via
    the compiled rcc's :/assets/custom/ alias, distinct from the KF mark's
    own :/assets/kerifoundation/ path."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import QResource, QFile, QIODevice

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    sys.path.insert(0, str(REPO_ROOT / "packaging"))
    brand_apply = importlib.import_module("brand_apply")

    # Minimal fake repo tree with a brand that ships SymbolLogo.svg.
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "assets" / "custom" / "SymbolLogo.svg").write_text("LOCKSMITH-SYMBOL")
    (tmp_path / "assets" / "kerifoundation").mkdir(parents=True)
    kf_asset = tmp_path / "assets" / "kerifoundation" / "SymbolLogo.svg"
    kf_asset.write_text("KF-OWNED-MARK")
    (tmp_path / "packaging" / "wix").mkdir(parents=True)
    (tmp_path / "packaging" / "wix" / "Locksmith.wxs.in").write_text(
        '<Package Name="@@NAME@@" UpgradeCode="@@UPGRADE_CODE@@" />')
    (tmp_path / "src" / "locksmith" / "release").mkdir(parents=True)
    # reference brand must exist for slot fallback (splash, other logo forms)
    lock = tmp_path / "brands" / "locksmith"
    lock.mkdir(parents=True)
    for f in ["SplashScreen.png", "SymbolLogo.svg", "SymbolLogoWhite.svg", "SymbolLogoBlack.svg",
              "NameLogo.svg", "NameLogoBlack.svg", "FullLogo.svg", "FullLogoBlack.svg"]:
        (lock / f).write_bytes(b"LOCK-" + f.encode())
    (lock / "AppIcon.icns").write_bytes(b"LOCK-ICNS")
    (lock / "AppIcon.ico").write_bytes(b"LOCK-ICO")
    brand = tmp_path / "brands" / "acme"
    brand.mkdir(parents=True)
    (brand / "brand.toml").write_text(
        (REPO_ROOT / "brands" / "example" / "brand.toml").read_text()
        .replace('id            = "example"', 'id            = "acme"')
        .replace("Example Vault", "Acme"))
    (brand / "SymbolLogo.svg").write_text("ACME-SYMBOL")

    out = tmp_path / "src" / "locksmith" / "release" / "acme"
    report = brand_apply.apply("acme", tmp_path, out=out, check=False)

    # Nothing under assets/ (neutral pool) was touched -- the brand's symbol
    # never lands in assets/custom/, and the KF-owned asset is untouched.
    assert (tmp_path / "assets" / "custom" / "SymbolLogo.svg").read_text() == "LOCKSMITH-SYMBOL"
    assert kf_asset.read_text() == "KF-OWNED-MARK"

    # The brand's symbol IS resolvable via the compiled rcc's :/assets/custom/
    # alias -- distinct from the KF mark's own, un-aliased :/ path.
    app = QGuiApplication.instance() or QGuiApplication([])
    assert QResource.registerResource(str(out / "assets.rcc"))
    try:
        f = QFile(":/assets/custom/SymbolLogo.svg"); f.open(QIODevice.ReadOnly)
        assert bytes(f.readAll()) == b"ACME-SYMBOL"; f.close()
        f = QFile(":/assets/kerifoundation/SymbolLogo.svg"); f.open(QIODevice.ReadOnly)
        assert bytes(f.readAll()) == b"KF-OWNED-MARK"; f.close()
    finally:
        QResource.unregisterResource(str(out / "assets.rcc"))
