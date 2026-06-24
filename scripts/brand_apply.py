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
