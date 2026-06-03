"""pyproject.toml must declare build-macos optional dependencies."""
from pathlib import Path
import tomllib

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_build_macos_group_exists():
    data = tomllib.loads(PYPROJECT.read_text())
    opt = data["project"].get("optional-dependencies", {})
    assert "build-macos" in opt, "missing [project.optional-dependencies].build-macos"


def test_build_macos_includes_pyinstaller():
    data = tomllib.loads(PYPROJECT.read_text())
    deps = data["project"]["optional-dependencies"]["build-macos"]
    assert any(d.startswith("pyinstaller") for d in deps), deps
