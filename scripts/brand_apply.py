#!/usr/bin/env python3
"""Build a brand's self-contained release bundle before a packaged build.

Reads brands/<brand>/brand.toml and writes everything into a single output
directory (default: brandlib.brand_release_dir(brand_id)) — never into
tracked paths like assets/custom/ or packaging/:
  - assets.rcc: a compiled Qt resource bundle containing the neutral assets/
    pool verbatim plus this brand's logo-slot files aliased onto the
    canonical :/assets/custom/* paths the UI expects (see generate_qrc.py);
  - brand.json: the runtime subset consumed by locksmith.core.branding;
  - Locksmith.wxs / dmg-layout.json: brand-parameterized packaging config;
  - AppIcon.icns/.ico: staged as files (not compiled into the rcc);
  - publisher_anchor.json / deploy_config.json: the brand's trust material,
    if present;
  - egf/: the brand's bundled EGF docs, if present.

Selection: --brand or $LOCKSMITH_BRAND (default 'locksmith'). --check writes
nothing and just reports what would happen. Fails loud (SystemExit) if
pyside6-rcc is unavailable or produces no output — never ships stale logos.
"""
import argparse, json, subprocess, shutil, sys, tempfile
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
