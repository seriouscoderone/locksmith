from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MACOS = REPO / "packaging" / "build-macos.sh"
WINDOWS = REPO / "packaging" / "build-windows.ps1"


def test_macos_resolves_brand_names():
    s = MACOS.read_text()
    # Resolves app name + artifact prefix from brandlib (no hardcoded product).
    assert "brandlib" in s
    assert "APP_NAME" in s and "ARTIFACT_PREFIX" in s


def test_macos_no_hardcoded_app_or_dmg_name():
    s = MACOS.read_text()
    # The literal build outputs must be brand-derived, not "Locksmith.app" /
    # "Locksmith-<v>.dmg". Comments may still say Locksmith; code must not.
    code = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))
    assert 'dist/Locksmith.app' not in code
    assert 'Locksmith-${VERSION}.dmg' not in code
    assert '"Locksmith"' not in code  # --volname etc.


def test_windows_resolves_brand_names():
    s = WINDOWS.read_text()
    assert "brandlib" in s
    assert "AppName" in s and "ArtifactPrefix" in s


def test_windows_no_hardcoded_exe_or_msi_name():
    s = WINDOWS.read_text()
    code = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))
    assert 'dist\\Locksmith' not in code
    assert 'Locksmith.exe' not in code
    assert 'Locksmith-$Version.msi' not in code
