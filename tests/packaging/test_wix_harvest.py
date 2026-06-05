"""Tests for packaging/wix/harvest.py — pure-Python WiX harvester."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
HARVEST = REPO_ROOT / "packaging" / "wix" / "harvest.py"
EXCLUSIONS = REPO_ROOT / "packaging" / "wix" / "heat-exclusions.txt"
NS = {"w": "http://wixtoolset.org/schemas/v4/wxs"}


def _build_fake_dist(root: Path) -> None:
    """Create a small dir layout that mirrors a real PyInstaller dist tree."""
    (root / "Locksmith.exe").write_bytes(b"\x4d\x5a")  # MZ header
    internal = root / "_internal"
    (internal / "PySide6").mkdir(parents=True)
    (internal / "PySide6" / "qt.conf").write_text("[Paths]\nPrefix = .\n")
    (internal / "assets").mkdir()
    (internal / "assets" / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (internal / "libsodium.dll").write_bytes(b"\x4d\x5a" + b"\x00" * 100)
    # Junk that should be excluded:
    (internal / "foo.pyc").write_bytes(b"bytecode")
    pycache = internal / "__pycache__"
    pycache.mkdir()
    (pycache / "bar.pyc").write_bytes(b"more bytecode")


def _run_harvest(source: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, str(HARVEST),
            "--source", str(source),
            "--out", str(out),
            "--exclusions", str(EXCLUSIONS),
        ],
        capture_output=True, text=True, check=True,
    )


def test_harvest_emits_well_formed_xml(tmp_path):
    src = tmp_path / "Locksmith"
    src.mkdir()
    _build_fake_dist(src)
    out = tmp_path / "harvest.wxs"
    _run_harvest(src, out)
    # XML must parse and be in the WiX v4 namespace.
    tree = ET.parse(out)
    root = tree.getroot()
    assert root.tag == f"{{{NS['w']}}}Wix"


def test_harvest_creates_componentgroup(tmp_path):
    src = tmp_path / "Locksmith"
    src.mkdir()
    _build_fake_dist(src)
    out = tmp_path / "harvest.wxs"
    _run_harvest(src, out)
    tree = ET.parse(out)
    group = tree.find(".//w:ComponentGroup", NS)
    assert group is not None
    assert group.attrib.get("Id") == "HarvestedComponents"


def test_harvest_excludes_pyc_and_pycache(tmp_path):
    src = tmp_path / "Locksmith"
    src.mkdir()
    _build_fake_dist(src)
    out = tmp_path / "harvest.wxs"
    _run_harvest(src, out)
    text = out.read_text(encoding="utf-8")
    assert "foo.pyc" not in text, "harvester should exclude *.pyc"
    assert "__pycache__" not in text, "harvester should exclude __pycache__"
    assert "bar.pyc" not in text


def test_harvest_includes_libsodium_and_exe(tmp_path):
    src = tmp_path / "Locksmith"
    src.mkdir()
    _build_fake_dist(src)
    out = tmp_path / "harvest.wxs"
    _run_harvest(src, out)
    text = out.read_text(encoding="utf-8")
    assert "Locksmith.exe" in text
    assert "libsodium.dll" in text


def test_harvest_guids_are_deterministic(tmp_path):
    src = tmp_path / "Locksmith"
    src.mkdir()
    _build_fake_dist(src)
    out1 = tmp_path / "a.wxs"
    out2 = tmp_path / "b.wxs"
    _run_harvest(src, out1)
    _run_harvest(src, out2)
    # File-content equality => GUIDs are stable across runs.
    assert out1.read_text() == out2.read_text()


def test_harvest_root_directoryref_is_install_folder(tmp_path):
    src = tmp_path / "Locksmith"
    src.mkdir()
    _build_fake_dist(src)
    out = tmp_path / "harvest.wxs"
    _run_harvest(src, out)
    tree = ET.parse(out)
    dref = tree.find(".//w:DirectoryRef", NS)
    assert dref is not None
    assert dref.attrib.get("Id") == "INSTALLFOLDER"
