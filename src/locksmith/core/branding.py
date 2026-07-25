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
    # JSON feeds — what the in-app KERI verify gate replays against
    # (``update/cli.py:_appcast_url``). MUST be the brand's own feed:
    # deploy_config.json is shared across brands and points at locksmith's, so a
    # non-locksmith brand verifying against it reads a `locksmith` seal and fails
    # the brand check ("update could not be verified").
    appcast_macos: str = "https://releases.keri.host/appcast/v1/macos.json"
    appcast_windows: str = "https://releases.keri.host/appcast/v1/windows.json"
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
    # --- [plugins] section: which bundled-only in-tree plugins (see
    # plugins/manager.py's BUNDLED_ONLY_PLUGIN_IDS) this brand activates.
    # Which surfaces a brand composes is brand config, never a framework
    # hardcode (HOA #4) — a non-HOA brand.toml simply omits [plugins] and
    # stays at this empty, inert default. ---
    bundled_plugins: tuple[str, ...] = ()
    # --- [egf] / [onboarding] sections: which ecosystem-governance-framework
    # doc a brand pins and whether the HOA onboarding flow is exposed. A
    # non-onboarding brand simply omits both tables and stays at these inert
    # defaults (library default accept_phases is production-only; a brand
    # opts into "bootstrap" explicitly for pilot use). ---
    egf_source: str = "local"
    egf_document_said: str = ""
    egf_accept_phases: tuple[str, ...] = ("production",)
    onboarding_enabled: bool = False


# The reference brand (#1). This is the SINGLE canonical hard-coded brand name.
_DEFAULT = Brand()

# Directory the active brand's doc (brand.json or the packaged default) was
# resolved from, recorded by load_brand() — None until load_brand() has run,
# or when it fell back to the hard-coded _DEFAULT with no file at all. Lets
# egf_local_dir() find the `egf/` dir bundled alongside that same source.
_brand_source_dir: Path | None = None


def _from_dict(doc: dict) -> Brand:
    bs = doc.get("bootstrap", {}) or {}
    pl = doc.get("plugins", {}) or {}
    eg = doc.get("egf", {}) or {}
    ob = doc.get("onboarding", {}) or {}
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
        appcast_macos=doc.get("appcast_macos", _DEFAULT.appcast_macos),
        appcast_windows=doc.get("appcast_windows", _DEFAULT.appcast_windows),
        theme=dict(doc.get("theme", {})),
        peel_core_pages=bool(bs.get("peel_core_pages", False)),
        default_vault_name=bs.get("default_vault_name", ""),
        default_passcode=bs.get("default_passcode", ""),
        default_aid_alias=bs.get("default_aid_alias", ""),
        default_witnesses=list(bs.get("default_witnesses", [])),
        default_toad=int(bs.get("default_toad", 0)),
        bundled_plugins=tuple(pl.get("bundled", [])),
        egf_source=eg.get("source", _DEFAULT.egf_source),
        egf_document_said=eg.get("document_said", _DEFAULT.egf_document_said),
        egf_accept_phases=tuple(eg.get("accept_phases", _DEFAULT.egf_accept_phases)),
        onboarding_enabled=bool(ob.get("enabled", _DEFAULT.onboarding_enabled)),
    )


def load_brand() -> Brand:
    """Resolve the active brand (env-injection first, baked-in default last)."""
    global _brand_source_dir
    env_path = os.environ.get(BRAND_CONFIG_ENV_VAR)
    if env_path:
        injected = Path(env_path)
        if injected.is_file():
            _brand_source_dir = injected.resolve().parent
            return _from_dict(json.loads(injected.read_text(encoding="utf-8")))
        raise FileNotFoundError(
            f"{BRAND_CONFIG_ENV_VAR} is set to {env_path!r} but no file exists "
            f"there (brand.json injection misconfigured)"
        )
    if _PACKAGED_BRAND_JSON.is_file():
        _brand_source_dir = _PACKAGED_BRAND_JSON.resolve().parent
        return _from_dict(json.loads(_PACKAGED_BRAND_JSON.read_text(encoding="utf-8")))
    _brand_source_dir = None
    return _DEFAULT


@lru_cache(maxsize=1)
def brand() -> Brand:
    """Cached active brand — use this everywhere in the app."""
    return load_brand()


def app_title(vault_name: str | None) -> str:
    """Window title: the brand name, optionally with an open vault appended."""
    name = brand().display_name
    return f"{name} | {vault_name}" if vault_name else name


def egf_local_dir() -> Path | None:
    """The `egf/` dir bundled alongside the resolved brand source, or None.

    Sibling to whichever file load_brand() actually read (the env-injected
    brand.json's parent dir, or the packaged release/ dir) — so this resolves
    the same way whether running from a packaged build or with
    LOCKSMITH_BRAND_CONFIG pointed at a brand's staged brand.json. None when
    load_brand() hasn't run yet, fell back to the hard-coded default (no file
    at all), or the source dir simply has no egf/ subdirectory.
    """
    if _brand_source_dir is None:
        return None
    candidate = _brand_source_dir / "egf"
    return candidate if candidate.is_dir() else None


def brand_source_dir() -> Path | None:
    """Directory the active brand was resolved from (populated by load_brand)."""
    return _brand_source_dir


def brand_assets_rcc() -> Path | None:
    """The compiled Qt bundle sibling to the resolved brand source, or None."""
    if _brand_source_dir is None:
        return None
    candidate = _brand_source_dir / "assets.rcc"
    return candidate if candidate.is_file() else None


def register_brand_resources() -> Path:
    """Register the active brand's assets.rcc — the single atomic asset surface.

    Must run before any ``:/assets/*`` access. Ensures the brand source dir is
    resolved (via ``brand()``), then registers ``<dir>/assets.rcc`` so logos,
    splash, fonts AND config all come from the same brand source. Raises
    ``RuntimeError`` when no bundle is found (a partial/unbranded state is not
    allowed to boot) or when Qt registration fails.
    """
    from PySide6.QtCore import QResource
    brand()  # populate _brand_source_dir as a side effect
    rcc = brand_assets_rcc()
    if rcc is None:
        raise RuntimeError(
            "No brand asset bundle (assets.rcc) found. Build one with "
            "`python scripts/brand_apply.py --brand locksmith` (writes "
            "src/locksmith/release/assets.rcc), or point LOCKSMITH_BRAND_CONFIG "
            "at a brand.json whose directory contains assets.rcc."
        )
    if not QResource.registerResource(str(rcc)):
        raise RuntimeError(f"Failed to register brand asset bundle: {rcc}")
    global _registered_rcc
    _registered_rcc = rcc
    return rcc


_registered_rcc: Path | None = None


def unregister_brand_resources() -> None:
    """Detach the bundle registered by register_brand_resources() (test isolation).

    No-op if nothing is registered. The running app never needs this; tests use
    it to reset between brand switches (Qt resource overlap is first-wins).
    """
    global _registered_rcc
    if _registered_rcc is not None:
        from PySide6.QtCore import QResource
        QResource.unregisterResource(str(_registered_rcc))
        _registered_rcc = None


def _reset_cache_for_tests() -> None:
    global _brand_source_dir
    unregister_brand_resources()
    brand.cache_clear()
    _brand_source_dir = None
