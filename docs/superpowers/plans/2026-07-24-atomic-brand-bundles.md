# Atomic Runtime-Resolved Brand Bundles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a Locksmith brand a self-contained bundle resolved at runtime (`brand.json` + `assets.rcc`), so `brand_apply` never mutates tracked files and no env path can produce a logo/config mismatch.

**Architecture:** `brand_apply --brand X --out <dir>` generates a per-brand aliased `.qrc` (neutral assets from `assets/`, brand logo slots aliased to `brands/X/`), compiles it to `<dir>/assets.rcc`, and writes `brand.json` + packaging files + staged `egf/`/`AppIcon.*` there — touching nothing tracked. At startup the app registers exactly one `assets.rcc` via `QResource.registerResource()` (sibling to the resolved `brand.json`), so logos, splash, fonts, and config all come from the same brand source. The tracked, generated `resources_rc.py` is deleted.

**Tech Stack:** Python 3, PySide6 6.10.3 (`pyside6-rcc --binary`, `QResource`), pytest (headless `QT_QPA_PLATFORM=offscreen`), tomllib.

## Global Constraints

- **PySide6 6.10.3**; `pyside6-rcc --binary <qrc> -o <out>.rcc` produces the binary bundle; `QResource.registerResource(path)` / `unregisterResource(path)` register/detach it. Registration is static (no `QApplication`); `QPixmap`/`QImage`/`QFontDatabase` construction needs a `QApplication`.
- **Per-worktree venv.** Run pytest headless + focused: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest <path> --import-mode=importlib -p no:cacheprovider`. NEVER run the full suite, `tests/peer`, or subprocess-spawning suites (they crash macOS). After entry-point / `pyproject` edits: `.venv/bin/pip install -e . --no-deps`.
- **No tracked-file mutation** is the whole point: after any `brand_apply` run, `git status --porcelain` over tracked paths MUST be empty. Generated artifacts live only under gitignored `src/locksmith/release/…`.
- **Fail loud:** missing `pyside6-rcc`, an empty/failed `.rcc` compile, or a missing `.rcc` at launch must raise / exit non-zero — never warn-and-continue.
- **Domain-neutral:** framework code stays brand-agnostic; brand specifics live only in `brands/<id>/` + the bundle. The reference brand is `locksmith`; `brands/example/` is a docs-only template (no asset files).
- **The 8 `:/`-resource brand slots** (compiled into `assets.rcc`): `SplashScreen.png`, `SymbolLogo.svg`, `SymbolLogoWhite.svg`, `SymbolLogoBlack.svg`, `NameLogo.svg`, `NameLogoBlack.svg`, `FullLogo.svg`, `FullLogoBlack.svg`. The 2 app-icon slots (`AppIcon.icns`, `AppIcon.ico`) are staged as **files** into `<out>/` (embedded at freeze / used as the runtime window icon), never compiled into the `.rcc`.
- **Canonical resource prefix stays `:/assets/custom/<file>`** for logos/splash so the existing call sites (`ui/toolbar.py:92`, `ui/home.py:52`, `ui/styles.py:76`, `ui/vaults/drawer.py:126`) need no changes.

## File Structure

- `brands/locksmith/` — **gains** the reference logo/splash/app-icon files (moved from `assets/custom/`); becomes a full brand like `brands/usurance/`. `brand.toml` already lists them under `[assets]`.
- `assets/` — the strictly brand-**neutral** shared pool (`material-icons/`, `fonts/`, `kerifoundation/`, `cloud_lock.svg`, neutral `custom/*.png` nav glyphs, `custom/flags/`, `custom/step-icon-*.png`, `custom/dmgBackground.jpeg`, `custom/connector.png`). Never mutated by a brand build.
- `resources.qrc` — regenerated neutral-only list (source of truth for the neutral pool).
- `scripts/generate_qrc.py` — gains `build_brand_qrc(...)` that emits a per-brand aliased qrc.
- `scripts/brand_apply.py` — rewritten: qrc→`.rcc` into `<out>`, all outputs to `<out>`, fail loud, `--out` flag, no tracked mutation.
- `packaging/brandlib.py` — gains `brand_release_dir(brand_id)`.
- `src/locksmith/core/branding.py` — gains `brand_source_dir()`, `brand_assets_rcc()`, `register_brand_resources()`.
- `src/locksmith/main.py` — drop `import resources_rc`; splash from `:/`.
- `src/locksmith/ui/styles.py` — register bundle first; window-icon from bundle dir; font from `:/`.
- `src/locksmith/resources_rc.py` — **deleted** + gitignored.
- `packaging/Locksmith.macos.spec`, `Locksmith.windows.spec`, `build-macos.sh`, `build-windows.ps1` — read from the brand release dir; bundle `assets.rcc`; drop the loose `assets/` tree from the freeze.
- Tests under `tests/unit/branding/` and `tests/packaging/` updated; new atomicity + fail-loud tests.
- Docs: `docs/developer-guide.rst`, `README.md`, `CLAUDE.md`, and ugard `docs/demos/2026-07-21-hoa-multi-role-live-demo.md`.

---

### Task 1: Reorg — split brand-specific assets out of the neutral pool

**Files:**
- Move (git): `assets/custom/{SplashScreen.png, SymbolLogo.svg, SymbolLogoWhite.svg, SymbolLogoBlack.svg, NameLogo.svg, NameLogoBlack.svg, FullLogo.svg, FullLogoBlack.svg, AppIcon.icns, AppIcon.ico}` → `brands/locksmith/`
- Modify: `resources.qrc` (regenerated)
- Test: `tests/unit/branding/test_asset_reorg.py` (Create)

**Interfaces:**
- Produces: `brands/locksmith/` now contains the 8 logo/splash files + 2 app-icons with canonical filenames; `assets/custom/` contains only neutral assets; `resources.qrc` lists only neutral files.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/branding/test_asset_reorg.py
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
BRAND_SLOTS = ["SplashScreen.png", "SymbolLogo.svg", "SymbolLogoWhite.svg",
               "SymbolLogoBlack.svg", "NameLogo.svg", "NameLogoBlack.svg",
               "FullLogo.svg", "FullLogoBlack.svg", "AppIcon.icns", "AppIcon.ico"]

def test_brand_slots_moved_to_locksmith_brand():
    for f in BRAND_SLOTS:
        assert (REPO / "brands" / "locksmith" / f).is_file(), f"missing brands/locksmith/{f}"
        assert not (REPO / "assets" / "custom" / f).exists(), f"assets/custom/{f} should be gone"

def test_neutral_assets_stay():
    for f in ["settings.png", "vault.png", "flags/us.svg", "step-icon-check.png"]:
        assert (REPO / "assets" / "custom" / f).is_file()

def test_resources_qrc_is_neutral_only():
    qrc = (REPO / "resources.qrc").read_text()
    assert "assets/custom/SymbolLogo.svg" not in qrc
    assert "assets/custom/FullLogo.svg" not in qrc
    assert "assets/custom/settings.png" in qrc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_asset_reorg.py --import-mode=importlib -p no:cacheprovider -q`
Expected: FAIL (files still in `assets/custom/`, qrc still lists logos).

- [ ] **Step 3: Move the files and regenerate the qrc**

```bash
cd /Users/seriouscoderone/code/locksmith
for f in SplashScreen.png SymbolLogo.svg SymbolLogoWhite.svg SymbolLogoBlack.svg \
         NameLogo.svg NameLogoBlack.svg FullLogo.svg FullLogoBlack.svg AppIcon.icns AppIcon.ico; do
  git mv "assets/custom/$f" "brands/locksmith/$f"
done
.venv/bin/python scripts/generate_qrc.py   # rewrites ./resources.qrc from ./assets (now neutral-only)
```

Confirm `brands/locksmith/brand.toml`'s `[assets]` filenames exactly match the moved files (they already do — canonical names). No toml edit expected; if a name differs, fix the toml value.

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_asset_reorg.py --import-mode=importlib -p no:cacheprovider -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A brands/locksmith assets/custom resources.qrc tests/unit/branding/test_asset_reorg.py
git commit -m "refactor(brand): move reference logos/splash/app-icons to brands/locksmith; assets/ becomes neutral-only"
```

- [ ] **Step 6: Keep the focused test surface green — fix the disk-path readers of the moved files**

The `git mv` breaks code/tests that read the moved brand files from the OLD `assets/custom/` disk path (the `:/` call sites still resolve off the stale tracked `resources_rc.py` until Task 6). Handle each:

- **Permanent fixes (new source location is final) — do them here:**
  - `tests/unit/branding/test_kf_icon_brand_independent.py:27` — change the reference from `assets/custom/SymbolLogo.svg` to `brands/locksmith/SymbolLogo.svg` (the reference symbol lives there now). Leave the tmp_path fake-repo lines (39-40, 60) untouched.
  - `tests/packaging/test_appicon_windows.py:12` — change `ICO = REPO_ROOT / "assets" / "custom" / "AppIcon.ico"` to `REPO_ROOT / "brands" / "locksmith" / "AppIcon.ico"`.
- **Bridge (behavior changes to `:/` in Task 5) — xfail with a tracking reason here:**
  - `tests/unit/test_splash.py` — the disk-path test (`test_make_splash_returns_splashscreen_when_art_present`) breaks because `main.py:137` reads the moved `assets/custom/SplashScreen.png`. Mark it `@pytest.mark.xfail(reason="_make_splash moves to :/ in Task 5 (atomic-brand-bundles)", strict=False)`. Task 5 removes the xfail and rewrites the test for the `:/` path.
- **Deferred to their named tasks (NOT changed here) — tracked, mostly not test-covered:** `src/locksmith/main.py:137` + `src/locksmith/ui/styles.py:62` (Task 5); `packaging/Locksmith.macos.spec:194`, `packaging/Locksmith.windows.spec:33`, `packaging/build-macos.sh:111`, `packaging/build-appicon.py:37-43` (Task 8).

- [ ] **Step 7: Re-run the focused surface + commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_asset_reorg.py tests/unit/branding/test_kf_icon_brand_independent.py tests/packaging/test_appicon_windows.py tests/unit/test_splash.py --import-mode=importlib -p no:cacheprovider -q`
Expected: all pass (test_splash's disk test shows as xfail). Then amend the commit (or add a follow-up commit) including the reader fixes.

> Note: after this task the app still boots off the (stale-but-present) tracked `resources_rc.py`; the runtime switch happens in Tasks 4–6. The `assets/custom/` disk-path readers listed above are fixed here (tests) or deferred to Tasks 5/8 (production).

---

### Task 2: Per-brand aliased qrc generator

**Files:**
- Modify: `scripts/generate_qrc.py`
- Test: `tests/unit/branding/test_build_brand_qrc.py` (Create)

**Interfaces:**
- Produces: `generate_qrc.build_brand_qrc(repo_root: Path, brand_dir: Path, manifest: dict) -> str` returning qrc XML. Neutral files under `assets/` are emitted as `<file>assets/…</file>` (verbatim, relative to `repo_root`). Each of the 8 `:/`-resource brand slots is emitted as `<file alias="assets/custom/<canonical>"><source-relative-to-repo_root></file>`, where source = `brands/<id>/<file>` if present, else the `_VARIANT_FALLBACK` base, else `brands/locksmith/<canonical>`.
- Consumes (from Task 1): `assets/` is neutral-only; `brands/locksmith/` holds the reference slot files.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/branding/test_build_brand_qrc.py
import importlib, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "packaging"))
gen = importlib.import_module("generate_qrc")
brandlib = importlib.import_module("brandlib")

def test_usurance_qrc_aliases_logos_to_brand_dir():
    m = brandlib.load_brand_manifest("usurance")
    qrc = gen.build_brand_qrc(REPO, REPO / "brands" / "usurance", m)
    # brand logo aliased to the usurance source
    assert '<file alias="assets/custom/SymbolLogo.svg">brands/usurance/SymbolLogo.svg</file>' in qrc
    assert '<file alias="assets/custom/SplashScreen.png">brands/usurance/SplashScreen.png</file>' in qrc
    # a neutral asset is present verbatim
    assert "<file>assets/custom/settings.png</file>" in qrc
    # app-icons are NOT compiled into the rcc
    assert "AppIcon.icns" not in qrc

def test_locksmith_qrc_uses_reference_slots():
    m = brandlib.load_brand_manifest("locksmith")
    qrc = gen.build_brand_qrc(REPO, REPO / "brands" / "locksmith", m)
    assert '<file alias="assets/custom/SymbolLogo.svg">brands/locksmith/SymbolLogo.svg</file>' in qrc

def test_missing_variant_falls_back_to_standard(tmp_path):
    # brand ships only the standard symbol → white/black alias its standard file
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "assets" / "custom" / "settings.png").write_text("x")
    bd = tmp_path / "brands" / "acme"; bd.mkdir(parents=True)
    for f in ["SplashScreen.png","SymbolLogo.svg","NameLogo.svg","NameLogoBlack.svg","FullLogo.svg","FullLogoBlack.svg"]:
        (bd / f).write_text("x")
    manifest = {"brand": {"id": "acme"}, "assets": {
        "splash":"SplashScreen.png","symbol_logo":"SymbolLogo.svg",
        "name_logo":"NameLogo.svg","name_logo_black":"NameLogoBlack.svg",
        "full_logo":"FullLogo.svg","full_logo_black":"FullLogoBlack.svg"}}
    qrc = gen.build_brand_qrc(tmp_path, bd, manifest)
    assert '<file alias="assets/custom/SymbolLogoWhite.svg">brands/acme/SymbolLogo.svg</file>' in qrc
    assert '<file alias="assets/custom/SymbolLogoBlack.svg">brands/acme/SymbolLogo.svg</file>' in qrc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_build_brand_qrc.py --import-mode=importlib -p no:cacheprovider -q`
Expected: FAIL with `AttributeError: module 'generate_qrc' has no attribute 'build_brand_qrc'`.

- [ ] **Step 3: Implement `build_brand_qrc`**

```python
# append to scripts/generate_qrc.py
# Canonical resource filenames for the 8 :/-accessed brand slots, keyed by
# the brand.toml [assets] key. app_icon_* are intentionally excluded (staged
# as files, not compiled). Mirrors brand_apply._ASSET_KEYS minus app icons.
_QRC_SLOTS = {
    "splash": "SplashScreen.png",
    "symbol_logo": "SymbolLogo.svg",
    "symbol_logo_white": "SymbolLogoWhite.svg",
    "symbol_logo_black": "SymbolLogoBlack.svg",
    "name_logo": "NameLogo.svg",
    "name_logo_black": "NameLogoBlack.svg",
    "full_logo": "FullLogo.svg",
    "full_logo_black": "FullLogoBlack.svg",
}
# variant slot -> base slot used when a brand omits the variant
_QRC_VARIANT_FALLBACK = {
    "symbol_logo_white": "symbol_logo",
    "symbol_logo_black": "symbol_logo",
}


def _slot_source(repo_root, brand_dir, manifest, slot, canonical):
    """Repo-relative POSIX path of the file that should back this slot."""
    assets = manifest.get("assets", {})
    fname = assets.get(slot)
    if fname and (brand_dir / fname).is_file():
        return (brand_dir / fname).relative_to(repo_root).as_posix()
    base_slot = _QRC_VARIANT_FALLBACK.get(slot)
    if base_slot:
        base_fname = assets.get(base_slot)
        if base_fname and (brand_dir / base_fname).is_file():
            return (brand_dir / base_fname).relative_to(repo_root).as_posix()
    # reference default
    return (repo_root / "brands" / "locksmith" / canonical).relative_to(repo_root).as_posix()


def build_brand_qrc(repo_root, brand_dir, manifest) -> str:
    """Emit a per-brand qrc: neutral assets/ verbatim + brand logo-slot aliases."""
    from pathlib import Path
    repo_root = Path(repo_root); brand_dir = Path(brand_dir)
    lines = ['<RCC>', '    <qresource prefix="/">']
    for p in sorted((repo_root / "assets").rglob("*")):
        if p.is_file():
            lines.append(f'        <file>{p.relative_to(repo_root).as_posix()}</file>')
    for slot, canonical in _QRC_SLOTS.items():
        src = _slot_source(repo_root, brand_dir, manifest, slot, canonical)
        lines.append(f'        <file alias="assets/custom/{canonical}">{src}</file>')
    lines += ['    </qresource>', '</RCC>', '']
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_build_brand_qrc.py --import-mode=importlib -p no:cacheprovider -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_qrc.py tests/unit/branding/test_build_brand_qrc.py
git commit -m "feat(brand): per-brand aliased qrc generator (neutral verbatim + logo-slot aliases)"
```

---

### Task 3: Rewrite `brand_apply` — compile `.rcc` to `<out>`, all outputs to `<out>`, fail loud

**Files:**
- Modify: `scripts/brand_apply.py`
- Modify: `packaging/brandlib.py` (add `brand_release_dir`)
- Test: `tests/unit/branding/test_brand_apply.py` (rewrite)
- Test: `tests/packaging/test_usurance_brand_apply.py` (update — it currently asserts the OLD behavior: `apply()` staging over `assets/custom/AppIcon.icns` at line ~60. Change it to assert the usurance bundle now lands in `<out>` — `assets.rcc` + `brand.json` + staged `AppIcon.*` in the release dir — and that `assets/custom/` is NOT mutated.)

**Interfaces:**
- Consumes: `generate_qrc.build_brand_qrc` (Task 2); `brandlib.runtime_brand_json/render_wxs/render_dmg_layout`.
- Produces: `brandlib.brand_release_dir(brand_id: str, repo_root: Path = REPO_ROOT) -> Path` = `repo_root/src/locksmith/release` for `locksmith`, else `…/release/<brand_id>`. `brand_apply.apply(brand_id, repo_root, *, out: Path | None = None, check: bool = False) -> dict` writes into `out` (default `brand_release_dir`): `assets.rcc`, `brand.json`, `Locksmith.wxs`, `dmg-layout.json`, `AppIcon.icns/.ico`, `egf/`, trust jsons. Raises `SystemExit`/`RuntimeError` on rcc-tool failure. The report dict gains `"out"` and `"rcc"` keys.

- [ ] **Step 1: Add `brand_release_dir` to brandlib + its test**

```python
# packaging/brandlib.py  (add near REPO_ROOT)
def brand_release_dir(brand_id: str, repo_root: Path = REPO_ROOT) -> Path:
    """Where brand_apply writes a brand's generated bundle (gitignored).

    locksmith → src/locksmith/release/ (flat: preserves the no-env dev launch
    and the frozen _PACKAGED_BRAND_JSON path); every other brand → a namespaced
    subdir so brands never overwrite each other and the tree stays clean.
    """
    base = repo_root / "src" / "locksmith" / "release"
    return base if brand_id == DEFAULT_BRAND else base / brand_id
```

```python
# tests/unit/branding/test_brand_release_dir.py  (Create)
import importlib, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "packaging"))
brandlib = importlib.import_module("brandlib")

def test_locksmith_is_flat_release():
    assert brandlib.brand_release_dir("locksmith", REPO) == REPO/"src"/"locksmith"/"release"

def test_other_brand_is_namespaced():
    assert brandlib.brand_release_dir("usurance", REPO) == REPO/"src"/"locksmith"/"release"/"usurance"
```

- [ ] **Step 2: Write the failing brand_apply test (rewrite the file)**

```python
# tests/unit/branding/test_brand_apply.py  (replace entire file)
import importlib, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brand_apply = importlib.import_module("brand_apply")


@pytest.fixture
def fake_repo(tmp_path):
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "assets" / "custom" / "settings.png").write_bytes(b"NEUTRAL")
    (tmp_path / "packaging" / "wix").mkdir(parents=True)
    (tmp_path / "packaging" / "wix" / "Locksmith.wxs.in").write_text(
        '<Package Name="@@NAME@@" UpgradeCode="@@UPGRADE_CODE@@" />')
    (tmp_path / "src" / "locksmith" / "release").mkdir(parents=True)
    # reference brand must exist for slot fallback
    lock = tmp_path / "brands" / "locksmith"; lock.mkdir(parents=True)
    for f in ["SplashScreen.png","SymbolLogo.svg","SymbolLogoWhite.svg","SymbolLogoBlack.svg",
              "NameLogo.svg","NameLogoBlack.svg","FullLogo.svg","FullLogoBlack.svg"]:
        (lock / f).write_bytes(b"LOCK-"+f.encode())
    (lock / "AppIcon.icns").write_bytes(b"LOCK-ICNS"); (lock / "AppIcon.ico").write_bytes(b"LOCK-ICO")
    # acme brand ships its own symbol + app icon
    acme = tmp_path / "brands" / "acme"; acme.mkdir(parents=True)
    (acme / "brand.toml").write_text((REPO_ROOT/"brands"/"example"/"brand.toml").read_text()
        .replace('id            = "example"','id            = "acme"').replace("Example Vault","Acme"))
    for f in ["SplashScreen.png","SymbolLogo.svg","SymbolLogoWhite.svg","SymbolLogoBlack.svg",
              "NameLogo.svg","NameLogoBlack.svg","FullLogo.svg","FullLogoBlack.svg"]:
        (acme / f).write_bytes(b"ACME-"+f.encode())
    (acme / "AppIcon.icns").write_bytes(b"ACME-ICNS"); (acme / "AppIcon.ico").write_bytes(b"ACME-ICO")
    (acme / "publisher_anchor.json").write_text('{"publisher_aid":"EAcme"}')
    (acme / "deploy_config.json").write_text('{"s3_bucket":"acme"}')
    return tmp_path


def test_apply_writes_bundle_to_out_and_leaves_tree_clean(fake_repo):
    out = fake_repo / "src" / "locksmith" / "release" / "acme"
    report = brand_apply.apply("acme", fake_repo, out=out, check=False)
    # compiled rcc exists and is non-empty
    rcc = out / "assets.rcc"
    assert rcc.is_file() and rcc.stat().st_size > 0
    # config + packaging outputs land in <out>
    assert json.loads((out / "brand.json").read_text())["display_name"] == "Acme"
    assert 'Name="Acme"' in (out / "Locksmith.wxs").read_text()
    assert json.loads((out / "dmg-layout.json").read_text())["volume_name"] == "Acme"
    # app-icons staged as files (not in the rcc)
    assert (out / "AppIcon.icns").read_bytes() == b"ACME-ICNS"
    # trust material injected into <out>
    assert (out / "publisher_anchor.json").is_file()
    # NOTHING tracked was mutated: the neutral pool + packaging template untouched
    assert (fake_repo / "assets" / "custom" / "settings.png").read_bytes() == b"NEUTRAL"
    assert "@@NAME@@" in (fake_repo / "packaging" / "wix" / "Locksmith.wxs.in").read_text()
    assert not (fake_repo / "packaging" / "wix" / "Locksmith.wxs").exists()
    assert report["out"] == str(out)


def test_registered_rcc_resolves_brand_logo(fake_repo):
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import QResource, QFile, QIODevice
    out = fake_repo / "src" / "locksmith" / "release" / "acme"
    brand_apply.apply("acme", fake_repo, out=out, check=False)
    app = QGuiApplication.instance() or QGuiApplication([])
    assert QResource.registerResource(str(out / "assets.rcc"))
    try:
        f = QFile(":/assets/custom/SymbolLogo.svg"); f.open(QIODevice.ReadOnly)
        data = bytes(f.readAll()); f.close()
        assert data == b"ACME-SymbolLogo.svg"          # came from brands/acme, atomically
    finally:
        QResource.unregisterResource(str(out / "assets.rcc"))


def test_missing_rcc_tool_fails_loud(fake_repo, monkeypatch):
    monkeypatch.setattr(brand_apply.shutil, "which", lambda _n: None)
    monkeypatch.setattr(brand_apply, "_find_rcc", lambda: None)
    out = fake_repo / "src" / "locksmith" / "release" / "acme"
    with pytest.raises((SystemExit, RuntimeError)):
        brand_apply.apply("acme", fake_repo, out=out, check=False)


def test_check_mode_writes_nothing(fake_repo):
    out = fake_repo / "src" / "locksmith" / "release" / "acme"
    brand_apply.apply("acme", fake_repo, out=out, check=True)
    assert not (out / "assets.rcc").exists()
    assert not (out / "brand.json").exists()
```

- [ ] **Step 3: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_brand_apply.py tests/unit/branding/test_brand_release_dir.py --import-mode=importlib -p no:cacheprovider -q`
Expected: FAIL (`apply()` has no `out` kwarg; writes to old locations).

- [ ] **Step 4: Rewrite `scripts/brand_apply.py`**

Replace `_recompile_resources` and `apply`/`main` with the bundle build. Key points: `_find_rcc()` helper; compile via a temp qrc; raise on failure; all writes into `out`; `dmg-layout.json` filename; no writes to `assets/custom` or `packaging/`.

```python
import argparse, json, os, subprocess, shutil, sys, tempfile
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent.parent / "packaging"))
sys.path.insert(0, str(_THIS.parent))          # for generate_qrc
import brandlib          # noqa: E402
import generate_qrc      # noqa: E402

_ASSET_FILE_KEYS = ("app_icon_icns", "app_icon_ico")   # staged as files, not compiled


def _find_rcc() -> str | None:
    cand = Path(sys.executable).parent / "pyside6-rcc"
    return str(cand) if cand.exists() else shutil.which("pyside6-rcc")


def _compile_rcc(repo_root: Path, brand_dir: Path, manifest: dict, out_rcc: Path) -> None:
    rcc = _find_rcc()
    if not rcc:
        raise SystemExit("brand_apply: pyside6-rcc not found — cannot build assets.rcc "
                         "(install PySide6 in this environment). Refusing to ship stale logos.")
    qrc_text = generate_qrc.build_brand_qrc(repo_root, brand_dir, manifest)
    out_rcc.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".qrc", dir=repo_root, delete=False) as tf:
        tf.write(qrc_text); qrc_path = Path(tf.name)
    try:
        subprocess.run([rcc, "--binary", str(qrc_path), "-o", str(out_rcc)],
                       cwd=repo_root, check=True)
    finally:
        qrc_path.unlink(missing_ok=True)
    if not out_rcc.is_file() or out_rcc.stat().st_size == 0:
        raise SystemExit(f"brand_apply: rcc produced no output at {out_rcc}")


def apply(brand_id: str, repo_root: Path, *, out: Path | None = None, check: bool = False) -> dict:
    import tomllib
    brands_dir = repo_root / "brands"
    brand_dir = brands_dir / brand_id
    if not (brand_dir / "brand.toml").is_file():
        brand_dir = brands_dir / "example"
    manifest = tomllib.loads((brand_dir / "brand.toml").read_text(encoding="utf-8"))
    manifest["_dir"] = brand_dir
    if out is None:
        out = brandlib.brand_release_dir(brand_id, repo_root)
    wxs_tmpl = repo_root / "packaging" / "wix" / "Locksmith.wxs.in"

    assets = manifest.get("assets", {})
    staged_icons = [assets[k] for k in _ASSET_FILE_KEYS
                    if assets.get(k) and (brand_dir / assets[k]).is_file()]
    injected = [n for k, n in (("anchor", "publisher_anchor.json"),
                               ("deploy_config", "deploy_config.json"))
                if (s := manifest.get("publisher", {}).get(k)) and (brand_dir / s).is_file()]
    egf_src = brand_dir / "egf"
    egf_staged = sorted(p.name for p in egf_src.glob("*.json")) if egf_src.is_dir() else []

    report = {"brand": manifest["brand"]["id"], "out": str(out), "rcc": str(out / "assets.rcc"),
              "staged_icons": staged_icons, "injected": injected,
              "egf_staged": egf_staged, "check": check}
    if check:
        return report

    out.mkdir(parents=True, exist_ok=True)
    _compile_rcc(repo_root, brand_dir, manifest, out / "assets.rcc")
    (out / "brand.json").write_text(
        json.dumps(brandlib.runtime_brand_json(manifest), indent=2) + "\n", encoding="utf-8")
    (out / "Locksmith.wxs").write_text(
        brandlib.render_wxs(manifest, wxs_tmpl.read_text(encoding="utf-8")), encoding="utf-8")
    (out / "dmg-layout.json").write_text(
        json.dumps(brandlib.render_dmg_layout(manifest), indent=2) + "\n", encoding="utf-8")
    for k in _ASSET_FILE_KEYS:
        fn = assets.get(k)
        if fn and (brand_dir / fn).is_file():
            shutil.copyfile(brand_dir / fn, out / fn)
    for k, dst in (("anchor", "publisher_anchor.json"), ("deploy_config", "deploy_config.json")):
        src = manifest.get("publisher", {}).get(k)
        if src and (brand_dir / src).is_file():
            shutil.copyfile(brand_dir / src, out / dst)
    if egf_src.is_dir():
        egf_dst = out / "egf"
        if egf_dst.exists():
            shutil.rmtree(egf_dst)
        shutil.copytree(egf_src, egf_dst)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default=brandlib.active_brand_id())
    ap.add_argument("--out", default=None, help="output dir (default: brand_release_dir)")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = Path(args.out) if args.out else None
    print(json.dumps(apply(args.brand, brandlib.REPO_ROOT, out=out, check=args.check)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_brand_apply.py tests/unit/branding/test_brand_release_dir.py --import-mode=importlib -p no:cacheprovider -q`
Expected: PASS (all tests, incl. the registered-rcc atomicity and fail-loud tests).

- [ ] **Step 6: Smoke-build the real usurance + locksmith bundles**

Run:
```bash
.venv/bin/python scripts/brand_apply.py --brand locksmith
.venv/bin/python scripts/brand_apply.py --brand usurance
ls -la src/locksmith/release/assets.rcc src/locksmith/release/usurance/assets.rcc
git status --porcelain   # MUST be empty over tracked paths (only gitignored release/ churn, added in Task 7)
```
Expected: both `assets.rcc` present; no tracked file modified.

- [ ] **Step 7: Commit**

```bash
git add scripts/brand_apply.py packaging/brandlib.py \
        tests/unit/branding/test_brand_apply.py tests/unit/branding/test_brand_release_dir.py
git commit -m "feat(brand): brand_apply builds self-contained assets.rcc into release/<brand>/; fail loud; no tracked mutation"
```

---

### Task 4: Runtime registration — `register_brand_resources()` in branding.py

**Files:**
- Modify: `src/locksmith/core/branding.py`
- Test: `tests/unit/branding/test_register_resources.py` (Create)

**Interfaces:**
- Consumes: `brand_apply.apply(...)` bundles (Task 3); `load_brand()`/`brand()` set `_brand_source_dir`.
- Produces: `branding.brand_source_dir() -> Path | None`; `branding.brand_assets_rcc() -> Path | None` (= `<dir>/assets.rcc` if it exists); `branding.register_brand_resources() -> Path` (ensures brand resolved, registers the rcc, returns its path; raises `RuntimeError` if no bundle / registration fails); `branding.unregister_brand_resources() -> None` (detaches the last-registered bundle — for test isolation). `branding` stays importable without Qt (lazy `QResource` import inside the functions).

> **Qt-resource precedence — VERIFIED first-registered-wins.** When two `.rcc`s register overlapping paths (e.g. `:/assets/custom/SymbolLogo.svg`), the FIRST registration wins; a later one does NOT override it. Consequences: (a) the real app registers exactly once at startup — no issue; (b) **tests must never leave a bundle registered across a brand switch** — always `unregister` before registering a different brand, and never auto-register a default globally (Task 6). Brand-override tests register their own bundle from a clean state and unregister in a `finally`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/branding/test_register_resources.py
import importlib, os, sys
from pathlib import Path
import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "packaging"))
brand_apply = importlib.import_module("brand_apply")
from locksmith.core import branding
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QResource, QFile, QIODevice


@pytest.fixture
def usurance_bundle(tmp_path):
    out = tmp_path / "usu"
    brand_apply.apply("usurance", REPO, out=out, check=False)
    return out


def test_register_resolves_logo_and_config_from_same_source(monkeypatch, usurance_bundle):
    _ = QGuiApplication.instance() or QGuiApplication([])
    monkeypatch.setenv(branding.BRAND_CONFIG_ENV_VAR, str(usurance_bundle / "brand.json"))
    branding._reset_cache_for_tests()
    rcc = branding.register_brand_resources()
    try:
        assert branding.brand().display_name == "Usurance"          # config
        f = QFile(":/assets/custom/SymbolLogo.svg"); f.open(QIODevice.ReadOnly)
        logo = bytes(f.readAll()); f.close()
        assert logo == (REPO / "brands" / "usurance" / "SymbolLogo.svg").read_bytes()  # logo, same source
    finally:
        QResource.unregisterResource(str(rcc)); branding._reset_cache_for_tests()


def test_missing_bundle_raises(monkeypatch, tmp_path):
    only_json = tmp_path / "brand.json"
    only_json.write_text('{"display_name":"NoRcc"}')          # brand.json but NO assets.rcc sibling
    monkeypatch.setenv(branding.BRAND_CONFIG_ENV_VAR, str(only_json))
    branding._reset_cache_for_tests()
    with pytest.raises(RuntimeError):
        branding.register_brand_resources()
    branding._reset_cache_for_tests()
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_register_resources.py --import-mode=importlib -p no:cacheprovider -q`
Expected: FAIL (`branding` has no `register_brand_resources`).

- [ ] **Step 3: Implement in `branding.py`**

```python
# add to src/locksmith/core/branding.py
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
```

Also extend `_reset_cache_for_tests()` to detach any registered bundle:

```python
def _reset_cache_for_tests() -> None:
    global _brand_source_dir
    unregister_brand_resources()
    brand.cache_clear()
    _brand_source_dir = None
```

- [ ] **Step 4: Run to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_register_resources.py --import-mode=importlib -p no:cacheprovider -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/core/branding.py tests/unit/branding/test_register_resources.py
git commit -m "feat(brand): register_brand_resources() — atomic runtime .rcc registration, fail loud"
```

---

### Task 5: Boot off the bundle — `main.py` + `styles.py` (splash, window-icon, font)

**Files:**
- Modify: `src/locksmith/main.py:121` (drop `import resources_rc`), `src/locksmith/main.py:136-142` (splash via `:/`)
- Modify: `src/locksmith/ui/styles.py:52-95` (register first; window-icon from bundle dir; font via `:/`)
- Modify: `tests/unit/test_splash.py` (remove the Task-1 `xfail` on the disk-path test and rewrite it for the `:/` path — after this task `_make_splash()` loads `:/assets/custom/SplashScreen.png`; the test must register the default bundle first, e.g. via the `default_brand_resources` fixture from Task 6, or `set_global_styles`)
- Test: `tests/unit/branding/test_styles_boot.py` (Create)

**Interfaces:**
- Consumes: `branding.register_brand_resources()`, `branding.brand_source_dir()` (Task 4).
- Produces: `set_global_styles(app)` registers the brand bundle as its first action; splash + font resolve via `:/`.

> Note (from Task 1 review): the disk-path readers of the moved brand files that this task owns are `src/locksmith/main.py:137` (splash) and `src/locksmith/ui/styles.py:62` (window-icon). Task 1 xfailed `tests/unit/test_splash.py`; this task un-xfails and rewrites it. If Task 6 (which adds `default_brand_resources`) has not run yet when this task executes, register the bundle inline in the test instead (build the default bundle via `brand_apply.apply("locksmith", REPO, out=REPO/"src"/"locksmith"/"release")` then `branding.register_brand_resources()` in a fixture that unregisters after).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/branding/test_styles_boot.py
import importlib, os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "packaging"))
brand_apply = importlib.import_module("brand_apply")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap


def test_set_global_styles_registers_bundle_and_splash_resolves(monkeypatch):
    out = REPO / "src" / "locksmith" / "release"           # default locksmith bundle
    brand_apply.apply("locksmith", REPO, out=out, check=False)
    from locksmith.core import branding
    branding._reset_cache_for_tests()
    monkeypatch.delenv(branding.BRAND_CONFIG_ENV_VAR, raising=False)
    from locksmith.ui.styles import set_global_styles
    app = QApplication.instance() or QApplication([])
    set_global_styles(app)                                  # registers the rcc
    assert app.applicationName() == "Locksmith"
    assert not QPixmap(":/assets/custom/SplashScreen.png").isNull()   # splash via :/
```

- [ ] **Step 2: Run to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_styles_boot.py --import-mode=importlib -p no:cacheprovider -q`
Expected: FAIL (splash still disk-loaded / no registration → `:/` null, or `import resources_rc` needed).

- [ ] **Step 3: Edit `styles.py`**

At the very top of `set_global_styles(app)` (before `asset_root = _asset_root()` on line 55), register the bundle:

```python
def set_global_styles(app: QApplication):
    global MONOSPACE_FONT_FAMILY
    from locksmith.core import branding
    branding.register_brand_resources()      # single atomic asset surface — must be first
    asset_root = _asset_root()
```

Replace the disk window-icon block (lines 62-76) with a bundle-dir lookup + `:/` fallback:

```python
    # Runtime window/taskbar icon from the active brand's bundle dir (atomic
    # with the registered logos); the .app/.exe embedded icon is a packaging
    # concern. Fall back to the compiled symbol logo.
    _src = branding.brand_source_dir()
    _icon_names = (("AppIcon.icns", "AppIcon.ico") if sys.platform == "darwin"
                   else ("AppIcon.ico", "AppIcon.icns"))
    _set = False
    if _src is not None:
        for _name in _icon_names:
            cand = _src / _name
            if cand.exists():
                app.setWindowIcon(QIcon(str(cand))); _set = True; break
    if not _set:
        app.setWindowIcon(QIcon(":/assets/custom/SymbolLogo.svg"))
```

Change the font load (line 92) from the disk path to the resource path:

```python
    font_id = QFontDatabase.addApplicationFont(":/assets/fonts/SourceCodePro-Regular.ttf")
```
(Delete the now-unused `font_path = asset_root / "assets" / "fonts" / ...` line. If other `asset_root/assets/fonts/*` loads exist below, convert them to `:/assets/fonts/<name>` too — grep `assets" / "fonts` in the file.)

- [ ] **Step 4: Edit `main.py`**

Delete line 121 `from locksmith import resources_rc  # noqa: F401` (registration now happens in `set_global_styles`, called at `main.py:212` before the splash at 216).

In `_make_splash()` (line 136-138), replace the disk load with the resource path:

```python
    try:
        pixmap = QPixmap(":/assets/custom/SplashScreen.png")
        if pixmap.isNull():
            logger.warning("splash art not found at :/assets/custom/SplashScreen.png; skipping splash")
            return None
        return QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
```
(Remove the now-unused `from locksmith.ui.styles import _asset_root` and `path = …` lines inside `_make_splash`.)

- [ ] **Step 5: Reinstall entry point and run the test**

Run:
```bash
.venv/bin/pip install -e . --no-deps >/dev/null
QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_styles_boot.py --import-mode=importlib -p no:cacheprovider -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/main.py src/locksmith/ui/styles.py tests/unit/branding/test_styles_boot.py
git commit -m "feat(brand): boot off the registered brand bundle — splash/font via :/, window-icon from bundle dir"
```

---

### Task 6: Delete + gitignore `resources_rc.py`; make tests self-provision the default bundle

**Files:**
- Delete: `src/locksmith/resources_rc.py`
- Modify: `.gitignore`
- Create: `tests/conftest.py` (or extend existing) — session fixture building the default bundle
- Create: `tests/unit/branding/conftest.py` — test-isolation shims that make the WHOLE `tests/unit/branding/` dir run green regardless of order (removes both pre-existing baseline caveats). See "Step 1b" below. Reference content saved at `/tmp/stray_branding_conftest.py` (an out-of-scope investigation-scratch draft surfaced during Task 5 — do NOT copy it blindly; re-derive/verify it, it is unreviewed).
- Test: reuse Task 5's `test_styles_boot.py` + a guard test

**Interfaces:**
- Produces: (a) a session-scoped autouse fixture `_ensure_default_brand_bundle` that BUILDS `src/locksmith/release/{assets.rcc,brand.json}` once (if absent) — build only, it does NOT register (first-wins precedence forbids a global default registration, or brand-override tests would keep reading locksmith bytes); (b) a function-scoped opt-in fixture `default_brand_resources` that registers the default bundle for a single test and unregisters after — for generic widget/icon tests that load `:/` paths without going through `set_global_styles`.

- [ ] **Step 1b: Create `tests/unit/branding/conftest.py` — green the whole branding dir**

Two pre-existing, order-dependent issues make `pytest tests/unit/branding/` (whole dir) fail while each file passes alone. Both are now diagnosed; neutralise them in a branding-suite conftest so broad runs (this task's Step 4, Task 10) are deterministic:

1. **Qt singleton type.** Sibling tests create the process-wide Qt singleton as a bare `QGuiApplication`; `test_styles_branding` needs a `QApplication` (only it has `setStyle`, called by `set_global_styles`). Qt allows one app object per process, so a `QGuiApplication`-first order makes the styles tests crash. Fix: a session-scoped autouse fixture that creates the `QApplication` superset up front (`QApplication.instance() or QApplication([])`), so every later `*.instance()` resolves to it.
2. **`keri` namespace shadow (root cause).** `scripts/keri/` is a kli config-data dir (`cf/*.json`, no `__init__.py`). Sibling tests do `sys.path.insert(0, <repo>/scripts)` at import time, so the first `import keri` resolves to that PEP-420 namespace package (no `__version__`) → keripy's `from keri import __version__` raises `ImportError: ... 'keri' (unknown location)`. Fix: `import keri` at the TOP of this conftest (runs before any test's `sys.path.insert`), caching real keripy in `sys.modules` so the data dir can never win.

Write the conftest with `QT_QPA_PLATFORM` defaulted to `offscreen`, the early `import keri`, and the session-autouse `QApplication` fixture. A reference draft is at `/tmp/stray_branding_conftest.py` — verify its reasoning, don't trust it blindly. Confirm with: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding --import-mode=importlib -p no:cacheprovider -q` → the WHOLE dir passes (this retires baseline caveats #1 and #2 in the ledger). Note: `tests/unit/pytest.ini` makes `tests/unit` the rootdir, so a `tests/conftest.py` does NOT apply here (confcutdir) — the branding conftest must be its own file.

- [ ] **Step 1: Add the fixtures**

Check whether `tests/conftest.py` exists (`ls tests/conftest.py`). Create it if absent, else append:

```python
# tests/conftest.py
import importlib, sys
from pathlib import Path
import pytest

_REPO = Path(__file__).resolve().parents[1]


def _build_default_bundle():
    rcc = _REPO / "src" / "locksmith" / "release" / "assets.rcc"
    if not rcc.is_file():
        sys.path.insert(0, str(_REPO / "scripts")); sys.path.insert(0, str(_REPO / "packaging"))
        importlib.import_module("brand_apply").apply(
            "locksmith", _REPO, out=_REPO / "src" / "locksmith" / "release", check=False)
    return rcc


@pytest.fixture(scope="session", autouse=True)
def _ensure_default_brand_bundle():
    """Build (NOT register) the reference bundle once so :/ can be registered.

    resources_rc.py no longer exists; compiled assets live in the gitignored
    release/assets.rcc built by brand_apply. Registration is per-test, because
    Qt resource overlap is first-registered-wins — a global default would
    shadow brand-override tests. Cheap + idempotent.
    """
    _build_default_bundle()
    yield


@pytest.fixture
def default_brand_resources(monkeypatch):
    """Opt-in: register the default bundle for one test, then detach.

    For generic tests that load :/assets/... without calling set_global_styles.
    Do NOT combine with a brand-override in the same test (first-wins).
    """
    from locksmith.core import branding
    _build_default_bundle()
    monkeypatch.delenv(branding.BRAND_CONFIG_ENV_VAR, raising=False)
    branding._reset_cache_for_tests()
    rcc = branding.register_brand_resources()
    yield rcc
    branding._reset_cache_for_tests()   # unregisters (see Task 4)
```

- [ ] **Step 2: Delete the tracked blob and gitignore it**

```bash
git rm src/locksmith/resources_rc.py
```
Add to `.gitignore` (near the existing `release/brand.json` block):
```
# Generated Qt resource module — replaced by the per-brand release/assets.rcc
# built by scripts/brand_apply.py. Never committed.
src/locksmith/resources_rc.py
```

- [ ] **Step 3: Confirm nothing else imports `resources_rc`**

Run: `grep -rn "resources_rc" src/ tests/ packaging/ scripts/ | grep -v "\.gitignore"`
Expected: no hits (Task 5 removed the `main.py` import). If any remain, replace them with `from locksmith.core.branding import register_brand_resources; register_brand_resources()` at that entry point.

- [ ] **Step 4: Run the branding suite headless**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding tests/core/test_usurance_brand.py tests/core/test_branding_egf.py --import-mode=importlib -p no:cacheprovider -q`
Expected: PASS. If a generic widget/icon test fails with a null `:/` resource (it relied on the old `import resources_rc` side-effect), add the `default_brand_resources` fixture to it (or route it through the shared app fixture that calls `set_global_styles`). Such tests never switch brands, so first-wins is a non-issue for them.

- [ ] **Step 5: Commit**

```bash
git add -A .gitignore tests/conftest.py
git rm --quiet src/locksmith/resources_rc.py 2>/dev/null; git add -A src/locksmith
git commit -m "refactor(brand): untrack generated resources_rc.py; tests self-provision the default assets.rcc"
```

---

### Task 7: Untrack the generated packaging outputs; golden-fixture the wxs render test

**Files:**
- Untrack: `packaging/wix/Locksmith.wxs`, `packaging/dmg/layout.json`
- Modify: `.gitignore`
- Create: `tests/unit/branding/fixtures/locksmith.wxs.golden`
- Modify: `tests/unit/branding/test_render_packaging.py`

**Interfaces:**
- Produces: a committed golden wxs the render is checked against (replacing the "== committed tracked file" invariant, since the rendered wxs is no longer tracked).

- [ ] **Step 1: Snapshot the current locksmith render as the golden fixture**

```bash
mkdir -p tests/unit/branding/fixtures
.venv/bin/python - <<'PY'
import importlib, sys
from pathlib import Path
repo = Path.cwd()
sys.path.insert(0, str(repo / "packaging"))
b = importlib.import_module("brandlib")
tmpl = (repo/"packaging"/"wix"/"Locksmith.wxs.in").read_text()
out = b.render_wxs(b.load_brand_manifest("locksmith"), tmpl)
(repo/"tests"/"unit"/"branding"/"fixtures"/"locksmith.wxs.golden").write_text(out)
print("golden written")
PY
```

- [ ] **Step 2: Replace the "== committed" test with a golden test**

In `tests/unit/branding/test_render_packaging.py`, replace `test_render_wxs_locksmith_matches_committed_wxs_exactly` (lines 40-48) with:

```python
def test_render_wxs_locksmith_matches_golden():
    # The rendered wxs is generated (untracked); assert it matches a checked-in
    # golden so template/manifest drift is caught without tracking the output.
    repo = Path(__file__).resolve().parents[3]
    template = (repo / "packaging" / "wix" / "Locksmith.wxs.in").read_text()
    golden = (repo / "tests" / "unit" / "branding" / "fixtures" / "locksmith.wxs.golden").read_text()
    rendered = brandlib.render_wxs(brandlib.load_brand_manifest("locksmith"), template)
    assert rendered == golden
```

- [ ] **Step 3: Untrack the generated packaging files + gitignore**

```bash
git rm --cached packaging/wix/Locksmith.wxs packaging/dmg/layout.json
```
Add to `.gitignore`:
```
# Generated packaging artifacts — rendered per-brand into src/locksmith/release/<brand>/
# by scripts/brand_apply.py (Locksmith.wxs, dmg-layout.json) and no longer emitted
# to these tracked locations. Kept ignored so a stray legacy render can't be committed.
packaging/wix/Locksmith.wxs
packaging/dmg/layout.json
# Per-brand generated bundles (assets.rcc, brand.json, wxs, dmg-layout.json, egf/, icons).
src/locksmith/release/assets.rcc
src/locksmith/release/Locksmith.wxs
src/locksmith/release/dmg-layout.json
src/locksmith/release/AppIcon.icns
src/locksmith/release/AppIcon.ico
src/locksmith/release/*/
```

- [ ] **Step 4: Run the render test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding/test_render_packaging.py --import-mode=importlib -p no:cacheprovider -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A .gitignore tests/unit/branding/test_render_packaging.py tests/unit/branding/fixtures/locksmith.wxs.golden
git rm --cached packaging/wix/Locksmith.wxs packaging/dmg/layout.json 2>/dev/null
git commit -m "refactor(brand): untrack generated wxs/dmg-layout; golden-fixture the wxs render test"
```

---

### Task 8: Wire build scripts + PyInstaller specs to the brand release dir; drop the loose assets/ tree from the freeze

**Files:**
- Modify: `packaging/Locksmith.macos.spec`, `packaging/Locksmith.windows.spec`
- Modify: `packaging/build-macos.sh`, `packaging/build-windows.ps1`
- Modify: `packaging/build-appicon.py` (the icon/splash generator — its source SVGs + outputs moved to `brands/locksmith/` in Task 1; repoint `SVG`/`FULL_SVG`/`OUT_ICNS`/`OUT_ICO`/`OUT_SPLASH` at `brands/<brand>/`, defaulting to `brands/locksmith/`, and take a `--brand` argument)
- Test: `tests/packaging/test_spec_bundles_rcc.py` (Create) + existing `tests/packaging/test_spec_macos.py`/`test_spec_windows.py` updates

**Interfaces:**
- Consumes: `brandlib.brand_release_dir` (Task 3); `brand_apply` outputs.
- Produces: freezes that bundle `<release>/assets.rcc` + `<release>/brand.json` (flat into `locksmith/release`), use `<release>/AppIcon.icns` as the app icon, and no longer bundle the loose `assets/` tree; build scripts read wxs/dmg-layout from `<release>`.

> Note (from Task 1 review): the disk-path readers of the moved brand files that this task owns are `packaging/Locksmith.macos.spec:194` (`icon=…AppIcon.icns`), `packaging/Locksmith.windows.spec:33` (`WIN_ICON=…AppIcon.ico`), `packaging/build-macos.sh:111` (`--volicon`), and `packaging/build-appicon.py:37-43`. Repoint all of them at the brand release dir (icons the freeze consumes) or `brands/<brand>/` (the generator's source), never the old `assets/custom/`. Also VERIFY `packaging/wix/gen_ui_images.py:26` (`ASSETS = REPO/"assets"/"custom"`): if it reads any moved brand file (logo/splash), repoint it; if it only reads neutral UI images, leave it and say so in the report.

- [ ] **Step 1: Write a guard test for the macOS spec**

```python
# tests/packaging/test_spec_bundles_rcc.py
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]

def test_macos_spec_bundles_rcc_not_loose_assets():
    spec = (REPO / "packaging" / "Locksmith.macos.spec").read_text()
    assert "assets.rcc" in spec                       # the compiled bundle is shipped
    assert '(str(REPO_ROOT / "assets"), "assets")' not in spec   # loose tree dropped

def test_windows_spec_bundles_rcc():
    spec = (REPO / "packaging" / "Locksmith.windows.spec").read_text()
    assert "assets.rcc" in spec
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/packaging/test_spec_bundles_rcc.py --import-mode=importlib -p no:cacheprovider -q`
Expected: FAIL.

- [ ] **Step 3: Edit `Locksmith.macos.spec`**

Near the top (after `_BRAND = _brandlib.load_brand_manifest()`), compute the release dir:
```python
_RELEASE = _brandlib.brand_release_dir(_BRAND["brand"]["id"], REPO_ROOT)
```
In `datas` (line 54-77): remove `(str(REPO_ROOT / "assets"), "assets"),` and add the compiled bundle; keep brand.json (source it from `_RELEASE`):
```python
datas = [
    # (libsodium etc. unchanged)
    (str(_RELEASE / "assets.rcc"), "locksmith/release"),
    (str(_RELEASE / "brand.json"), "locksmith/release"),
    (str(_RELEASE / "publisher_anchor.json"), "locksmith/release"),
    (str(_RELEASE / "deploy_config.json"), "locksmith/release"),
    # egf staged dir → locksmith/release/egf (if present)
    *( [(str(_RELEASE / "egf"), "locksmith/release/egf")] if (_RELEASE / "egf").is_dir() else [] ),
]
```
Change the app icon (line 194) to the staged brand icon:
```python
    icon=str(_RELEASE / "AppIcon.icns") if (_RELEASE / "AppIcon.icns").exists() else None,
```

- [ ] **Step 4: Edit `Locksmith.windows.spec`** — mirror Step 3 (compute `_RELEASE`, drop loose `assets`, add `assets.rcc` + `brand.json` under `locksmith/release`, icon → `_RELEASE/AppIcon.ico`).

- [ ] **Step 5: Edit `build-macos.sh`**

Add a release-dir var after line 25:
```bash
export LOCKSMITH_RELEASE="$(.venv/bin/python -c "import sys;sys.path.insert(0,'packaging');import brandlib;print(brandlib.brand_release_dir('$LOCKSMITH_BRAND'))")"
```
Ensure the brand is applied before packaging (if not already): `.venv/bin/python scripts/brand_apply.py --brand "$LOCKSMITH_BRAND"`.
Change the dmg-coords read (line 94) from `packaging/dmg/layout.json` → `"$LOCKSMITH_RELEASE/dmg-layout.json"`, and `--volicon` (line 111) from `assets/custom/AppIcon.icns` → `"$LOCKSMITH_RELEASE/AppIcon.icns"`.

- [ ] **Step 6: Edit `build-windows.ps1`**

Compute `$releaseDir = python -c "...brandlib.brand_release_dir(...)"`; run `python scripts/brand_apply.py --brand $env:LOCKSMITH_BRAND`; change the `wix build` invocation (line ~145) to build `"$releaseDir\Locksmith.wxs"` (adjust `-b`/base-path args so it resolves referenced files) instead of the in-tree `Locksmith.wxs`.

- [ ] **Step 7: Run the guard test + existing spec tests**

Run: `.venv/bin/pytest tests/packaging/test_spec_bundles_rcc.py tests/packaging/test_spec_macos.py tests/packaging/test_spec_windows.py --import-mode=importlib -p no:cacheprovider -q`
Expected: PASS (update assertions in the existing spec tests that referenced the loose `assets` datas entry or the old icon path).

- [ ] **Step 8: Commit**

```bash
git add packaging/Locksmith.macos.spec packaging/Locksmith.windows.spec \
        packaging/build-macos.sh packaging/build-windows.ps1 \
        tests/packaging/test_spec_bundles_rcc.py tests/packaging/test_spec_macos.py tests/packaging/test_spec_windows.py
git commit -m "build(brand): freeze bundles release/assets.rcc (drop loose assets tree); build scripts read wxs/dmg from the brand release dir"
```

---

### Task 9: Update the publishing / release / setup docs

**Files:**
- Modify: `docs/developer-guide.rst`, `README.md`, `CLAUDE.md`
- Modify: `/Users/seriouscoderone/code/ugard/docs/demos/2026-07-21-hoa-multi-role-live-demo.md`

- [ ] **Step 1: `docs/developer-guide.rst:26-32`** — replace the manual `pyside6-rcc resources.qrc -o resources_rc.py; mv …` block with:

```
The Qt resource bundle is no longer a tracked file. Build the reference brand's
bundle once (writes the gitignored ``src/locksmith/release/assets.rcc`` and
``brand.json``); the app registers it at startup:

.. code-block:: bash

   python scripts/brand_apply.py --brand locksmith
```

- [ ] **Step 2: `README.md:6`** — replace `python ./scripts/generate_qrc.py; pyside6-rcc resources.qrc -o resources_rc.py; mv resources_rc.py ./src/locksmith;` with `python scripts/brand_apply.py --brand locksmith`.

- [ ] **Step 3: `README.md:48-77`** — rewrite the white-label section for the bundle model: `brand_apply --brand <x>` writes a self-contained bundle to `src/locksmith/release/<x>/` (`assets.rcc` + `brand.json` + `Locksmith.wxs` + `dmg-layout.json` + staged `egf/`/`AppIcon.*`), touching no tracked files; the per-platform build reads that bundle. Note the no-env dev launch uses the flat `src/locksmith/release/` (locksmith); a non-default brand launches with `LOCKSMITH_BRAND_CONFIG=src/locksmith/release/<x>/brand.json`.

- [ ] **Step 4: ugard demo runbook** — in `/Users/seriouscoderone/code/ugard/docs/demos/2026-07-21-hoa-multi-role-live-demo.md`:
  - Delete the GOTCHA #2 `cp`/`rm` block (lines ~19-29) — it no longer applies (brand_apply never overwrites a shared `release/brand.json`).
  - §1 env prep: `.venv/bin/python scripts/brand_apply.py --brand usurance` now writes `src/locksmith/release/usurance/` (bundle incl. `assets.rcc` + `egf/`); the admin runs the **default** bundle (`brand_apply --brand locksmith`, no env).
  - §3 user HOA launch: `LOCKSMITH_BRAND_CONFIG=~/code/locksmith/.../src/locksmith/release/usurance/brand.json` (its `assets.rcc` sibling makes branding atomic).
  - §5 wrap: drop "Restore/regenerate release/brand.json" (nothing to restore — no tracked file is mutated).

- [ ] **Step 5: `CLAUDE.md`** — if it documents `brand_apply` staging over `assets/custom/` or a tracked `resources_rc.py`, update to the bundle model.

- [ ] **Step 6: Commit**

```bash
# locksmith repo
git add docs/developer-guide.rst README.md CLAUDE.md
git commit -m "docs(brand): document the runtime brand-bundle model (brand_apply → release/<brand>/); drop resources_rc setup"
# ugard repo (separate commit, separate repo)
cd /Users/seriouscoderone/code/ugard && git add docs/demos/2026-07-21-hoa-multi-role-live-demo.md && \
  git commit -m "docs(demo): update HOA multi-role runbook for atomic brand bundles (drop brand.json cp/rm gotcha)"
```

---

### Task 10: Live acceptance — clean tree + correct branding for locksmith and usurance

**Files:** none (verification gate). Uses the HOA #4 launch harness (per-app `LOCKSMITH_CONTROL_SOCKET`, fresh `HOME`, `LOCKSMITH_BRAND_CONFIG`, `ui_tester` dev-control socket).

- [ ] **Step 1: Clean-tree proof**

```bash
cd /Users/seriouscoderone/code/locksmith
git checkout -- . ; git status --porcelain > /tmp/before.txt
.venv/bin/python scripts/brand_apply.py --brand locksmith
.venv/bin/python scripts/brand_apply.py --brand usurance
git status --porcelain > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt && echo "TREE CLEAN — no tracked files changed"
```
Expected: no diff (only gitignored `release/**` changed).

- [ ] **Step 2: Focused headless suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/unit/branding tests/packaging/test_usurance_brand_apply.py tests/packaging/test_spec_bundles_rcc.py tests/core/test_usurance_brand.py tests/core/test_branding_egf.py tests/core/test_usurance_egf_bundle.py --import-mode=importlib -p no:cacheprovider -q`
Expected: PASS. (Fix any test still assuming `assets/custom/` staging or a tracked `resources_rc.py`.)

- [ ] **Step 3: Windowed launch — default (locksmith)**

```bash
mkdir -p /tmp/lock-default-demo
HOME=/tmp/lock-default-demo LOCKSMITH_CONTROL_SOCKET=/tmp/lock-default.sock \
  .venv/bin/python -m locksmith.main &
```
Via the `ui_tester` dev-control socket (copy the plugin into the fresh HOME's `~/.locksmith/plugins` first), capture the window: assert title == "Locksmith", toolbar/home favicon == Locksmith symbol, splash was the Locksmith splash. Screenshot. Quit.

- [ ] **Step 4: Windowed launch — usurance white-label**

```bash
mkdir -p /tmp/lock-usurance-demo
HOME=/tmp/lock-usurance-demo LOCKSMITH_CONTROL_SOCKET=/tmp/lock-usurance.sock \
  LOCKSMITH_BRAND_CONFIG=/Users/seriouscoderone/code/locksmith/src/locksmith/release/usurance/brand.json \
  .venv/bin/python -m locksmith.main &
```
Assert title == "Usurance", toolbar/home favicon == Usurance symbol (NOT Locksmith), splash == Usurance splash — logo AND title from the same bundle. Screenshot. Quit.

- [ ] **Step 5: Negative check (the live bug can't recur)**

Confirm there is no `LOCKSMITH_BRAND_CONFIG`-only path that yields a mismatched logo: launching usurance's `brand.json` always registers its sibling `assets.rcc`, so a "Usurance title + Locksmith logo" state is unreachable. (Covered automatically by `test_register_resources.py`; this step is the human-visible confirmation.)

- [ ] **Step 6: Whole-branch review + finish**

Run `superpowers:requesting-code-review` over the full task range, then `superpowers:finishing-a-development-branch`. Flip the ugard backlog/brainstorm status if tracked; note the locksmith commit range.

---

## Self-Review

**1. Spec coverage:**
- Defect 1 (partial brand) → Tasks 4, 5, 10 (single atomic surface; atomicity + negative tests). ✓
- Defect 2 (tracked-file mutation, incl. packaging) → Tasks 3, 7, 8, 10 (all outputs to `<out>`; clean-tree proof). ✓
- Defect 3 (tracked generated blob) → Task 6 (delete + gitignore `resources_rc.py`). ✓
- Defect 4 (silent stale logos) → Task 3 (`_compile_rcc` raises) + fail-loud test. ✓
- Repo reorg (brands/locksmith) → Task 1. ✓
- Runtime `.rcc` registration → Task 4. ✓
- Splash/font/window-icon atomicity → Task 5. ✓
- Build/freeze wiring + drop loose assets → Task 8. ✓
- Docs (incl. mid-turn ask + ugard runbook) → Task 9. ✓
- Live verification (locksmith + usurance) → Task 10. ✓

**2. Placeholder scan:** No TBD/TODO; every code step has runnable code; every build/doc edit names exact files + lines. The Windows `wix build` base-path detail (Task 8 Step 6) is described concretely (build `$releaseDir\Locksmith.wxs`, adjust `-b`) — the implementer confirms wix's base-dir flag against the existing invocation at `build-windows.ps1:145`.

**3. Type consistency:** `build_brand_qrc(repo_root, brand_dir, manifest) -> str` (defined Task 2, used Task 3). `brand_release_dir(brand_id, repo_root=REPO_ROOT) -> Path` (Task 3, used Tasks 3/8). `apply(brand_id, repo_root, *, out=None, check=False)` with `out` kwarg (Task 3, used Tasks 4/5/6/10 fixtures). `register_brand_resources() -> Path`, `unregister_brand_resources() -> None`, `brand_source_dir() -> Path|None`, `brand_assets_rcc() -> Path|None` (Task 4, used Task 5 + conftest Task 6); `_reset_cache_for_tests()` extended (Task 4) to unregister. `_find_rcc()` referenced by the fail-loud test (Task 3 Step 2) and defined in Task 3 Step 4. Resource path `:/assets/custom/SplashScreen.png` consistent across Tasks 2/3/5. Names consistent throughout.

**4. Qt-resource precedence:** first-registered-wins (verified). Encoded in Task 4 (unregister helper + note) and Task 6 (no global auto-register; opt-in per-test registration; unregister between brand switches). No task leaves a bundle registered across a brand switch.
