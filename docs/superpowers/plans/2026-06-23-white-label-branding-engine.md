# White-Label Branding Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Locksmith a reusable white-label engine — one codebase that builds into several independently-branded desktop apps from a per-brand manifest — with Locksmith itself as the reference brand reproducing today's app exactly.

**Architecture:** A per-brand `brands/<brand>/brand.toml` is the single source of truth. At runtime the app reads a small generated `brand.json` (display name, org, URLs, theme accent) via a loader mirroring `release/deploy.py`, falling back to a baked-in Locksmith default. At build time `scripts/brand_apply.py` reads the manifest (via `packaging/brandlib.py`), stages assets over `assets/custom/`, renders the WiX `.wxs` + DMG `layout.json`, writes `brand.json`, and injects the brand's trust material; the PyInstaller specs and the publisher CLI read the active brand. A fail-closed validator (`check-brand-complete.py`) guards release builds.

**Tech Stack:** Python 3.11+ (`tomllib`), PySide6 (Qt), PyInstaller `.spec`, WiX v4, Click (publisher CLI), pytest.

## Global Constraints

- **Run tests with `--import-mode=importlib`** from the repo root venv: `.venv/bin/python -m pytest <path> -q --import-mode=importlib` (the top-level `packaging/` dir otherwise shadows the `packaging` library). Publisher tests run from `tools/publisher/`.
- **Privacy rule:** no real personal AIDs/federation in committed files. Per-brand **trust material** (`publisher_anchor.json`, `deploy_config.json`) is gitignored in every brand dir; `brands/example/` carries only `example.com` placeholders. `brands/locksmith/brand.toml` + the canonical `assets/custom/` ARE committed (their values already appear in today's committed packaging — no new disclosure).
- **Immutable-per-brand identity** (never change post-release): `bundle_id`, `upgrade_code` (mint a NEW GUID per brand), `data_dir`, `artifact_prefix`, `appcast_*` URLs.
- **Locksmith reference values (pin these — the keystone test asserts them):** display name `Locksmith`, manufacturer `KERI.host`, bundle id `host.keri.locksmith`, WiX UpgradeCode `297BBF26-821C-4D56-8857-309C7B531E21`, data dir `Locksmith`, artifact prefix `Locksmith`, website `https://locksmith.app`, support `https://locksmith.app/support`, appcast `https://releases.keri.host/appcast/v1/{macos,windows}.json`, theme primary `#F57B03` / hover `#D66A02` / pressed `#E67E00` / toolbar_dark `#1A252C`, org name `keri.host`, org domain `keri.host`.
- **Module placement:** runtime loader at `src/locksmith/core/branding.py` (per spec); build-time manifest reader at `packaging/brandlib.py`. The runtime loader mirrors the resolution order of `src/locksmith/release/deploy.py:load_deploy_config`.
- **Brand selection:** build/runtime brand chosen by `$LOCKSMITH_BRAND` (default `locksmith`); runtime config injected via `$LOCKSMITH_BRAND_CONFIG` → packaged `release/brand.json` → baked-in Locksmith default.
- DRY, YAGNI, TDD, frequent commits.

**Scope:** Phases 1 (runtime) + 2 (build). **Out of scope (Phase 3, gated on a real second brand's infra):** renaming the platform build-script output files (`build-macos.sh`/`build-windows.ps1` only diverge from `Locksmith-{version}` for a non-Locksmith brand), running a real second brand's publisher ceremony, and publishing a second edition. Also out: runtime brand-switching, cross-brand data migration, auto-minting UpgradeCode, localization, brand-management UI.

**Phase-3 pipeline-integration follow-on (tracked — built here, wired there).** Phases 1+2 deliver `scripts/brand_apply.py` and `scripts/check-brand-complete.py` as working, tested tools, but they are NOT yet invoked by CI or the build scripts. Wiring them is deferred to Phase 3 (alongside the build-script artifact rename) because it requires reconciling where each brand's trust material lives: the guard reads `brands/<brand>/publisher_anchor.json`, while today's `release.ci.yml` injects the anchor to `src/locksmith/release/publisher_anchor.json` — and `brand_apply` is what copies the former to the latter. The coherent Phase-3 CI sequence is: inject (or run `brand_apply` to stage) the brand's trust material → run `check-brand-complete --brand $LOCKSMITH_BRAND` (mirroring how `check-anchor-present.py` is already wired at `release.ci.yml`) → `brand_apply` → platform build. For brand #1 (`locksmith`) this is no regression: the existing `check-anchor-present.py` already gates the anchor in CI, so the locksmith release is not unprotected. Also tracked for Phase 3 (completeness, not enumerated in the Phase-1/2 surface): branding the remaining UI prose strings that still say "Locksmith" (`dialogs/update_consent.py`, `dialogs/verification_log.py`, `vault/settings/updates_widget.py`, `plugins/upgrade_banner.py`, `vault/settings/page.py` "Locksmith Identifier", `otping.py` TOTP issuer); consuming `Brand.website`/`Brand.support` in the About panel; the guard also flagging placeholder `appcast_*` URLs and cross-checking the injected anchor's `publisher_aid` belongs to the brand; and shipping `brands/example/` as a complete copy-paste starter (placeholder asset files + `*.example.json` trust templates).

---

### Task 1: Runtime brand loader (`core/branding.py`)

**Files:**
- Create: `src/locksmith/core/branding.py`
- Create: `tests/unit/branding/__init__.py`
- Create: `tests/unit/branding/test_branding_loader.py`
- Modify: `.gitignore` (add the generated runtime `brand.json`)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Brand` with fields `display_name: str`, `tagline: str`, `org_name: str`, `org_domain: str`, `website: str`, `support: str`, `theme: dict[str, str]`.
  - `load_brand() -> Brand` — resolution order: `$LOCKSMITH_BRAND_CONFIG` path → packaged `src/locksmith/release/brand.json` → baked-in `_DEFAULT` (Locksmith). Raises `FileNotFoundError` only when `$LOCKSMITH_BRAND_CONFIG` points at a missing file.
  - `brand() -> Brand` — cached (`functools.lru_cache`) accessor used everywhere in the app.
  - `app_title(vault_name: str | None) -> str` — returns `display_name` when `vault_name` is falsy, else `f"{display_name} | {vault_name}"`.
  - `_reset_cache_for_tests() -> None` — clears the `brand()` cache (tests only).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/branding/__init__.py` (empty), then `tests/unit/branding/test_branding_loader.py`:

```python
import json
import importlib

import pytest

branding = importlib.import_module("locksmith.core.branding")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("LOCKSMITH_BRAND_CONFIG", raising=False)
    branding._reset_cache_for_tests()
    yield
    branding._reset_cache_for_tests()


def test_default_is_locksmith():
    b = branding.load_brand()
    assert b.display_name == "Locksmith"
    assert b.org_name == "keri.host"
    assert b.org_domain == "keri.host"
    assert b.website == "https://locksmith.app"
    assert b.support == "https://locksmith.app/support"
    assert b.theme["primary"] == "#F57B03"


def test_env_override(tmp_path, monkeypatch):
    cfg = tmp_path / "brand.json"
    cfg.write_text(json.dumps({
        "display_name": "Acme Vault", "tagline": "secure keys",
        "org_name": "acme.example.com", "org_domain": "acme.example.com",
        "website": "https://acme.example.com",
        "support": "https://acme.example.com/help",
        "theme": {"primary": "#112233"},
    }))
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(cfg))
    branding._reset_cache_for_tests()
    b = branding.brand()
    assert b.display_name == "Acme Vault"
    assert b.theme["primary"] == "#112233"


def test_env_path_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(tmp_path / "nope.json"))
    branding._reset_cache_for_tests()
    with pytest.raises(FileNotFoundError):
        branding.load_brand()


def test_brand_is_cached(monkeypatch):
    assert branding.brand() is branding.brand()


def test_app_title():
    assert branding.app_title(None) == "Locksmith"
    assert branding.app_title("") == "Locksmith"
    assert branding.app_title("Personal") == "Locksmith | Personal"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_branding_loader.py -q --import-mode=importlib`
Expected: FAIL — `ModuleNotFoundError: No module named 'locksmith.core.branding'`.

- [ ] **Step 3: Implement `core/branding.py`**

Create `src/locksmith/core/branding.py`:

```python
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
    theme: dict = field(default_factory=dict)


# The reference brand (#1). This is the SINGLE canonical hard-coded brand name.
_DEFAULT = Brand(
    display_name="Locksmith",
    tagline="KERI identity vault",
    org_name="keri.host",
    org_domain="keri.host",
    website="https://locksmith.app",
    support="https://locksmith.app/support",
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
```

- [ ] **Step 4: Add the gitignore entry for the generated runtime config**

Add to `.gitignore` immediately after the `deploy_config.json` block (after line 200, before the `/out/` block):

```gitignore
# Runtime brand config — generated by scripts/brand_apply.py from the active
# brand's brand.toml. The committed default lives in code
# (locksmith.core.branding._DEFAULT == the Locksmith reference brand); a
# white-label build writes this file to override it. Never committed.
# See locksmith.core.branding.load_brand.
src/locksmith/release/brand.json
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_branding_loader.py -q --import-mode=importlib`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/core/branding.py tests/unit/branding/__init__.py tests/unit/branding/test_branding_loader.py .gitignore
git commit -m "feat(brand): runtime brand loader + app_title helper (default=Locksmith)"
```

---

### Task 2: Theme accent overrides (`ui/colors.py`)

**Files:**
- Modify: `src/locksmith/ui/colors.py` (append an override function)
- Create: `tests/unit/branding/test_color_overrides.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `apply_theme_overrides(theme: dict[str, str]) -> None` in `locksmith.ui.colors` — maps brand theme keys onto module-level accent constants and rebuilds nothing else. Mapping: `primary→PRIMARY`, `primary_hover→PRIMARY_HOVER`, `primary_pressed→PRIMARY_PRESSED`, `toolbar_dark→TOOLBAR_DARK`. Unknown keys are ignored. Missing keys leave the default.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/branding/test_color_overrides.py`:

```python
import importlib

import pytest

colors = importlib.import_module("locksmith.ui.colors")


@pytest.fixture(autouse=True)
def _restore_defaults():
    saved = {k: getattr(colors, k) for k in
             ("PRIMARY", "PRIMARY_HOVER", "PRIMARY_PRESSED", "TOOLBAR_DARK",
              "BACKGROUND_WINDOW", "DANGER")}
    yield
    for k, v in saved.items():
        setattr(colors, k, v)


def test_overrides_accent_only():
    colors.apply_theme_overrides({
        "primary": "#112233", "primary_hover": "#0A1722",
        "primary_pressed": "#2A4458", "toolbar_dark": "#000010",
    })
    assert colors.PRIMARY == "#112233"
    assert colors.PRIMARY_HOVER == "#0A1722"
    assert colors.PRIMARY_PRESSED == "#2A4458"
    assert colors.TOOLBAR_DARK == "#000010"
    # neutrals / semantic colors are untouched
    assert colors.BACKGROUND_WINDOW == "#F2F3FA"
    assert colors.DANGER == "#DC2626"


def test_missing_keys_leave_defaults():
    before = colors.PRIMARY_HOVER
    colors.apply_theme_overrides({"primary": "#999999"})
    assert colors.PRIMARY == "#999999"
    assert colors.PRIMARY_HOVER == before


def test_unknown_keys_ignored():
    colors.apply_theme_overrides({"banana": "#FFFFFF"})
    assert not hasattr(colors, "banana")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_color_overrides.py -q --import-mode=importlib`
Expected: FAIL — `AttributeError: module 'locksmith.ui.colors' has no attribute 'apply_theme_overrides'`.

- [ ] **Step 3: Implement the override function**

Append to `src/locksmith/ui/colors.py` (after the `TOOLBAR_DARK` line at the end of the file):

```python


# =============================================================================
# Per-brand theme overrides
# =============================================================================
# Maps brand.toml [theme] keys → the module-level accent constants above. Only
# the accent set is brandable; neutrals and semantic (danger/success) colors are
# shared across all brands. Called once at startup BEFORE the QSS is built.
_THEME_KEY_TO_CONST = {
    "primary": "PRIMARY",
    "primary_hover": "PRIMARY_HOVER",
    "primary_pressed": "PRIMARY_PRESSED",
    "toolbar_dark": "TOOLBAR_DARK",
}


def apply_theme_overrides(theme: dict) -> None:
    """Overwrite the accent constants from a brand's theme dict (in place)."""
    g = globals()
    for key, const_name in _THEME_KEY_TO_CONST.items():
        value = theme.get(key)
        if value:
            g[const_name] = value
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_color_overrides.py -q --import-mode=importlib`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/ui/colors.py tests/unit/branding/test_color_overrides.py
git commit -m "feat(brand): per-brand accent theme overrides in ui.colors"
```

---

### Task 3: Wire runtime branding into the UI

**Files:**
- Modify: `src/locksmith/ui/styles.py:52-69` (app name/org/domain + apply theme overrides)
- Modify: `src/locksmith/ui/window.py:58` and `:612` (window titles)
- Modify: `src/locksmith/ui/vaults/drawer.py:735` (vault-open title)
- Modify: `src/locksmith/ui/toolbar.py:101` (toolbar wordmark)
- Modify: `src/locksmith/core/configing.py:50` (remove dead `appName`)
- Create: `tests/unit/branding/test_styles_branding.py`

**Interfaces:**
- Consumes: `locksmith.core.branding.brand`, `locksmith.core.branding.app_title`, `locksmith.ui.colors.apply_theme_overrides`.
- Produces: no new public API; `set_global_styles` now applies brand identity + theme.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/branding/test_styles_branding.py`:

```python
import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

branding = importlib.import_module("locksmith.core.branding")


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication
    inst = QApplication.instance() or QApplication([])
    yield inst


def test_set_global_styles_applies_brand_identity(app):
    from locksmith.ui import styles
    branding._reset_cache_for_tests()
    styles.set_global_styles(app)
    assert app.applicationName() == branding.brand().display_name == "Locksmith"
    assert app.organizationName() == branding.brand().org_name == "keri.host"
    assert app.organizationDomain() == branding.brand().org_domain == "keri.host"


def test_set_global_styles_applies_theme(app, tmp_path, monkeypatch):
    import json
    from locksmith.ui import styles, colors
    cfg = tmp_path / "brandcfg.json"
    cfg.write_text(json.dumps({"display_name": "Acme", "theme": {"primary": "#0055AA"}}))
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(cfg))
    branding._reset_cache_for_tests()
    try:
        styles.set_global_styles(app)
        assert colors.PRIMARY == "#0055AA"
    finally:
        colors.PRIMARY = "#F57B03"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_styles_branding.py -q --import-mode=importlib`
Expected: FAIL — `assert 'Locksmith' == ...` currently passes the name (hard-coded) but `organizationName` already equals `keri.host`; the theme test FAILS because `set_global_styles` does not yet call `apply_theme_overrides` (PRIMARY stays `#F57B03`, not `#0055AA`).

- [ ] **Step 3: Edit `styles.py` to source identity + theme from the brand**

In `src/locksmith/ui/styles.py`, replace the block at lines 63-69:

```python
    app.setApplicationName("Locksmith")
    # setOrganizationName is required for QSettings() with no args to
    # write to a stable per-user location on Windows. Without it,
    # consent_seen / last_checked / other UpdatePrefs values would land
    # somewhere ephemeral and consent dialog would re-fire every launch.
    app.setOrganizationName("keri.host")
    app.setOrganizationDomain("keri.host")
```

with:

```python
    from locksmith.core.branding import brand
    from locksmith.ui import colors as _colors

    _b = brand()
    # Apply the brand's accent theme BEFORE the QSS below is built from it.
    _colors.apply_theme_overrides(_b.theme)

    app.setApplicationName(_b.display_name)
    # setOrganizationName is required for QSettings() with no args to
    # write to a stable per-user location on Windows. Without it,
    # consent_seen / last_checked / other UpdatePrefs values would land
    # somewhere ephemeral and consent dialog would re-fire every launch.
    app.setOrganizationName(_b.org_name)
    app.setOrganizationDomain(_b.org_domain)
```

(The `from locksmith.ui import colors` already exists at line 40; the local `_colors` alias avoids relying on import order. The QSS f-string further down reads `colors.*` at call time, so the overrides take effect.)

- [ ] **Step 4: Edit the two window titles in `window.py`**

At `src/locksmith/ui/window.py:58`, replace:

```python
        self.setWindowTitle("Locksmith")
```

with:

```python
        from locksmith.core.branding import app_title
        self.setWindowTitle(app_title(None))
```

At `src/locksmith/ui/window.py:612` (inside `on_lock_vault`, the `# Reset title` line), replace:

```python
        # Reset title
        self.setWindowTitle("Locksmith")
```

with:

```python
        # Reset title
        from locksmith.core.branding import app_title
        self.setWindowTitle(app_title(None))
```

- [ ] **Step 5: Edit the vault-open title in `drawer.py`**

At `src/locksmith/ui/vaults/drawer.py:735`, replace:

```python
        self.parent.setWindowTitle(f"Locksmith | {vault_name}")
```

with:

```python
        from locksmith.core.branding import app_title
        self.parent.setWindowTitle(app_title(vault_name))
```

- [ ] **Step 6: Edit the toolbar wordmark in `toolbar.py`**

At `src/locksmith/ui/toolbar.py:101`, replace:

```python
        text_label = QLabel("Locksmith")
```

with:

```python
        from locksmith.core.branding import brand
        text_label = QLabel(brand().display_name)
```

- [ ] **Step 7: Remove the dead `appName` constant in `configing.py`**

At `src/locksmith/core/configing.py:50`, delete the line:

```python
    appName = 'Locksmith'
```

(Confirmed unused anywhere in `src/`; its role is replaced by `brand().display_name`.)

- [ ] **Step 8: Run the test + a quick import smoke check**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_styles_branding.py -q --import-mode=importlib`
Expected: PASS (2 passed).

Run: `.venv/bin/python -c "import locksmith.ui.window, locksmith.ui.toolbar, locksmith.ui.vaults.drawer, locksmith.core.configing"`
Expected: no output, exit 0 (no import errors from the edits).

- [ ] **Step 9: Commit**

```bash
git add src/locksmith/ui/styles.py src/locksmith/ui/window.py src/locksmith/ui/vaults/drawer.py src/locksmith/ui/toolbar.py src/locksmith/core/configing.py tests/unit/branding/test_styles_branding.py
git commit -m "feat(brand): wire runtime brand name/org/theme into the UI; drop dead appName"
```

---

### Task 4: Brand manifests + build-time reader (`packaging/brandlib.py`)

**Files:**
- Create: `brands/example/brand.toml`
- Create: `brands/locksmith/brand.toml`
- Create: `packaging/brandlib.py`
- Create: `tests/unit/branding/test_brandlib.py`
- Modify: `.gitignore` (ignore per-brand trust material)

**Interfaces:**
- Produces (in `packaging/brandlib.py`):
  - `BRANDS_DIR: Path` — repo `brands/` dir.
  - `active_brand_id() -> str` — `os.environ.get("LOCKSMITH_BRAND", "locksmith")`.
  - `load_brand_manifest(brand_id: str | None = None) -> dict` — reads `brands/<brand>/brand.toml` via `tomllib`; if the dir is absent, falls back to `brands/example/brand.toml`. Returns the parsed dict (sections `brand`, `identity`, `urls`, `theme`, `assets`, `publisher`). The brand's own directory path is attached as `manifest["_dir"]` (a `Path`).
  - `runtime_brand_json(manifest: dict) -> dict` — the `brand.json` runtime subset (see Task 5).
  - `exe_name(manifest) -> str` → `manifest["brand"]["display_name"]`.
  - `macos_info_plist(manifest, version: str) -> dict` and `macos_bundle_kwargs(manifest, version: str) -> dict` (see Task 8).

- [ ] **Step 1: Write the example + locksmith manifests**

Create `brands/example/brand.toml`:

```toml
[brand]
id            = "example"
display_name  = "Example Vault"
tagline       = "KERI identity vault"
manufacturer  = "Example, Inc."

[identity]
bundle_id       = "com.example.vault"
upgrade_code    = "00000000-0000-0000-0000-000000000000"
data_dir        = "ExampleVault"
artifact_prefix = "ExampleVault"
org_domain      = "example.com"

[urls]
website         = "https://example.com"
support         = "https://example.com/support"
appcast_macos   = "https://releases.example.com/appcast/v1/macos.json"
appcast_windows = "https://releases.example.com/appcast/v1/windows.json"

[theme]
primary         = "#3366CC"
primary_hover   = "#2A52A3"
primary_pressed = "#1F3D7A"
toolbar_dark    = "#11202B"

[assets]
app_icon_icns     = "AppIcon.icns"
app_icon_ico      = "AppIcon.ico"
splash            = "SplashScreen.png"
symbol_logo       = "SymbolLogo.svg"
name_logo         = "NameLogo.svg"
full_logo         = "FullLogo.svg"
symbol_logo_black = "SymbolLogoBlack.svg"
name_logo_black   = "NameLogoBlack.svg"
full_logo_black   = "FullLogoBlack.svg"

[publisher]
anchor        = "publisher_anchor.json"
deploy_config = "deploy_config.json"
```

Create `brands/locksmith/brand.toml` (the reference brand — values match today's committed packaging):

```toml
[brand]
id            = "locksmith"
display_name  = "Locksmith"
tagline       = "KERI identity vault"
manufacturer  = "KERI.host"

[identity]
bundle_id       = "host.keri.locksmith"
upgrade_code    = "297BBF26-821C-4D56-8857-309C7B531E21"
data_dir        = "Locksmith"
artifact_prefix = "Locksmith"
org_domain      = "keri.host"

[urls]
website         = "https://locksmith.app"
support         = "https://locksmith.app/support"
appcast_macos   = "https://releases.keri.host/appcast/v1/macos.json"
appcast_windows = "https://releases.keri.host/appcast/v1/windows.json"

[theme]
primary         = "#F57B03"
primary_hover   = "#D66A02"
primary_pressed = "#E67E00"
toolbar_dark    = "#1A252C"

[org]
name = "keri.host"

[assets]
# The locksmith reference brand uses the canonical committed assets/custom/
# tree; it ships NO asset files in its brand dir, so brand_apply copies nothing
# and the in-tree assets are used as-is. Listed here for documentation only.
app_icon_icns     = "AppIcon.icns"
app_icon_ico      = "AppIcon.ico"
splash            = "SplashScreen.png"
symbol_logo       = "SymbolLogo.svg"
name_logo         = "NameLogo.svg"
full_logo         = "FullLogo.svg"
symbol_logo_black = "SymbolLogoBlack.svg"
name_logo_black   = "NameLogoBlack.svg"
full_logo_black   = "FullLogoBlack.svg"

[publisher]
anchor        = "publisher_anchor.json"
deploy_config = "deploy_config.json"
```

Note: `org_name` in `runtime_brand_json` reads `[org].name` if present, else falls back to `[identity].org_domain`. The example omits `[org]` to exercise the fallback.

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/branding/test_brandlib.py`:

```python
import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("LOCKSMITH_BRAND", raising=False)


def test_active_brand_defaults_to_locksmith():
    assert brandlib.active_brand_id() == "locksmith"


def test_active_brand_from_env(monkeypatch):
    monkeypatch.setenv("LOCKSMITH_BRAND", "example")
    assert brandlib.active_brand_id() == "example"


def test_load_locksmith_manifest():
    m = brandlib.load_brand_manifest("locksmith")
    assert m["brand"]["display_name"] == "Locksmith"
    assert m["brand"]["manufacturer"] == "KERI.host"
    assert m["identity"]["bundle_id"] == "host.keri.locksmith"
    assert m["identity"]["upgrade_code"] == "297BBF26-821C-4D56-8857-309C7B531E21"
    assert m["identity"]["artifact_prefix"] == "Locksmith"
    assert m["urls"]["website"] == "https://locksmith.app"
    assert m["theme"]["primary"] == "#F57B03"
    assert m["_dir"].name == "locksmith"


def test_unknown_brand_falls_back_to_example():
    m = brandlib.load_brand_manifest("does-not-exist")
    assert m["brand"]["id"] == "example"


def test_exe_name():
    assert brandlib.exe_name(brandlib.load_brand_manifest("locksmith")) == "Locksmith"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_brandlib.py -q --import-mode=importlib`
Expected: FAIL — `ModuleNotFoundError: No module named 'brandlib'`.

- [ ] **Step 4: Implement `packaging/brandlib.py`**

Create `packaging/brandlib.py`:

```python
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
```

- [ ] **Step 5: Add gitignore entries for per-brand trust material**

Add to `.gitignore` after the `src/locksmith/release/brand.json` block:

```gitignore
# Per-brand trust material — the REAL publisher anchor + deploy_config for each
# brand carry real AIDs/federation domains and are never committed. Only
# brands/example/*.example.json placeholders and brands/<brand>/brand.toml
# (non-secret identity) are tracked. See docs/superpowers/specs/2026-06-23-*.
brands/*/publisher_anchor.json
brands/*/deploy_config.json
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_brandlib.py -q --import-mode=importlib`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add brands/example/brand.toml brands/locksmith/brand.toml packaging/brandlib.py tests/unit/branding/test_brandlib.py .gitignore
git commit -m "feat(brand): brand manifests (example + locksmith) + build-time brandlib reader"
```

---

### Task 5: Runtime `brand.json` rendering

**Files:**
- Modify: `packaging/brandlib.py` (already has `runtime_brand_json` from Task 4 — this task verifies it explicitly)
- Create: `tests/unit/branding/test_runtime_brand_json.py`

**Interfaces:**
- Consumes: `brandlib.load_brand_manifest`, `brandlib.runtime_brand_json`.
- Produces: a verified `runtime_brand_json(manifest)` whose output is loadable by `locksmith.core.branding._from_dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/branding/test_runtime_brand_json.py`:

```python
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")
branding = importlib.import_module("locksmith.core.branding")


def test_locksmith_runtime_json_round_trips_to_brand():
    m = brandlib.load_brand_manifest("locksmith")
    doc = brandlib.runtime_brand_json(m)
    assert doc["display_name"] == "Locksmith"
    assert doc["org_name"] == "keri.host"      # from [org].name
    assert doc["website"] == "https://locksmith.app"
    assert doc["theme"]["primary"] == "#F57B03"
    b = branding._from_dict(doc)
    assert b.display_name == "Locksmith"
    assert b.org_domain == "keri.host"


def test_example_org_name_falls_back_to_domain():
    m = brandlib.load_brand_manifest("example")
    doc = brandlib.runtime_brand_json(m)
    # example/brand.toml omits [org], so org_name falls back to org_domain
    assert doc["org_name"] == "example.com"
```

- [ ] **Step 2: Run the test to verify it fails or passes**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_runtime_brand_json.py -q --import-mode=importlib`
Expected: PASS (the function exists from Task 4). If it FAILS, fix `runtime_brand_json` per the assertions before continuing. (This task is the explicit contract test binding `brandlib` output to the runtime loader — TDD here means the test pins the integration that Task 4 only implemented.)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/branding/test_runtime_brand_json.py
git commit -m "test(brand): pin brandlib.runtime_brand_json output to the runtime loader"
```

---

### Task 6: Render WiX `.wxs` + DMG `layout.json` from the manifest

**Files:**
- Create: `packaging/wix/Locksmith.wxs.in` (tokenized template — copy of the current `.wxs` with brand values replaced by `@@TOKENS@@`)
- Modify: `packaging/brandlib.py` (add `render_wxs` + `render_dmg_layout`)
- Create: `tests/unit/branding/test_render_packaging.py`

**Interfaces:**
- Produces (in `brandlib`):
  - `render_wxs(manifest: dict, template_text: str) -> str` — replaces tokens `@@NAME@@`, `@@MANUFACTURER@@`, `@@UPGRADE_CODE@@`, `@@URL_ABOUT@@`, `@@URL_SUPPORT@@`, `@@TAGLINE@@`, `@@DATA_DIR@@` in `template_text`. (Token-replace, not `str.format`, to avoid clashing with `$(var.Version)` and XML.)
  - `render_dmg_layout(manifest: dict) -> dict` — returns the DMG layout dict with `volume_name` = display name and the app icon `name` = `f"{display_name}.app"`.
  - `WXS_TEMPLATE_PATH: Path` and `WXS_OUTPUT_PATH: Path`.

- [ ] **Step 1: Create the tokenized WiX template**

Create `packaging/wix/Locksmith.wxs.in` as a copy of the current `packaging/wix/Locksmith.wxs`, with these exact substitutions (every brand-bearing literal → token; leave `$(var.Version)`, the `Software\` registry path's `KERI.host` segment uses `@@MANUFACTURER@@`, and the install/start-menu folder `Name="Locksmith"` uses `@@NAME@@`):

- `Name="Locksmith"` (Package) → `Name="@@NAME@@"`
- `Manufacturer="KERI.host"` → `Manufacturer="@@MANUFACTURER@@"`
- `UpgradeCode="297BBF26-821C-4D56-8857-309C7B531E21"` → `UpgradeCode="@@UPGRADE_CODE@@"`
- `DowngradeErrorMessage="A newer version of Locksmith is already installed."` → `...of @@NAME@@ is already...`
- `ARPURLINFOABOUT" Value="https://locksmith.app"` → `Value="@@URL_ABOUT@@"`
- `ARPHELPLINK" Value="https://locksmith.app/support"` → `Value="@@URL_SUPPORT@@"`
- `<Directory Id="INSTALLFOLDER" Name="Locksmith" />` → `Name="@@NAME@@"`
- `<Directory Id="ApplicationProgramsFolder" Name="Locksmith" />` → `Name="@@NAME@@"`
- Shortcut `Name="Locksmith"` (both) → `Name="@@NAME@@"`
- Shortcut `Description="Locksmith — KERI identity vault"` (both) → `Description="@@NAME@@ — @@TAGLINE@@"`
- `Target="[INSTALLFOLDER]Locksmith.exe"` (both) → `Target="[INSTALLFOLDER]@@NAME@@.exe"`
- `Key="Software\KERI.host\Locksmith"` (both) → `Key="Software\@@MANUFACTURER@@\@@NAME@@"`
- `Feature ... Title="Locksmith"` → `Title="@@NAME@@"`

Leave `Icon Id="LocksmithIcon"`, `ARPPRODUCTICON" Value="LocksmithIcon"`, and `Icon="LocksmithIcon"` as the literal id `LocksmithIcon` (it is an internal WiX symbol, not user-visible — keeping it stable avoids editing three cross-references; documented in the template header).

Add this comment at the top of the `.in` file (after the existing top comment block):

```xml
<!-- TEMPLATE: rendered by scripts/brand_apply.py (brandlib.render_wxs) into
     Locksmith.wxs for the active brand. Tokens: @@NAME@@ @@MANUFACTURER@@
     @@UPGRADE_CODE@@ @@URL_ABOUT@@ @@URL_SUPPORT@@ @@TAGLINE@@ @@DATA_DIR@@.
     The "LocksmithIcon" symbol id is intentionally NOT tokenized (internal). -->
```

- [ ] **Step 2: Write the failing test**

Create `tests/unit/branding/test_render_packaging.py`:

```python
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")

TEMPLATE = (REPO_ROOT / "packaging" / "wix" / "Locksmith.wxs.in").read_text(encoding="utf-8")


def test_render_wxs_locksmith_matches_current_values():
    m = brandlib.load_brand_manifest("locksmith")
    out = brandlib.render_wxs(m, TEMPLATE)
    assert 'Name="Locksmith"' in out
    assert 'Manufacturer="KERI.host"' in out
    assert 'UpgradeCode="297BBF26-821C-4D56-8857-309C7B531E21"' in out
    assert 'Value="https://locksmith.app"' in out
    assert 'Value="https://locksmith.app/support"' in out
    assert r'Key="Software\KERI.host\Locksmith"' in out
    assert "@@" not in out  # every token resolved


def test_render_wxs_for_another_brand():
    m = brandlib.load_brand_manifest("example")
    out = brandlib.render_wxs(m, TEMPLATE)
    assert 'Name="Example Vault"' in out
    assert 'Manufacturer="Example, Inc."' in out
    assert 'UpgradeCode="00000000-0000-0000-0000-000000000000"' in out
    assert "@@" not in out


def test_render_dmg_layout():
    m = brandlib.load_brand_manifest("locksmith")
    layout = brandlib.render_dmg_layout(m)
    assert layout["volume_name"] == "Locksmith"
    assert layout["icons"][0]["name"] == "Locksmith.app"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_render_packaging.py -q --import-mode=importlib`
Expected: FAIL — `AttributeError: module 'brandlib' has no attribute 'render_wxs'`.

- [ ] **Step 4: Implement `render_wxs` + `render_dmg_layout`**

Append to `packaging/brandlib.py`:

```python
WIX_DIR = REPO_ROOT / "packaging" / "wix"
WXS_TEMPLATE_PATH = WIX_DIR / "Locksmith.wxs.in"
WXS_OUTPUT_PATH = WIX_DIR / "Locksmith.wxs"
DMG_LAYOUT_PATH = REPO_ROOT / "packaging" / "dmg" / "layout.json"


def render_wxs(manifest: dict, template_text: str) -> str:
    name = manifest["brand"]["display_name"]
    tokens = {
        "@@NAME@@": name,
        "@@MANUFACTURER@@": manifest["brand"]["manufacturer"],
        "@@UPGRADE_CODE@@": manifest["identity"]["upgrade_code"],
        "@@URL_ABOUT@@": manifest["urls"]["website"],
        "@@URL_SUPPORT@@": manifest["urls"]["support"],
        "@@TAGLINE@@": manifest["brand"]["tagline"],
        "@@DATA_DIR@@": manifest["identity"]["data_dir"],
    }
    out = template_text
    for token, value in tokens.items():
        out = out.replace(token, value)
    return out


def render_dmg_layout(manifest: dict) -> dict:
    name = manifest["brand"]["display_name"]
    return {
        "_comment": "Generated by scripts/brand_apply.py from the active brand. "
                    "Coordinates in pixels, origin top-left.",
        "window": {"position": [200, 200], "size": [540, 380]},
        "icon_size": 96,
        "background": "background.png",
        "volume_name": name,
        "icons": [
            {"name": f"{name}.app", "pos": [140, 200]},
            {"name": "Applications", "pos": [400, 200],
             "type": "symlink", "target": "/Applications"},
        ],
    }
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_render_packaging.py -q --import-mode=importlib`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add packaging/wix/Locksmith.wxs.in packaging/brandlib.py tests/unit/branding/test_render_packaging.py
git commit -m "feat(brand): render WiX .wxs + DMG layout from the brand manifest"
```

---

### Task 7: `scripts/brand_apply.py` orchestrator

**Files:**
- Create: `scripts/brand_apply.py`
- Create: `tests/unit/branding/test_brand_apply.py`

**Interfaces:**
- Consumes: all of `brandlib`.
- Produces:
  - `apply(brand_id: str, repo_root: Path, *, check: bool = False) -> dict` — when `check` is False: stages asset files present in the brand dir over `assets/custom/`, writes `src/locksmith/release/brand.json`, writes `packaging/wix/Locksmith.wxs` (rendered), writes `packaging/dmg/layout.json` (rendered), and copies the brand's `publisher_anchor.json` + `deploy_config.json` into `src/locksmith/release/` if they exist. Returns a dict report of what it did. When `check` is True: writes nothing, returns the same report describing what *would* be written.
  - CLI: `python scripts/brand_apply.py [--brand <id>] [--check]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/branding/test_brand_apply.py`:

```python
import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brand_apply = importlib.import_module("brand_apply")


@pytest.fixture
def fake_repo(tmp_path):
    """A minimal repo tree: brands/, assets/custom/, packaging/, src/.../release/."""
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "assets" / "custom" / "AppIcon.icns").write_text("OLD-ICON")
    (tmp_path / "packaging" / "wix").mkdir(parents=True)
    (tmp_path / "packaging" / "dmg").mkdir(parents=True)
    (tmp_path / "packaging" / "wix" / "Locksmith.wxs.in").write_text(
        '<Package Name="@@NAME@@" UpgradeCode="@@UPGRADE_CODE@@" />')
    (tmp_path / "src" / "locksmith" / "release").mkdir(parents=True)
    acme = tmp_path / "brands" / "acme"
    acme.mkdir(parents=True)
    (acme / "brand.toml").write_text((REPO_ROOT / "brands" / "example" / "brand.toml")
                                     .read_text().replace('id            = "example"',
                                                          'id            = "acme"')
                                     .replace("Example Vault", "Acme"))
    (acme / "AppIcon.icns").write_text("ACME-ICON")
    (acme / "publisher_anchor.json").write_text('{"publisher_aid": "EAcme"}')
    (acme / "deploy_config.json").write_text('{"s3_bucket": "acme"}')
    return tmp_path


def test_apply_stages_assets_and_writes_outputs(fake_repo):
    report = brand_apply.apply("acme", fake_repo, check=False)
    # asset staged over assets/custom/
    assert (fake_repo / "assets" / "custom" / "AppIcon.icns").read_text() == "ACME-ICON"
    # runtime brand.json written
    doc = json.loads((fake_repo / "src" / "locksmith" / "release" / "brand.json").read_text())
    assert doc["display_name"] == "Acme"
    # wxs rendered
    wxs = (fake_repo / "packaging" / "wix" / "Locksmith.wxs").read_text()
    assert 'Name="Acme"' in wxs and "@@" not in wxs
    # dmg layout written
    layout = json.loads((fake_repo / "packaging" / "dmg" / "layout.json").read_text())
    assert layout["volume_name"] == "Acme"
    # trust material injected
    assert (fake_repo / "src" / "locksmith" / "release" / "publisher_anchor.json").exists()
    assert (fake_repo / "src" / "locksmith" / "release" / "deploy_config.json").exists()
    assert report["staged_assets"] == ["AppIcon.icns"]


def test_check_mode_writes_nothing(fake_repo):
    brand_apply.apply("acme", fake_repo, check=True)
    assert (fake_repo / "assets" / "custom" / "AppIcon.icns").read_text() == "OLD-ICON"
    assert not (fake_repo / "src" / "locksmith" / "release" / "brand.json").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_brand_apply.py -q --import-mode=importlib`
Expected: FAIL — `ModuleNotFoundError: No module named 'brand_apply'`.

- [ ] **Step 3: Implement `scripts/brand_apply.py`**

Create `scripts/brand_apply.py`:

```python
#!/usr/bin/env python3
"""Apply a brand to the working tree before a packaged build.

Reads brands/<brand>/brand.toml and:
  - stages any asset files present in the brand dir over assets/custom/
    (same filenames; the locksmith reference brand ships none, using the
    canonical committed assets);
  - writes src/locksmith/release/brand.json (runtime subset);
  - renders packaging/wix/Locksmith.wxs and packaging/dmg/layout.json;
  - injects the brand's publisher_anchor.json + deploy_config.json (if present)
    into src/locksmith/release/.

Selection: --brand or $LOCKSMITH_BRAND (default 'locksmith'). --check writes
nothing and just reports what would happen.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent.parent / "packaging"))
import brandlib  # noqa: E402

_ASSET_KEYS = ("app_icon_icns", "app_icon_ico", "splash", "symbol_logo",
               "name_logo", "full_logo", "symbol_logo_black", "name_logo_black",
               "full_logo_black")


def apply(brand_id: str, repo_root: Path, *, check: bool = False) -> dict:
    brands_dir = repo_root / "brands"
    brand_dir = brands_dir / brand_id
    if not (brand_dir / "brand.toml").is_file():
        brand_dir = brands_dir / "example"
    import tomllib
    manifest = tomllib.loads((brand_dir / "brand.toml").read_text(encoding="utf-8"))
    manifest["_dir"] = brand_dir

    assets_dst = repo_root / "assets" / "custom"
    release_dir = repo_root / "src" / "locksmith" / "release"
    wxs_out = repo_root / "packaging" / "wix" / "Locksmith.wxs"
    wxs_tmpl = repo_root / "packaging" / "wix" / "Locksmith.wxs.in"
    dmg_out = repo_root / "packaging" / "dmg" / "layout.json"

    staged = []
    for key in _ASSET_KEYS:
        fname = manifest.get("assets", {}).get(key)
        if fname and (brand_dir / fname).is_file():
            staged.append(fname)
            if not check:
                shutil.copyfile(brand_dir / fname, assets_dst / fname)

    injected = []
    for key, dst_name in (("anchor", "publisher_anchor.json"),
                          ("deploy_config", "deploy_config.json")):
        src_name = manifest.get("publisher", {}).get(key)
        if src_name and (brand_dir / src_name).is_file():
            injected.append(dst_name)
            if not check:
                shutil.copyfile(brand_dir / src_name, release_dir / dst_name)

    if not check:
        (release_dir / "brand.json").write_text(
            json.dumps(brandlib.runtime_brand_json(manifest), indent=2) + "\n",
            encoding="utf-8")
        wxs_out.write_text(
            brandlib.render_wxs(manifest, wxs_tmpl.read_text(encoding="utf-8")),
            encoding="utf-8")
        dmg_out.write_text(
            json.dumps(brandlib.render_dmg_layout(manifest), indent=2) + "\n",
            encoding="utf-8")

    return {
        "brand": manifest["brand"]["id"],
        "staged_assets": staged,
        "injected": injected,
        "check": check,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default=brandlib.active_brand_id())
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    report = apply(args.brand, brandlib.REPO_ROOT, check=args.check)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_brand_apply.py -q --import-mode=importlib`
Expected: PASS (2 passed).

- [ ] **Step 5: Verify applying the real locksmith brand is a no-op on the working tree**

Run: `.venv/bin/python scripts/brand_apply.py --brand locksmith && git status --porcelain packaging/wix/Locksmith.wxs packaging/dmg/layout.json`
Expected: JSON report with `"staged_assets": []`; `git status` shows the two files either unchanged or with only formatting-identical content. Inspect `git diff packaging/dmg/layout.json packaging/wix/Locksmith.wxs` — the rendered output must be semantically identical to the committed files for the locksmith brand (volume_name `Locksmith`, Name `Locksmith`, UpgradeCode unchanged). If `layout.json` differs only by the regenerated `_comment`, that is acceptable; restore with `git checkout -- packaging/dmg/layout.json packaging/wix/Locksmith.wxs` after confirming.

- [ ] **Step 6: Commit**

```bash
git add scripts/brand_apply.py tests/unit/branding/test_brand_apply.py
git commit -m "feat(brand): brand_apply orchestrator (stage assets, write brand.json, render wix/dmg, inject trust)"
```

---

### Task 8: PyInstaller specs read the active brand

**Files:**
- Modify: `packaging/Locksmith.macos.spec:129-195`
- Modify: `packaging/Locksmith.windows.spec:137-176`
- Create: `tests/unit/branding/test_spec_brand_values.py`

**Interfaces:**
- Consumes: `brandlib.exe_name`, `brandlib.macos_info_plist`, `brandlib.load_brand_manifest`, and the manifest `identity.bundle_id` / `urls.appcast_macos`.
- Produces: the specs' EXE/COLLECT `name`, the macOS BUNDLE `name`/`bundle_identifier`/`info_plist` now derive from the active brand.

- [ ] **Step 1: Write the failing test (covers the brandlib seams the specs use)**

Create `tests/unit/branding/test_spec_brand_values.py`:

```python
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")


def test_macos_info_plist_from_locksmith():
    m = brandlib.load_brand_manifest("locksmith")
    plist = brandlib.macos_info_plist(m, "0.1.8")
    assert plist["CFBundleName"] == "Locksmith"
    assert plist["CFBundleIdentifier"] == "host.keri.locksmith"
    assert plist["CFBundleExecutable"] == "Locksmith"
    assert plist["CFBundleShortVersionString"] == "0.1.8"
    assert plist["SUFeedURL"] == "https://releases.keri.host/appcast/v1/macos.json"
    # KERI is sole trust: Sparkle's EdDSA key must NOT be present
    assert "SUPublicEDKey" not in plist


def test_exe_name_locksmith():
    assert brandlib.exe_name(brandlib.load_brand_manifest("locksmith")) == "Locksmith"
```

- [ ] **Step 2: Run the test to verify it passes (the seams exist from Task 4)**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_spec_brand_values.py -q --import-mode=importlib`
Expected: PASS (2 passed). These seams were added in Task 4; this test pins the exact values the spec edits below will consume.

- [ ] **Step 3: Edit `Locksmith.macos.spec` to read the brand**

Near the top of `packaging/Locksmith.macos.spec`, after `REPO_ROOT` is defined, add (find the existing `REPO_ROOT = ...` line and insert after it):

```python
import sys as _sys
_sys.path.insert(0, str(REPO_ROOT / "packaging"))
import brandlib as _brandlib
_BRAND = _brandlib.load_brand_manifest()
_BRAND_NAME = _BRAND["brand"]["display_name"]
```

Then in the `EXE(...)` call replace `name="Locksmith",` with `name=_BRAND_NAME,`.

In the `COLLECT(...)` call replace `name="Locksmith",` with `name=_BRAND_NAME,`.

Replace the `BUNDLE(...)` call's brand-bearing args:

```python
app = BUNDLE(
    coll,
    name="Locksmith.app",
    icon=str(REPO_ROOT / "assets" / "custom" / "AppIcon.icns")
        if (REPO_ROOT / "assets" / "custom" / "AppIcon.icns").exists()
        else None,
    bundle_identifier="host.keri.locksmith",
    version=LOCKSMITH_VERSION,
    info_plist={
        "CFBundleName": "Locksmith",
        ...
    },
)
```

with:

```python
app = BUNDLE(
    coll,
    name=f"{_BRAND_NAME}.app",
    icon=str(REPO_ROOT / "assets" / "custom" / "AppIcon.icns")
        if (REPO_ROOT / "assets" / "custom" / "AppIcon.icns").exists()
        else None,
    bundle_identifier=_BRAND["identity"]["bundle_id"],
    version=LOCKSMITH_VERSION,
    info_plist=_brandlib.macos_info_plist(_BRAND, LOCKSMITH_VERSION),
)
```

(The full `info_plist` dict is now produced by `brandlib.macos_info_plist`, which reproduces every key the inline dict had — verified by Task 8 Step 1 — including the deliberate omission of `SUPublicEDKey`.)

- [ ] **Step 4: Edit `Locksmith.windows.spec` to read the brand**

Near the top of `packaging/Locksmith.windows.spec`, after the `WIN_ICON = ...` line, add:

```python
import sys as _sys
_sys.path.insert(0, str(REPO_ROOT / "packaging"))
import brandlib as _brandlib
_BRAND = _brandlib.load_brand_manifest()
_BRAND_NAME = _BRAND["brand"]["display_name"]
```

In the `EXE(...)` call replace `name="Locksmith",` with `name=_BRAND_NAME,`.

In the `COLLECT(...)` call replace `name="Locksmith",` with `name=_BRAND_NAME,`.

(The WinSparkle appcast URL is set at runtime by `winsparkle_init.py`; that is wired to the brand in Task 9 / out-of-scope note — the spec's splash + icon paths are filename-stable and need no change.)

- [ ] **Step 5: Smoke-check the specs parse with the brand import**

Run:
```bash
.venv/bin/python - <<'PY'
import sys, types
from pathlib import Path
root = Path("packaging")
# Exercise the brand preamble both specs now share.
sys.path.insert(0, "packaging")
import brandlib
m = brandlib.load_brand_manifest()
assert m["brand"]["display_name"] == "Locksmith"
assert brandlib.macos_info_plist(m, "9.9.9")["CFBundleIdentifier"] == "host.keri.locksmith"
print("spec brand preamble OK")
PY
```
Expected: `spec brand preamble OK`. (PyInstaller is not invoked here — full `.spec` execution happens in a packaged build, Phase 3 / CI. This check validates the brand-reading preamble the edits added.)

- [ ] **Step 6: Commit**

```bash
git add packaging/Locksmith.macos.spec packaging/Locksmith.windows.spec tests/unit/branding/test_spec_brand_values.py
git commit -m "feat(brand): PyInstaller specs read identity/plist/name from the active brand"
```

---

### Task 9: Publisher CLI artifact prefix from deploy_config

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/cli.py:281` (artifact_url prefix)
- Modify: `src/locksmith/release/deploy_config.example.json` (add `artifact_prefix`)
- Create or Modify: a publisher unit test under `tools/publisher/tests/` asserting the appcast artifact URL uses the configured prefix

**Interfaces:**
- Consumes: `cfg["artifact_prefix"]` from `load_deploy_config()` (defaulting to `"Locksmith"` when absent, for backward compatibility with the current example).
- Produces: appcast `artifact_url` = `f"{cdn}/releases/{version}/{prefix}-{version}.{ext}"`.

- [ ] **Step 1: Add `artifact_prefix` to the deploy_config example**

In `src/locksmith/release/deploy_config.example.json`, add a top-level key (match the file's existing formatting):

```json
  "artifact_prefix": "ExampleVault",
```

(The committed example uses placeholder values; real per-brand `deploy_config.json` files set their brand's prefix — `Locksmith` for the locksmith brand.)

- [ ] **Step 2: Write the failing test**

Locate the existing publisher appcast/publish test under `tools/publisher/tests/` (e.g. `test_cli.py` or `test_appcast.py`). Add:

```python
def test_publish_artifact_url_uses_configured_prefix(monkeypatch, tmp_path):
    # The appcast artifact_url must use deploy_config["artifact_prefix"],
    # not a hard-coded "Locksmith".
    from locksmith_publisher import cli
    cfg = {"s3_bucket": "b", "releases_cdn_base": "https://cdn.example.com",
           "publisher_kel_url": "https://cdn.example.com/publisher/v1/kel.cesr",
           "artifact_prefix": "Acme"}
    monkeypatch.setattr(cli, "load_deploy_config", lambda: cfg)
    # Build a single appcast entry via the same expression publish_cmd uses:
    version = "1.2.3"
    cdn = cfg["releases_cdn_base"].rstrip("/")
    prefix = cfg.get("artifact_prefix", "Locksmith")
    url = f"{cdn}/releases/{version}/{prefix}-{version}.dmg"
    assert url == "https://cdn.example.com/releases/1.2.3/Acme-1.2.3.dmg"
```

(If the publisher exposes a helper for the artifact URL, assert through that instead. The assertion pins the prefix-from-config contract.)

- [ ] **Step 3: Run the test to verify it fails**

Run (from the publisher package): `cd tools/publisher && ../../.venv/bin/python -m pytest tests/ -q -k artifact_url --import-mode=importlib`
Expected: FAIL if a helper is asserted (not yet prefix-aware); the inline-expression form documents the target. Proceed to wire the CLI.

- [ ] **Step 4: Edit the publisher CLI**

In `tools/publisher/src/locksmith_publisher/cli.py`, inside `publish_cmd`, after `cdn = cfg["releases_cdn_base"].rstrip("/")` add:

```python
    artifact_prefix = cfg.get("artifact_prefix", "Locksmith")
```

Then in the `_appcast` inner function replace:

```python
               "artifact_url": f"{cdn}/releases/{version}/Locksmith-{version}.{ext}"}
```

with:

```python
               "artifact_url": f"{cdn}/releases/{version}/{artifact_prefix}-{version}.{ext}"}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/ -q -k artifact_url --import-mode=importlib`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/cli.py src/locksmith/release/deploy_config.example.json tools/publisher/tests/
git commit -m "feat(brand): publisher artifact filename uses deploy_config artifact_prefix"
```

---

### Task 10: `check-brand-complete.py` release guard

**Files:**
- Create: `scripts/check-brand-complete.py`
- Create: `tests/unit/branding/test_check_brand_complete.py`

**Interfaces:**
- Produces: a fail-closed CLI `python scripts/check-brand-complete.py --brand <id>` returning non-zero on any defect, mirroring `scripts/check-anchor-present.py`. A testable `validate(brand_id, brands_dir) -> list[str]` returns the list of problems (empty == OK).
- Defect classes: missing `brand.toml`; missing required identity field; `example.com`/placeholder URL or zero/all-zero `upgrade_code` for a non-`example` brand; a non-`locksmith` brand reusing Locksmith's `bundle_id` or `upgrade_code`; for a non-`locksmith` brand, a missing asset file named in `[assets]`; a missing or placeholder `publisher_anchor.json` (reusing the `check-anchor-present` rule: empty/`Placeholder` `publisher_aid` or no `witness_oobis`).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/branding/test_check_brand_complete.py`:

```python
import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
cbc = importlib.import_module("check_brand_complete")


def _write_brand(tmp, bid, *, urls_ok=True, reuse_locksmith=False,
                 with_assets=True, with_anchor=True):
    bdir = tmp / "brands" / bid
    bdir.mkdir(parents=True)
    website = "https://acme.test" if urls_ok else "https://example.com"
    bundle = "host.keri.locksmith" if reuse_locksmith else "com.acme.vault"
    upgrade = ("297BBF26-821C-4D56-8857-309C7B531E21" if reuse_locksmith
               else "11111111-2222-3333-4444-555555555555")
    (bdir / "brand.toml").write_text(f'''
[brand]
id = "{bid}"
display_name = "Acme"
tagline = "vault"
manufacturer = "Acme"
[identity]
bundle_id = "{bundle}"
upgrade_code = "{upgrade}"
data_dir = "Acme"
artifact_prefix = "Acme"
org_domain = "acme.test"
[urls]
website = "{website}"
support = "{website}/support"
appcast_macos = "{website}/appcast/v1/macos.json"
appcast_windows = "{website}/appcast/v1/windows.json"
[theme]
primary = "#112233"
[assets]
app_icon_icns = "AppIcon.icns"
[publisher]
anchor = "publisher_anchor.json"
deploy_config = "deploy_config.json"
''')
    if with_assets:
        (bdir / "AppIcon.icns").write_text("x")
    if with_anchor:
        (bdir / "publisher_anchor.json").write_text(
            '{"publisher_aid": "EReal", "witness_oobis": ["https://w/oobi"]}')
    return tmp


def test_clean_brand_passes(tmp_path):
    _write_brand(tmp_path, "acme")
    assert cbc.validate("acme", tmp_path / "brands") == []


def test_placeholder_url_rejected(tmp_path):
    _write_brand(tmp_path, "acme", urls_ok=False)
    probs = cbc.validate("acme", tmp_path / "brands")
    assert any("example.com" in p for p in probs)


def test_reusing_locksmith_identity_rejected(tmp_path):
    _write_brand(tmp_path, "acme", reuse_locksmith=True)
    probs = cbc.validate("acme", tmp_path / "brands")
    assert any("Locksmith" in p or "host.keri.locksmith" in p for p in probs)


def test_missing_asset_rejected(tmp_path):
    _write_brand(tmp_path, "acme", with_assets=False)
    probs = cbc.validate("acme", tmp_path / "brands")
    assert any("AppIcon.icns" in p for p in probs)


def test_missing_anchor_rejected(tmp_path):
    _write_brand(tmp_path, "acme", with_anchor=False)
    probs = cbc.validate("acme", tmp_path / "brands")
    assert any("anchor" in p.lower() for p in probs)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_check_brand_complete.py -q --import-mode=importlib`
Expected: FAIL — `ModuleNotFoundError: No module named 'check_brand_complete'`.

- [ ] **Step 3: Implement `scripts/check-brand-complete.py`**

Create `scripts/check-brand-complete.py`:

```python
#!/usr/bin/env python3
"""Fail if the active brand is incomplete or still a placeholder (CI guard:
a tagged release must ship a fully-branded, real-trust build — never half
white-labeled or gate-dark). Mirrors scripts/check-anchor-present.py.

Importable as `check_brand_complete` (hyphen→underscore) for tests.
"""
import argparse
import json
import sys
import tomllib
from pathlib import Path

_LOCKSMITH_BUNDLE = "host.keri.locksmith"
_LOCKSMITH_UPGRADE = "297BBF26-821C-4D56-8857-309C7B531E21"
_REQUIRED_IDENTITY = ("bundle_id", "upgrade_code", "data_dir",
                      "artifact_prefix", "org_domain")
_ANCHOR_PLACEHOLDER = "Placeholder"


def validate(brand_id: str, brands_dir: Path) -> list:
    problems = []
    bdir = Path(brands_dir) / brand_id
    toml_path = bdir / "brand.toml"
    if not toml_path.is_file():
        return [f"no brand.toml for brand {brand_id!r} at {toml_path}"]
    m = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    ident = m.get("identity", {})
    for field in _REQUIRED_IDENTITY:
        if not ident.get(field):
            problems.append(f"missing identity.{field}")

    is_example = brand_id == "example"
    is_locksmith = brand_id == "locksmith"

    if not is_example:
        for label, val in (("website", m.get("urls", {}).get("website", "")),
                           ("support", m.get("urls", {}).get("support", ""))):
            if "example.com" in val or not val:
                problems.append(f"placeholder/empty urls.{label} ({val!r})")
        uc = ident.get("upgrade_code", "")
        if set(uc) <= {"0", "-"}:
            problems.append(f"placeholder upgrade_code ({uc!r})")

    if not is_locksmith:
        if ident.get("bundle_id") == _LOCKSMITH_BUNDLE:
            problems.append("non-locksmith brand reuses Locksmith bundle_id "
                            f"({_LOCKSMITH_BUNDLE})")
        if ident.get("upgrade_code") == _LOCKSMITH_UPGRADE:
            problems.append("non-locksmith brand reuses Locksmith upgrade_code")
        for key, fname in m.get("assets", {}).items():
            if not (bdir / fname).is_file():
                problems.append(f"missing asset file {fname} (assets.{key})")

    if not is_example:
        anchor_name = m.get("publisher", {}).get("anchor", "publisher_anchor.json")
        anchor_path = bdir / anchor_name
        if not anchor_path.is_file():
            problems.append(f"missing publisher anchor at {anchor_path}")
        else:
            doc = json.loads(anchor_path.read_text(encoding="utf-8"))
            aid = doc.get("publisher_aid", "")
            if not aid or _ANCHOR_PLACEHOLDER in aid:
                problems.append(f"placeholder/empty publisher_aid ({aid!r})")
            if not doc.get("witness_oobis"):
                problems.append("anchor has no witness_oobis")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", required=True)
    ap.add_argument("--brands-dir",
                    default=str(Path(__file__).resolve().parent.parent / "brands"))
    args = ap.parse_args()
    problems = validate(args.brand, Path(args.brands_dir))
    if problems:
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 1
    print(f"brand OK: {args.brand}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: tests import via the hyphenated filename. Add an import shim — create `scripts/check_brand_complete.py` that re-exports:

```python
# -*- encoding: utf-8 -*-
"""Underscore alias so `import check_brand_complete` works (the executable
script is check-brand-complete.py; CI invokes the hyphenated form)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "_cbc_impl", Path(__file__).with_name("check-brand-complete.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
validate = _mod.validate
main = _mod.main
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_check_brand_complete.py -q --import-mode=importlib`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/check-brand-complete.py scripts/check_brand_complete.py tests/unit/branding/test_check_brand_complete.py
git commit -m "feat(brand): check-brand-complete release guard (fail-closed)"
```

---

### Task 11: Keystone regression — the `locksmith` brand reproduces today's identity

**Files:**
- Create: `tests/unit/branding/test_locksmith_brand_regression.py`

**Interfaces:**
- Consumes: `brandlib`, the committed `brands/locksmith/brand.toml`, the committed `packaging/wix/Locksmith.wxs.in`.
- Produces: a single guard test that pins every Locksmith identity value the engine must not regress.

- [ ] **Step 1: Write the regression test**

Create `tests/unit/branding/test_locksmith_brand_regression.py`:

```python
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brandlib = importlib.import_module("brandlib")


def test_locksmith_identity_unchanged():
    m = brandlib.load_brand_manifest("locksmith")
    i = m["identity"]
    assert m["brand"]["display_name"] == "Locksmith"
    assert m["brand"]["manufacturer"] == "KERI.host"
    assert i["bundle_id"] == "host.keri.locksmith"
    assert i["upgrade_code"] == "297BBF26-821C-4D56-8857-309C7B531E21"
    assert i["data_dir"] == "Locksmith"
    assert i["artifact_prefix"] == "Locksmith"


def test_locksmith_rendered_wxs_matches_today():
    m = brandlib.load_brand_manifest("locksmith")
    tmpl = (REPO_ROOT / "packaging" / "wix" / "Locksmith.wxs.in").read_text()
    out = brandlib.render_wxs(m, tmpl)
    assert 'Name="Locksmith"' in out
    assert 'Manufacturer="KERI.host"' in out
    assert 'UpgradeCode="297BBF26-821C-4D56-8857-309C7B531E21"' in out
    assert 'Value="https://locksmith.app"' in out
    assert 'Value="https://locksmith.app/support"' in out
    assert r'Key="Software\KERI.host\Locksmith"' in out
    assert "@@" not in out


def test_locksmith_runtime_brand_json():
    m = brandlib.load_brand_manifest("locksmith")
    doc = brandlib.runtime_brand_json(m)
    assert doc["display_name"] == "Locksmith"
    assert doc["org_name"] == "keri.host"
    assert doc["theme"]["primary"] == "#F57B03"
    assert doc["theme"]["primary_hover"] == "#D66A02"
    assert doc["theme"]["primary_pressed"] == "#E67E00"
    assert doc["theme"]["toolbar_dark"] == "#1A252C"


def test_locksmith_dmg_layout():
    m = brandlib.load_brand_manifest("locksmith")
    layout = brandlib.render_dmg_layout(m)
    assert layout["volume_name"] == "Locksmith"
    assert layout["icons"][0]["name"] == "Locksmith.app"
```

- [ ] **Step 2: Run the regression test**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_locksmith_brand_regression.py -q --import-mode=importlib`
Expected: PASS (4 passed). If any assertion fails, the `brands/locksmith/brand.toml` values or a render function drifted from today's identity — fix the manifest/renderer, do not change the assertion.

- [ ] **Step 3: Run the full branding test suite + the existing release/update suites for regressions**

Run:
```bash
.venv/bin/python -m pytest tests/unit/branding tests/unit/release tests/unit/update -q --import-mode=importlib
cd tools/publisher && ../../.venv/bin/python -m pytest tests/ -q --import-mode=importlib
```
Expected: all PASS (no regressions in the existing release/update/publisher suites from the brand wiring).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/branding/test_locksmith_brand_regression.py
git commit -m "test(brand): keystone regression — locksmith brand reproduces today's identity"
```

---

## Self-Review

**1. Spec coverage:**
- Manifest schema + repo layout + privacy → Tasks 1, 4 (+ gitignore in 1, 4). ✓
- Runtime flow (`brand.json`, `core.branding`, UI wiring, colors override) → Tasks 1, 2, 3, 5. ✓
- Build flow (specs read manifest, wxs/dmg/brand.json generated, asset staging, anchor/deploy injection) → Tasks 4, 6, 7, 8. ✓
- Publisher CLI brand-aware (artifact prefix) → Task 9. ✓
- Validation fail-closed → Task 10. ✓
- Keystone regression (locksmith reproduces today) → Task 11. ✓
- Immutable-identity set → enforced by Task 10 + pinned by Task 11. ✓
- Per-brand publisher ceremony → reuses the existing operator CLI; no code change needed here (documented in scope; the real second-brand mint is Phase 3). ✓
- Phase 3 (real second brand, build-script artifact rename, WinSparkle runtime URL per brand) → explicitly out of scope in Global Constraints. ✓

**2. Placeholder scan:** No "TBD"/"implement later"/"handle edge cases". Every code step shows complete code; every test step shows the test; commands have expected output. The `example.com` strings are intentional placeholder *content* (the committed template), not plan placeholders. ✓

**3. Type consistency:** `brand()`/`load_brand()`/`Brand`/`app_title` (Task 1) used consistently in Task 3. `load_brand_manifest`/`runtime_brand_json`/`exe_name`/`macos_info_plist`/`render_wxs`/`render_dmg_layout` (Tasks 4, 6) used consistently in Tasks 5, 7, 8, 11. `apply(brand_id, repo_root, *, check)` (Task 7) matches its test. `validate(brand_id, brands_dir)` (Task 10) matches its test. `apply_theme_overrides(theme)` (Task 2) matches Task 3's call. ✓

**Two flagged design refinements vs the spec** (surface to the human at pre-flight review):
1. The runtime fallback is a baked-in `_DEFAULT` (Locksmith) in code, not an `example` file — so an unconfigured dev build is Locksmith, not placeholder text.
2. `brands/locksmith/brand.toml` is **committed** (non-secret; its values already appear in today's committed packaging), only per-brand trust material is gitignored — this is what makes the Task 11 keystone runnable in CI. The spec Section 1 showed `brands/locksmith/` as gitignored; this plan narrows the ignore to the trust files.
