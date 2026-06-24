# White-Label Branding Engine — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorm) — ready for implementation plan
**Repo:** locksmith (`~/code/locksmith`)
**Depends on:** the publisher operator CLI + trust-root bootstrap being live (done — `incept`/`gen-anchor`/`anchor`/`publish` shipped, Locksmith 0.1.7 anchored & published, gate live).

## Summary

Turn Locksmith into a **reusable white-label engine**: one codebase that builds into several fully
independent, differently-branded desktop apps from a per-brand manifest. Each brand is its own OS/update
*product* — its own display name, app icon, splash, in-app logos, theme accent, support URLs, OS bundle
identity, **and its own KERI publisher trust root**. "Locksmith" becomes brand #1 (the reference brand),
so the engine proves itself by reproducing today's app byte-for-identity.

The design formalizes a pattern the repo already uses: `publisher_anchor.json` + `deploy_config.json` are
already gitignored and build-injected. A brand is simply a bundle of **{identity + assets + theme + that
anchor/deploy_config pair}**, selected at build time and fed into two consumers — the running app (a small
runtime `brand.json`) and the packaging/publisher pipeline (generated installer files + staged assets).

## Locked decisions (from brainstorm)

1. **Reusable white-label engine** (not a one-off rebrand): one source → N branded builds.
2. **Per-brand publisher** (full isolation): each brand runs its own `incept`/`gen-anchor` ceremony → its
   own publisher AID, CDN/domain, federation choice, `deploy_config`. Maximum independence (a partner can
   self-publish their edition).
3. **Full brand surface incl. theme:** display name + OS app/dock/tray/window icon + splash + in-app SVG
   logos (toolbar wordmark, About logo) + About/support/website URLs + manufacturer/org name + a per-brand
   accent palette.
4. **Architecture A — manifest + build-time generation:** one `brands/<brand>/brand.toml` is the single
   source of truth; a `brand apply` build step renders the templated installer files, stages assets, writes
   a runtime `brand.json`, and injects the anchor/deploy_config. Brand selected via `$LOCKSMITH_BRAND`
   (default `locksmith`).
5. **Locksmith is brand #1.** Its manifest reproduces today's exact identity — existing users see zero change.
6. **Theme is an override, not a redefinition:** a brand supplies ~4 accent colors; the ~55 neutral/semantic
   colors stay shared as defaults in `ui.colors`.

## Why this shape (grounded in the code)

The brand name "Locksmith" is **scattered, not centralized**: ~4 hard-coded UI strings (`window.py:58`,
`window.py:612`, `toolbar.py:101`, `styles.py:63`), a dynamic title (`drawer.py:735`), an *unused*
`LocksmithConfig.appName='Locksmith'` constant (`configing.py:50`), plus ~40 references across packaging
(`Locksmith.macos.spec`, `Locksmith.windows.spec`, `wix/Locksmith.wxs`, `dmg/layout.json`) and the publisher
CLI's hard-coded artifact name (`cli.py:283`). The theme is already centralized in `ui.colors` (~60 flat hex
constants) feeding an f-string QSS in `styles.py:set_global_styles`, of which only a handful are brand accent.

A white-label engine is therefore three coupled layers — runtime UI, build-time packaging identity, and the
update/trust pipeline — tied together by one manifest schema.

## Repo layout & privacy

```
brands/
  example/                      # COMMITTED template — example.com / placeholder only
    brand.toml
    AppIcon.icns, AppIcon.ico, SplashScreen.png, *Logo*.svg
    publisher_anchor.example.json
    deploy_config.example.json
  locksmith/                    # GITIGNORED real brand (brand #1 — today's app)
    brand.toml
    <assets…>
    publisher_anchor.json       # the trust root minted in the publisher bootstrap
    deploy_config.json
```

Real brand dirs (carrying domains, AIDs, the anchor) are **gitignored**; only `brands/example/` with
`example.com` placeholders is committed — identical to the existing `deploy_config`/`publisher_anchor`
privacy rule (`.gitignore` + `*.example.json` templates).

## The brand manifest (`brands/<brand>/brand.toml`)

```toml
[brand]
id            = "locksmith"          # slug → $LOCKSMITH_BRAND, asset dir name
display_name  = "Locksmith"          # every visible name (UI + OS)
tagline       = "KERI identity vault"
manufacturer  = "KERI.host"          # WiX Manufacturer / org name

[identity]                            # unique & immutable-once-shipped per brand
bundle_id       = "host.keri.locksmith"   # CFBundleIdentifier + Sparkle update scoping
upgrade_code    = "297BBF26-821C-4D56-8857-309C7B531E21"  # WiX UpgradeCode — mint a NEW GUID per brand
data_dir        = "Locksmith"             # App Support / LOCALAPPDATA folder; Linux lowercases
artifact_prefix = "Locksmith"             # {prefix}-{version}.dmg / .msi
org_domain      = "keri.host"             # setOrganizationDomain / QSettings location

[urls]
website         = "https://locksmith.app"
support         = "https://locksmith.app/support"
appcast_macos   = "https://releases.keri.host/appcast/v1/macos.json"
appcast_windows = "https://releases.keri.host/appcast/v1/windows.json"

[theme]                               # overrides into ui.colors — accent set only
primary         = "#F57B03"
primary_hover   = "#D66A02"
primary_pressed = "#E67E00"
toolbar_dark    = "#1A252C"
# all other colors (neutrals, danger/success) inherit the shared defaults

[assets]                              # filenames relative to the brand dir
app_icon_icns = "AppIcon.icns"
app_icon_ico  = "AppIcon.ico"
splash        = "SplashScreen.png"
symbol_logo   = "SymbolLogo.svg"
name_logo     = "NameLogo.svg"
full_logo     = "FullLogo.svg"
symbol_logo_black = "SymbolLogoBlack.svg"
name_logo_black   = "NameLogoBlack.svg"
full_logo_black   = "FullLogoBlack.svg"

[publisher]                           # pointers to this brand's gitignored trust material
anchor        = "publisher_anchor.json"
deploy_config = "deploy_config.json"
```

## Architecture — two flows

The manifest feeds two consumers, split by what each needs and when.

### Runtime flow (what the app reads at startup)

`brand apply` writes a small **`brand.json`** into `src/locksmith/release/` (gitignored; loaded exactly like
`deploy_config.json` — loader order `$LOCKSMITH_BRAND_CONFIG` → injected file → `example`). It carries only
the runtime subset:

```json
{ "display_name": "Locksmith", "tagline": "KERI identity vault",
  "org_name": "keri.host", "org_domain": "keri.host",
  "website": "https://locksmith.app", "support": "https://locksmith.app/support",
  "theme": { "primary": "#F57B03", "primary_hover": "#D66A02",
             "primary_pressed": "#E67E00", "toolbar_dark": "#1A252C" } }
```

A new `locksmith.core.branding` module exposes `brand()` (cached load). The scattered hard-codes then resolve
to one source:

- `styles.py` → `app.setApplicationName(brand().display_name)`, `setOrganizationName(brand().org_name)`,
  `setOrganizationDomain(brand().org_domain)`; app icon from the staged `assets/custom/AppIcon.icns`.
- `window.py:58`, `window.py:612`, `toolbar.py:101` → `brand().display_name`.
- `drawer.py:735` → `f"{brand().display_name} | {vault_name}"`.
- `configing.py:50` → the dead, unused `appName='Locksmith'` constant is removed (its role is replaced by `brand().display_name`).
- `ui.colors` gains `_apply_overrides()` called once at startup: module constants remain the defaults, then
  `brand().theme` overwrites the accent names **before** `set_global_styles` builds the QSS. Widgets reading
  `colors.PRIMARY` at render time pick up the override.

### Build flow (`scripts/brand_apply.py`, selected by `$LOCKSMITH_BRAND`, default `locksmith`)

A hybrid that minimizes new machinery — the PyInstaller specs are already Python:

1. **Python specs read the manifest directly.** A shared `packaging/brandlib.py:load_brand()` lets
   `Locksmith.macos.spec` / `Locksmith.windows.spec` pull `display_name`, `bundle_id`, `CFBundle*`,
   `SUFeedURL`, icon path, and artifact name from the active brand. No template engine for these.
2. **Non-Python files are rendered** from small templates: `wix/Locksmith.wxs` (Name, Manufacturer,
   UpgradeCode, ARP URLs, install/start-menu folder names, registry keys, shortcut text, icon id) and
   `dmg/layout.json` (volume name, app name).
3. **Assets stage in place.** Brand assets copy over `assets/custom/` using the **same filenames**
   (`AppIcon.icns`, `SplashScreen.png`, `SymbolLogo.svg`, …). `resources.qrc` and every spec reference are
   untouched — same logical names, different bytes. No qrc edits.
4. **Trust material injects.** The brand's `publisher_anchor.json` + `deploy_config.json` copy into their
   existing expected gitignored paths.
5. **`brand.json` is written** for the runtime flow.

The publisher CLI also becomes brand-aware: its hard-coded `Locksmith-{version}.{dmg,msi}` (`cli.py:283`)
reads `brand().artifact_prefix`, and feed paths come from the brand's `deploy_config`.

The win: only two file types get a template engine (the WiX XML + one JSON); the Python build files just
import the manifest, and assets ride existing filenames so the qrc/spec wiring never changes.

## Per-brand identity is immutable once shipped

Five fields define a brand as a distinct OS/update product; changing them after release breaks installed
users, so the manifest treats them as write-once and the validator flags drift against last-shipped values:

| Field | Why immutable |
|---|---|
| `bundle_id` | macOS Sparkle scopes updates by it — changing it stops installed users seeing updates |
| `upgrade_code` | WiX upgrade chain — **mint a fresh GUID per brand**; reusing Locksmith's collides |
| `data_dir` | the user's vaults live there — changing it orphans their data |
| `artifact_prefix` | the appcast points at `{prefix}-{version}.dmg/.msi` |
| `appcast_*` URLs | the feed identity an installed build polls |

Each brand keeps its own stable `data_dir`, so there is **no cross-brand data migration** — a new brand has
no existing users, and Locksmith keeps `Locksmith`, leaving today's users untouched.

## Publishing a new brand (reuses the operator CLI)

A one-time ceremony, then the normal release loop:

1. Provision the brand's infra: domain/CDN/S3, signing certs (Apple Developer-ID / Azure), a fresh
   `UpgradeCode` GUID, federation choice in its `deploy_config`.
2. `publisher incept` → `gen-anchor` against **that brand's** witnesses → its `publisher_anchor.json` (the
   exact flow that minted Locksmith's root).
3. `LOCKSMITH_BRAND=<brand>` → CI builds/signs/notarizes → `anchor` → `publish` → `verify_artifact`. Each
   brand's KERI gate goes live on its own first anchored build, just like Locksmith 0.1.7.

## Error handling / validation (fail-closed)

`scripts/check-brand-complete.py` (the `check-anchor-present.py` analog), run for tagged release builds,
rejects and **stops the build** on: any missing asset file; `example.com`/placeholder URLs; a
placeholder/missing publisher anchor; missing immutable-identity fields; or a non-`locksmith` brand still
carrying Locksmith's `bundle_id`/`upgrade_code`. No silently half-branded release ships.

Per-step:
- `brand apply`: fail loudly if the selected brand dir or a referenced asset is missing (no partial stage).
- Manifest load: fail on missing required field or malformed value (typed parse).
- `.wxs`/`layout.json` render: fail if a substituted value is empty.

## Testing (machine-checkable, real paths, no mocks)

- **Unit:** manifest load/validate (required fields, types); theme merge (brand `primary` overrides, neutrals
  inherit); `brand.json` shape; `.wxs`/`layout.json` render → exact expected strings for a fixture brand;
  `check-brand-complete` rejects each defect class.
- **Integration:** `brand apply` for a synthetic `acme` fixture brand → assert generated `.wxs` has Acme's
  Name/UpgradeCode, `layout.json` the Acme volume name, `brand.json` the Acme display name, assets staged;
  plus a runtime assert — load the Acme `brand.json` → window title / app name / accent color reflect it.
- **Regression (keystone):** building the `locksmith` brand reproduces **today's** identity exactly —
  `bundle_id == host.keri.locksmith`, `UpgradeCode` unchanged, name `Locksmith`, accent `#F57B03`. Proves
  zero regression for existing users.
- Run tests with `.venv/bin/python -m pytest … --import-mode=importlib` (the repo's `packaging/` shadow rule).

## Scope & phasing

One cohesive spec, naturally three phases:

- **Phase 1 — runtime:** `core.branding` module + `brand.json` + wire UI strings and `ui.colors` overrides.
  Locksmith brand reproduces today's UI. Testable alone.
- **Phase 2 — build:** specs read the manifest; `.wxs`/`layout.json`/`brand.json` generated; asset staging;
  `check-brand-complete`; publisher CLI brand-aware. Locksmith brand reproduces today's packaging.
- **Phase 3 — prove it:** stand up one real second brand end-to-end (its own publisher ceremony + a
  signed/anchored/published edition). **Gated on that brand's real infra** (domain, certs) — like the
  publisher's Task 9 — so it may land as a follow-up.

**Out of scope:** runtime brand-switching (a build is one brand); migrating existing users *between* brands;
auto-minting the `UpgradeCode` (operator mints + records it per brand, documented); localization; any
brand-management UI.

## Definition of done

A `brands/<brand>/brand.toml` manifest schema + `brands/example/` committed template exist; the app reads a
runtime `brand.json` so no user-visible "Locksmith" string is hard-coded (display name, org, URLs, accent all
flow from the manifest); `brand_apply.py` stages assets, renders the WiX/DMG files, injects anchor +
deploy_config, and writes `brand.json`; the PyInstaller specs + publisher CLI read the active brand;
`check-brand-complete.py` fails the build on an incomplete/placeholder brand; the regression test proves the
`locksmith` brand reproduces today's identity exactly; and a synthetic second brand builds through
`brand apply` with all generated artifacts asserted. (Phase 3 — a real second published brand — is gated on
that brand's infrastructure.)

## Risks

1. **`ui.colors` override timing.** Overrides must be applied before `set_global_styles` builds the QSS and
   before any widget caches a color. *Mitigation:* `_apply_overrides()` runs in app bootstrap ahead of
   `set_global_styles`; the theme-merge unit test pins it.
2. **Asset stage-in-place mutates the working tree.** `brand apply` overwrites `assets/custom/`. *Mitigation:*
   the canonical committed assets are the `locksmith` brand's; CI stages from the selected brand dir into a
   clean checkout, and `brand apply --check` can verify without writing. Document that local dev runs
   `LOCKSMITH_BRAND=locksmith` (the default) to restore.
3. **Forgetting a fresh `UpgradeCode`/`bundle_id` for a new brand** → installer/update collision with another
   brand. *Mitigation:* `check-brand-complete` rejects a non-`locksmith` brand reusing Locksmith's values.
4. **Half-branded release** (a missed surface). *Mitigation:* the validator's asset+URL completeness check
   plus the integration test asserting every generated surface for the fixture brand.
5. **Per-brand publisher operational load.** Each brand needs its own ceremony + infra. *Accepted:* inherent
   to the per-brand-publisher decision; Phase 3 is explicitly gated on a brand's real infra.
