"""Static checks on packaging/Locksmith.windows.spec for WinSparkle integration."""
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = _REPO_ROOT / "packaging" / "Locksmith.windows.spec"


def test_windows_spec_bundles_winsparkle_dll():
    spec = _SPEC.read_text()
    assert "WinSparkle.dll" in spec


def test_windows_spec_documents_appcast_url():
    """The runtime URL is set by winsparkle_init.py, but document it here."""
    spec = _SPEC.read_text()
    assert "releases.keri.host/appcast/v1/windows.xml" in spec


def test_windows_spec_calls_out_dsa_verification_disabled():
    """KERI is the sole trust mechanism (spec §3); make that visible in the spec."""
    spec = _SPEC.read_text()
    assert "dsa_pub_pem(NULL)" in spec or "set_dsa_pub_pem" in spec
