from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BRAND_SLOTS = ["SplashScreen.png", "SymbolLogo.svg", "SymbolLogoWhite.svg",
               "SymbolLogoBlack.svg", "NameLogo.svg", "NameLogoBlack.svg",
               "FullLogo.svg", "FullLogoBlack.svg", "AppIcon.icns", "AppIcon.ico"]


def test_brand_slots_moved_to_locksmith_brand():
    for f in BRAND_SLOTS:
        assert (REPO / "brands" / "locksmith" / f).is_file(), f"missing brands/locksmith/{f}"
        assert not (REPO / "assets" / "custom" / f).exists(), f"assets/custom/{f} should be gone"


def test_neutral_assets_stay():
    for f in ["settings.png", "vault.png", "flags/us.svg", "step-icon-check.png"]:
        assert (REPO / "assets" / "custom" / f).is_file()


def test_resources_qrc_is_neutral_only():
    qrc = (REPO / "resources.qrc").read_text()
    assert "assets/custom/SymbolLogo.svg" not in qrc
    assert "assets/custom/FullLogo.svg" not in qrc
    assert "assets/custom/settings.png" in qrc
