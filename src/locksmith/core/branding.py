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


def _reference_theme() -> dict:
    return {
        "primary": "#F57B03",
        "primary_hover": "#D66A02",
        "primary_pressed": "#E67E00",
        "toolbar_dark": "#1A252C",
    }


@dataclass(frozen=True)
class Brand:
    # Every field below carries the reference Locksmith brand's own value as
    # its default, so the bare ``Brand()`` (no args) IS the reference brand —
    # matching the module-level promise that an unconfigured build is
    # Locksmith with zero setup. See ``_DEFAULT`` below.
    display_name: str = "Locksmith"
    tagline: str = "KERI identity vault"
    org_name: str = "keri.host"
    org_domain: str = "keri.host"
    website: str = "https://locksmith.app"
    support: str = "https://locksmith.app/support"
    id: str = "locksmith"
    appcast_macos_xml: str = "https://releases.keri.host/appcast/v1/macos.xml"
    appcast_windows_xml: str = "https://releases.keri.host/appcast/v1/windows.xml"
    theme: dict = field(default_factory=_reference_theme)
    # --- [bootstrap] section: first-run HOA defaults (Locksmith itself never
    # sets these — a non-HOA brand.toml simply omits [bootstrap] and every
    # field below stays at its safe, inert default). ---
    peel_core_pages: bool = False
    default_vault_name: str = ""
    default_passcode: str = ""
    default_aid_alias: str = ""
    default_witnesses: list[str] = field(default_factory=list)
    default_toad: int = 0


# The reference brand (#1). This is the SINGLE canonical hard-coded brand name.
_DEFAULT = Brand()


def _from_dict(doc: dict) -> Brand:
    bs = doc.get("bootstrap", {}) or {}
    return Brand(
        display_name=doc.get("display_name", _DEFAULT.display_name),
        tagline=doc.get("tagline", _DEFAULT.tagline),
        org_name=doc.get("org_name", _DEFAULT.org_name),
        org_domain=doc.get("org_domain", _DEFAULT.org_domain),
        website=doc.get("website", _DEFAULT.website),
        support=doc.get("support", _DEFAULT.support),
        id=doc.get("id", _DEFAULT.id),
        appcast_macos_xml=doc.get("appcast_macos_xml", _DEFAULT.appcast_macos_xml),
        appcast_windows_xml=doc.get("appcast_windows_xml", _DEFAULT.appcast_windows_xml),
        theme=dict(doc.get("theme", {})),
        peel_core_pages=bool(bs.get("peel_core_pages", False)),
        default_vault_name=bs.get("default_vault_name", ""),
        default_passcode=bs.get("default_passcode", ""),
        default_aid_alias=bs.get("default_aid_alias", ""),
        default_witnesses=list(bs.get("default_witnesses", [])),
        default_toad=int(bs.get("default_toad", 0)),
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
