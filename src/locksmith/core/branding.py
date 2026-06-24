# -*- encoding: utf-8 -*-
"""Runtime brand identity.

The white-label engine selects a brand at BUILD time; the running app reads a
small generated ``brand.json`` (display name, org, URLs, theme accent). This
module resolves that file the same way ``locksmith.release.deploy`` resolves
``deploy_config.json``: an env-injected path first, the packaged file next, and
finally a baked-in default. The default IS the Locksmith reference brand, so an
unconfigured dev build is Locksmith with zero setup.
"""
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BRAND_CONFIG_ENV_VAR = "LOCKSMITH_BRAND_CONFIG"

# Packaged runtime config, written by scripts/brand_apply.py (gitignored).
_PACKAGED_BRAND_JSON = Path(__file__).resolve().parents[1] / "release" / "brand.json"


@dataclass(frozen=True)
class Brand:
    display_name: str
    tagline: str
    org_name: str
    org_domain: str
    website: str
    support: str
    appcast_macos_xml: str = ""
    appcast_windows_xml: str = ""
    theme: dict = field(default_factory=dict)


# The reference brand (#1). This is the SINGLE canonical hard-coded brand name.
_DEFAULT = Brand(
    display_name="Locksmith",
    tagline="KERI identity vault",
    org_name="keri.host",
    org_domain="keri.host",
    website="https://locksmith.app",
    support="https://locksmith.app/support",
    appcast_macos_xml="https://releases.keri.host/appcast/v1/macos.xml",
    appcast_windows_xml="https://releases.keri.host/appcast/v1/windows.xml",
    theme={
        "primary": "#F57B03",
        "primary_hover": "#D66A02",
        "primary_pressed": "#E67E00",
        "toolbar_dark": "#1A252C",
    },
)


def _from_dict(doc: dict) -> Brand:
    return Brand(
        display_name=doc.get("display_name", _DEFAULT.display_name),
        tagline=doc.get("tagline", _DEFAULT.tagline),
        org_name=doc.get("org_name", _DEFAULT.org_name),
        org_domain=doc.get("org_domain", _DEFAULT.org_domain),
        website=doc.get("website", _DEFAULT.website),
        support=doc.get("support", _DEFAULT.support),
        appcast_macos_xml=doc.get("appcast_macos_xml", _DEFAULT.appcast_macos_xml),
        appcast_windows_xml=doc.get("appcast_windows_xml", _DEFAULT.appcast_windows_xml),
        theme=dict(doc.get("theme", {})),
    )


def load_brand() -> Brand:
    """Resolve the active brand (env-injection first, baked-in default last)."""
    env_path = os.environ.get(BRAND_CONFIG_ENV_VAR)
    if env_path:
        injected = Path(env_path)
        if injected.is_file():
            return _from_dict(json.loads(injected.read_text(encoding="utf-8")))
        raise FileNotFoundError(
            f"{BRAND_CONFIG_ENV_VAR} is set to {env_path!r} but no file exists "
            f"there (brand.json injection misconfigured)"
        )
    if _PACKAGED_BRAND_JSON.is_file():
        return _from_dict(json.loads(_PACKAGED_BRAND_JSON.read_text(encoding="utf-8")))
    return _DEFAULT


@lru_cache(maxsize=1)
def brand() -> Brand:
    """Cached active brand — use this everywhere in the app."""
    return load_brand()


def app_title(vault_name: str | None) -> str:
    """Window title: the brand name, optionally with an open vault appended."""
    name = brand().display_name
    return f"{name} | {vault_name}" if vault_name else name


def _reset_cache_for_tests() -> None:
    brand.cache_clear()
