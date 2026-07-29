"""Lint checks for the WiX authoring template (packaging/wix/Locksmith.wxs.in).

Static-only — does not invoke the wix CLI. The end-to-end MSI build is
exercised in CI on a Windows runner.

Locksmith.wxs itself is no longer a tracked file (scripts/brand_apply.py
renders it per-brand into the brand release dir, gitignored — see the
atomic-brand-bundles refactor). These lint checks render the locksmith
brand's wxs in-memory from the template so they stay fresh-clone-safe
(no dependency on a stray on-disk render).
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WIX_DIR = REPO_ROOT / "packaging" / "wix"
LICENSE_RTF = WIX_DIR / "license.rtf"
HEAT_EXCLUSIONS = WIX_DIR / "heat-exclusions.txt"

NS = {
    "w": "http://wixtoolset.org/schemas/v4/wxs",
    "ui": "http://wixtoolset.org/schemas/v4/wxs/ui",
}


def _render_wxs() -> str:
    sys.path.insert(0, str(REPO_ROOT / "packaging"))
    import brandlib
    template = (WIX_DIR / "Locksmith.wxs.in").read_text(encoding="utf-8")
    return brandlib.render_wxs(brandlib.load_brand_manifest("locksmith"), template)


@pytest.fixture(scope="module")
def wxs_tree():
    return ET.ElementTree(ET.fromstring(_render_wxs()))


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
    """Only genuinely brand-NEUTRAL wix assets live here.

    banner.png/dialog.png are brand art and are rendered per-brand into the
    brand's release dir at build time (packaging/wix/gen_ui_images.py via
    scripts/brand_apply.py) — covered by tests/packaging/test_wix_brand_images.py.
    """
    assert LICENSE_RTF.is_file(), f"missing {LICENSE_RTF}"


def test_heat_exclusions_present_and_nontrivial():
    assert HEAT_EXCLUSIONS.is_file()
    lines = [
        ln.strip() for ln in HEAT_EXCLUSIONS.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert "__pycache__" in lines
    assert "*.pyc" in lines


def test_no_hardcoded_changeme_strings():
    assert "CHANGEME" not in _render_wxs().upper()


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


def test_chrome_bitmaps_are_referenced_by_bare_name(wxs_tree):
    """Bare names let `wix build`'s bindpath order pick the BRAND's rendered
    chrome out of its release dir. Dimensions + per-brand art: see
    tests/packaging/test_wix_brand_images.py."""
    variables = {v.attrib["Id"]: v.attrib.get("Value")
                 for v in wxs_tree.findall(".//w:WixVariable", NS)}
    assert variables.get("WixUIBannerBmp") == "banner.png"
    assert variables.get("WixUIDialogBmp") == "dialog.png"
