"""Static check that sign.sh targets the new PyInstaller layout."""
from pathlib import Path

SIGN = Path(__file__).resolve().parents[2] / "scripts" / "sign.sh"


def test_no_flutter_paths():
    s = SIGN.read_text()
    assert "flutter_assets" not in s
    assert "App.framework" not in s


def test_uses_developer_id_app_cert_env():
    s = SIGN.read_text()
    assert "DEVELOPER_ID_APP_CERT" in s


def test_runs_codesign_deep_options_runtime():
    s = SIGN.read_text()
    assert "--options runtime" in s
    assert "--deep" in s


def test_uses_entitlements_plist():
    s = SIGN.read_text()
    assert "entitlements.plist" in s


def test_targets_locksmith_app():
    s = SIGN.read_text()
    assert "Locksmith.app" in s
