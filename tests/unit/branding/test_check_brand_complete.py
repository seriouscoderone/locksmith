import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
cbc = importlib.import_module("check_brand_complete")


def _write_brand(tmp, bid, *, urls_ok=True, reuse_locksmith=False,
                 with_assets=True, with_anchor=True):
    bdir = tmp / "brands" / bid
    bdir.mkdir(parents=True)
    website = "https://acme.test" if urls_ok else "https://example.com"
    bundle = "host.keri.locksmith" if reuse_locksmith else "com.acme.vault"
    upgrade = ("297BBF26-821C-4D56-8857-309C7B531E21" if reuse_locksmith
               else "11111111-2222-3333-4444-555555555555")
    (bdir / "brand.toml").write_text(f'''
[brand]
id = "{bid}"
display_name = "Acme"
tagline = "vault"
manufacturer = "Acme"
[identity]
bundle_id = "{bundle}"
upgrade_code = "{upgrade}"
data_dir = "Acme"
artifact_prefix = "Acme"
org_domain = "acme.test"
[urls]
website = "{website}"
support = "{website}/support"
appcast_macos = "{website}/appcast/v1/macos.json"
appcast_windows = "{website}/appcast/v1/windows.json"
[theme]
primary = "#112233"
[assets]
app_icon_icns = "AppIcon.icns"
[publisher]
anchor = "publisher_anchor.json"
deploy_config = "deploy_config.json"
''')
    if with_assets:
        (bdir / "AppIcon.icns").write_text("x")
    if with_anchor:
        (bdir / "publisher_anchor.json").write_text(
            '{"publisher_aid": "EReal", "witness_oobis": ["https://w/oobi"]}')
    return tmp


def test_clean_brand_passes(tmp_path):
    _write_brand(tmp_path, "acme")
    assert cbc.validate("acme", tmp_path / "brands") == []


def test_placeholder_url_rejected(tmp_path):
    _write_brand(tmp_path, "acme", urls_ok=False)
    probs = cbc.validate("acme", tmp_path / "brands")
    assert any("example.com" in p for p in probs)


def test_reusing_locksmith_identity_rejected(tmp_path):
    _write_brand(tmp_path, "acme", reuse_locksmith=True)
    probs = cbc.validate("acme", tmp_path / "brands")
    assert any("Locksmith" in p or "host.keri.locksmith" in p for p in probs)


def test_missing_asset_rejected(tmp_path):
    _write_brand(tmp_path, "acme", with_assets=False)
    probs = cbc.validate("acme", tmp_path / "brands")
    assert any("AppIcon.icns" in p for p in probs)


def test_missing_anchor_rejected(tmp_path):
    _write_brand(tmp_path, "acme", with_anchor=False)
    probs = cbc.validate("acme", tmp_path / "brands")
    assert any("anchor" in p.lower() for p in probs)
