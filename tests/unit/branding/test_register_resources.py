# tests/unit/branding/test_register_resources.py
import importlib, os, sys
from pathlib import Path
import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "packaging"))
brand_apply = importlib.import_module("brand_apply")
from locksmith.core import branding
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QResource, QFile, QIODevice


@pytest.fixture
def usurance_bundle(tmp_path):
    out = tmp_path / "usu"
    brand_apply.apply("usurance", REPO, out=out, check=False)
    return out


def test_register_resolves_logo_and_config_from_same_source(monkeypatch, usurance_bundle):
    _ = QGuiApplication.instance() or QGuiApplication([])
    monkeypatch.setenv(branding.BRAND_CONFIG_ENV_VAR, str(usurance_bundle / "brand.json"))
    branding._reset_cache_for_tests()
    rcc = branding.register_brand_resources()
    try:
        assert branding.brand().display_name == "Usurance"          # config
        f = QFile(":/assets/custom/SymbolLogo.svg"); f.open(QIODevice.ReadOnly)
        logo = bytes(f.readAll()); f.close()
        assert logo == (REPO / "brands" / "usurance" / "SymbolLogo.svg").read_bytes()  # logo, same source
    finally:
        QResource.unregisterResource(str(rcc)); branding._reset_cache_for_tests()


def test_missing_bundle_raises(monkeypatch, tmp_path):
    only_json = tmp_path / "brand.json"
    only_json.write_text('{"display_name":"NoRcc"}')          # brand.json but NO assets.rcc sibling
    monkeypatch.setenv(branding.BRAND_CONFIG_ENV_VAR, str(only_json))
    branding._reset_cache_for_tests()
    with pytest.raises(RuntimeError):
        branding.register_brand_resources()
    branding._reset_cache_for_tests()
