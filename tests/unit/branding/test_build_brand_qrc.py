import importlib, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "packaging"))
gen = importlib.import_module("generate_qrc")
brandlib = importlib.import_module("brandlib")

def test_usurance_qrc_aliases_logos_to_brand_dir():
    m = brandlib.load_brand_manifest("usurance")
    qrc = gen.build_brand_qrc(REPO, REPO / "brands" / "usurance", m)
    # brand logo aliased to the usurance source
    assert '<file alias="assets/custom/SymbolLogo.svg">brands/usurance/SymbolLogo.svg</file>' in qrc
    assert '<file alias="assets/custom/SplashScreen.png">brands/usurance/SplashScreen.png</file>' in qrc
    # a neutral asset is present verbatim
    assert "<file>assets/custom/settings.png</file>" in qrc
    # app-icons are NOT compiled into the rcc
    assert "AppIcon.icns" not in qrc

def test_locksmith_qrc_uses_reference_slots():
    m = brandlib.load_brand_manifest("locksmith")
    qrc = gen.build_brand_qrc(REPO, REPO / "brands" / "locksmith", m)
    assert '<file alias="assets/custom/SymbolLogo.svg">brands/locksmith/SymbolLogo.svg</file>' in qrc

def test_missing_variant_falls_back_to_standard(tmp_path):
    # brand ships only the standard symbol → white/black alias its standard file
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "assets" / "custom" / "settings.png").write_text("x")
    bd = tmp_path / "brands" / "acme"; bd.mkdir(parents=True)
    for f in ["SplashScreen.png","SymbolLogo.svg","NameLogo.svg","NameLogoBlack.svg","FullLogo.svg","FullLogoBlack.svg"]:
        (bd / f).write_text("x")
    manifest = {"brand": {"id": "acme"}, "assets": {
        "splash":"SplashScreen.png","symbol_logo":"SymbolLogo.svg",
        "name_logo":"NameLogo.svg","name_logo_black":"NameLogoBlack.svg",
        "full_logo":"FullLogo.svg","full_logo_black":"FullLogoBlack.svg"}}
    qrc = gen.build_brand_qrc(tmp_path, bd, manifest)
    assert '<file alias="assets/custom/SymbolLogoWhite.svg">brands/acme/SymbolLogo.svg</file>' in qrc
    assert '<file alias="assets/custom/SymbolLogoBlack.svg">brands/acme/SymbolLogo.svg</file>' in qrc
