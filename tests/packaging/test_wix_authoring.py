"""Lint checks for packaging/wix/Locksmith.wxs.

Static-only — does not invoke the wix CLI. The end-to-end MSI build is
exercised in CI on a Windows runner.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WIX_DIR = REPO_ROOT / "packaging" / "wix"
WXS = WIX_DIR / "Locksmith.wxs"
LICENSE_RTF = WIX_DIR / "license.rtf"
BANNER = WIX_DIR / "banner.png"
DIALOG = WIX_DIR / "dialog.png"
HEAT_EXCLUSIONS = WIX_DIR / "heat-exclusions.txt"

NS = {
    "w": "http://wixtoolset.org/schemas/v4/wxs",
    "ui": "http://wixtoolset.org/schemas/v4/wxs/ui",
}


@pytest.fixture(scope="module")
def wxs_tree():
    return ET.parse(WXS)


def test_wxs_is_well_formed(wxs_tree):
    root = wxs_tree.getroot()
    assert root.tag.endswith("}Wix"), f"unexpected root: {root.tag}"


def test_package_has_perUser_scope(wxs_tree):
    pkg = wxs_tree.find("w:Package", NS)
    assert pkg is not None, "no Package element"
    assert pkg.attrib.get("Scope") == "perUser", f"Scope={pkg.attrib.get('Scope')}"


def test_upgrade_code_is_immutable_guid(wxs_tree):
    pkg = wxs_tree.find("w:Package", NS)
    upgrade_code = pkg.attrib.get("UpgradeCode", "")
    # Must be a real GUID, not a placeholder.
    assert upgrade_code, "UpgradeCode missing"
    assert "<" not in upgrade_code, "UpgradeCode is still a placeholder"
    parsed = uuid.UUID(upgrade_code)
    assert str(parsed).upper() == upgrade_code.upper(), "UpgradeCode case mismatch"


def test_version_uses_variable(wxs_tree):
    pkg = wxs_tree.find("w:Package", NS)
    assert pkg.attrib.get("Version") == "$(var.Version)", (
        "Version should be the WiX variable, not hardcoded"
    )


def test_install_path_is_localappdata(wxs_tree):
    # INSTALLFOLDER must nest under LocalAppDataFolder so install is per-user.
    std = wxs_tree.find(".//w:StandardDirectory[@Id='LocalAppDataFolder']", NS)
    assert std is not None, "LocalAppDataFolder StandardDirectory missing"
    install = std.find(".//w:Directory[@Id='INSTALLFOLDER']", NS)
    assert install is not None, "INSTALLFOLDER not nested under LocalAppDataFolder"


def test_major_upgrade_block_present(wxs_tree):
    major = wxs_tree.find(".//w:MajorUpgrade", NS)
    assert major is not None, "MajorUpgrade element missing"
    assert major.attrib.get("AllowSameVersionUpgrades") == "yes"


def test_referenced_files_exist():
    assert LICENSE_RTF.is_file(), f"missing {LICENSE_RTF}"
    assert BANNER.is_file(), f"missing {BANNER}"
    assert DIALOG.is_file(), f"missing {DIALOG}"


def test_heat_exclusions_present_and_nontrivial():
    assert HEAT_EXCLUSIONS.is_file()
    lines = [
        ln.strip() for ln in HEAT_EXCLUSIONS.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert "__pycache__" in lines
    assert "*.pyc" in lines


def test_no_hardcoded_changeme_strings():
    text = WXS.read_text(encoding="utf-8")
    assert "CHANGEME" not in text.upper()


def test_manufacturer_is_keri_host(wxs_tree):
    pkg = wxs_tree.find("w:Package", NS)
    assert pkg.attrib.get("Manufacturer") == "KERI.host"


def test_arp_no_repair_set(wxs_tree):
    # The Add/Remove Programs entry should not offer Repair.
    # (ARPNOMODIFY is set by WixUI_InstallDir; we don't redefine it.)
    props = {p.attrib["Id"]: p.attrib.get("Value") for p in wxs_tree.findall(".//w:Property", NS)}
    assert props.get("ARPNOREPAIR") == "1"


def test_wix_ui_installdir_is_used(wxs_tree):
    ui = wxs_tree.find(".//ui:WixUI", NS)
    assert ui is not None, "WixUI element missing"
    assert ui.attrib.get("Id") == "WixUI_InstallDir"


def test_banner_dimensions():
    from PIL import Image
    with Image.open(BANNER) as img:
        assert img.size == (493, 58), f"banner {img.size} != (493, 58)"


def test_dialog_dimensions():
    from PIL import Image
    with Image.open(DIALOG) as img:
        assert img.size == (493, 312), f"dialog {img.size} != (493, 312)"
