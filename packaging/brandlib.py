# -*- encoding: utf-8 -*-
"""Build-time brand manifest reader.

Read by scripts/brand_apply.py and by the PyInstaller specs to resolve the
active brand's identity from brands/<brand>/brand.toml. The runtime app does
NOT use this module — it reads the generated brand.json via
locksmith.core.branding. Selection: $LOCKSMITH_BRAND (default 'locksmith').
"""
import os
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BRANDS_DIR = REPO_ROOT / "brands"
DEFAULT_BRAND = "locksmith"
FALLBACK_BRAND = "example"


def active_brand_id() -> str:
    return os.environ.get("LOCKSMITH_BRAND", DEFAULT_BRAND)


def load_brand_manifest(brand_id: str | None = None) -> dict:
    """Parse brands/<brand>/brand.toml; fall back to brands/example if absent."""
    bid = brand_id or active_brand_id()
    brand_dir = BRANDS_DIR / bid
    if not (brand_dir / "brand.toml").is_file():
        brand_dir = BRANDS_DIR / FALLBACK_BRAND
    manifest = tomllib.loads((brand_dir / "brand.toml").read_text(encoding="utf-8"))
    manifest["_dir"] = brand_dir
    return manifest


def _org_name(manifest: dict) -> str:
    return manifest.get("org", {}).get("name") or manifest["identity"]["org_domain"]


def runtime_brand_json(manifest: dict) -> dict:
    """The brand.json runtime subset consumed by locksmith.core.branding."""
    return {
        "display_name": manifest["brand"]["display_name"],
        "tagline": manifest["brand"]["tagline"],
        "org_name": _org_name(manifest),
        "org_domain": manifest["identity"]["org_domain"],
        "website": manifest["urls"]["website"],
        "support": manifest["urls"]["support"],
        "theme": dict(manifest.get("theme", {})),
    }


def exe_name(manifest: dict) -> str:
    return manifest["brand"]["display_name"]


def macos_info_plist(manifest: dict, version: str) -> dict:
    name = manifest["brand"]["display_name"]
    return {
        "CFBundleName": name,
        "CFBundleDisplayName": name,
        "CFBundleIdentifier": manifest["identity"]["bundle_id"],
        "CFBundleVersion": version,
        "CFBundleShortVersionString": version,
        "CFBundleExecutable": name,
        "CFBundlePackageType": "APPL",
        "CFBundleSupportedPlatforms": ["MacOSX"],
        "CFBundleDevelopmentRegion": "en",
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "13.0",
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": True,
        "SUFeedURL": manifest["urls"]["appcast_macos"],
        "SUEnableInstallerLauncherService": True,
        "SUEnableAutomaticChecks": False,
        "SUEnableDownloaderService": False,
        "NSAppTransportSecurity": {
            "NSAllowsArbitraryLoads": False,
            "NSExceptionDomains": {},
        },
    }
