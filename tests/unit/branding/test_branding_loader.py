import json
import importlib

import pytest

branding = importlib.import_module("locksmith.core.branding")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("LOCKSMITH_BRAND_CONFIG", raising=False)
    branding._reset_cache_for_tests()
    yield
    branding._reset_cache_for_tests()


def test_default_is_locksmith():
    b = branding.load_brand()
    assert b.display_name == "Locksmith"
    assert b.org_name == "keri.host"
    assert b.org_domain == "keri.host"
    assert b.website == "https://locksmith.app"
    assert b.support == "https://locksmith.app/support"
    assert b.theme["primary"] == "#F57B03"


def test_env_override(tmp_path, monkeypatch):
    cfg = tmp_path / "brand.json"
    cfg.write_text(json.dumps({
        "display_name": "Acme Vault", "tagline": "secure keys",
        "org_name": "acme.example.com", "org_domain": "acme.example.com",
        "website": "https://acme.example.com",
        "support": "https://acme.example.com/help",
        "theme": {"primary": "#112233"},
    }))
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(cfg))
    branding._reset_cache_for_tests()
    b = branding.brand()
    assert b.display_name == "Acme Vault"
    assert b.theme["primary"] == "#112233"


def test_env_path_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(tmp_path / "nope.json"))
    branding._reset_cache_for_tests()
    with pytest.raises(FileNotFoundError):
        branding.load_brand()


def test_brand_is_cached(monkeypatch):
    assert branding.brand() is branding.brand()


def test_app_title():
    assert branding.app_title(None) == "Locksmith"
    assert branding.app_title("") == "Locksmith"
    assert branding.app_title("Personal") == "Locksmith | Personal"


def test_default_brand_carries_xml_feeds():
    b = branding.load_brand()
    assert b.appcast_macos_xml == "https://releases.keri.host/appcast/v1/macos.xml"
    assert b.appcast_windows_xml == "https://releases.keri.host/appcast/v1/windows.xml"


def test_default_brand_id_is_locksmith():
    assert branding.load_brand().id == "locksmith"


def test_brand_id_from_injected_json(tmp_path, monkeypatch):
    cfg = tmp_path / "brand.json"
    cfg.write_text(json.dumps({
        "id": "usurance", "display_name": "Usurance", "tagline": "t",
        "org_name": "usurance.com", "org_domain": "usurance.com",
        "website": "https://usurance.com", "support": "https://usurance.com/help",
        "theme": {},
    }))
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(cfg))
    branding._reset_cache_for_tests()
    assert branding.brand().id == "usurance"


def test_app_data_dir_is_brand_scoped(tmp_path, monkeypatch):
    """Diagnostic logs (and any future per-install app data) must not land in
    another product's directory: a Usurance install writing into
    ~/Library/Application Support/Locksmith is a support headache and a
    brand-isolation leak (backlog/2026-07-29-grant-send-reports-success-
    while-undeliverable.md item 3). Pure path computation — no mkdir."""
    import platform as _platform
    from pathlib import Path

    cfg = tmp_path / "brand.json"
    cfg.write_text(json.dumps({"id": "usurance", "display_name": "Usurance"}))
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(cfg))
    branding._reset_cache_for_tests()

    p = branding.app_data_dir()

    sysname = _platform.system()
    if sysname == "Darwin":
        assert p == (Path.home() / "Library" / "Application Support"
                     / "Usurance")
    elif sysname == "Windows":
        assert p.name == "Usurance"
    else:
        assert p == Path.home() / ".local" / "share" / "usurance"


def test_app_data_dir_reference_brand_keeps_the_shipped_location():
    """The reference brand's dir must stay exactly where every shipped
    Locksmith build already writes (~/…/Locksmith) — moving it would orphan
    existing logs and verification history."""
    import platform as _platform
    from pathlib import Path

    p = branding.app_data_dir()
    sysname = _platform.system()
    if sysname == "Darwin":
        assert p == (Path.home() / "Library" / "Application Support"
                     / "Locksmith")
    elif sysname == "Windows":
        assert p.name == "Locksmith"
    else:
        assert p == Path.home() / ".local" / "share" / "locksmith"
