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
import subprocess
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent.parent / "packaging"))
import brandlib  # noqa: E402

_ASSET_KEYS = ("app_icon_icns", "app_icon_ico", "splash", "symbol_logo",
               "symbol_logo_on_dark", "name_logo", "full_logo",
               "symbol_logo_black", "name_logo_black", "full_logo_black")


def _recompile_resources(repo_root: Path) -> bool:
    """Recompile src/locksmith/resources_rc.py from resources.qrc.

    The Qt resource bundle (``:/assets/custom/*``) is a COMPILED blob; the UI
    loads brand logos through it (toolbar favicon, home, drawer). Staging files
    into assets/custom/ is not enough — without recompiling, those ``:/`` logos
    stay the compiled-in default brand's. Returns False (with a warning) if
    ``pyside6-rcc`` is unavailable. Asset filenames are fixed (_ASSET_KEYS), so
    the existing resources.qrc file list already covers them — no regen needed.
    """
    out = repo_root / "src" / "locksmith" / "resources_rc.py"
    # Nothing to compile when there is no qrc (minimal trees / test fixtures) —
    # skip cleanly rather than letting rcc fail the whole apply().
    qrc = repo_root / "resources.qrc"
    if not qrc.is_file():
        print(f"WARNING: {qrc} not found; :/ brand assets NOT recompiled",
              file=sys.stderr)
        return False
    # Prefer the rcc next to the running interpreter — brand_apply is commonly
    # invoked as `.venv/bin/python scripts/brand_apply.py` without the venv on
    # PATH, so a bare which() would miss it and silently skip the recompile.
    cand = Path(sys.executable).parent / "pyside6-rcc"
    rcc = str(cand) if cand.exists() else shutil.which("pyside6-rcc")
    if not rcc:
        print("WARNING: pyside6-rcc not found; :/ brand assets NOT recompiled "
              "(branded logos may not appear via :/ paths)", file=sys.stderr)
        return False
    subprocess.run([rcc, "resources.qrc", "-o", str(out)],
                   cwd=repo_root, check=True)
    return True


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
        # Recompile the Qt resource bundle so :/assets/custom/* carries THIS
        # brand's logos. Only when we actually staged brand assets (the default
        # locksmith brand ships none → committed resources_rc.py already matches).
        if staged:
            _recompile_resources(repo_root)

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
