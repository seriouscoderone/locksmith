"""Full brand_apply.apply() pipeline exercised for the real usurance brand.

Runs the actual Python entrypoint (not a shelled build) against a tmp_path
mirror of the repo tree, seeded with the REAL brands/usurance/brand.toml +
assets, so this proves the whole bundle-build pipeline — not just
brandlib.runtime_brand_json() in isolation (already covered by
tests/unit/branding/test_runtime_brand_json.py) — produces a correct
runtime brand.json (id + bootstrap table), a compiled assets.rcc, staged app
icons, and brand-parameterized wix/dmg packaging config, all written into
<out> (never into the tracked working tree: assets/custom/ stays untouched).
"""
import importlib
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packaging"))
brand_apply = importlib.import_module("brand_apply")


def _fake_repo(tmp_path: Path) -> Path:
    """Minimal repo skeleton (assets/, packaging/, src/.../release/) with the
    REAL brands/usurance AND brands/locksmith (reference, for slot fallback)
    directories copied in verbatim."""
    (tmp_path / "assets" / "custom").mkdir(parents=True)
    (tmp_path / "assets" / "custom" / "settings.png").write_bytes(b"NEUTRAL")
    (tmp_path / "packaging" / "wix").mkdir(parents=True)
    (tmp_path / "packaging" / "wix" / "Locksmith.wxs.in").write_text(
        (REPO_ROOT / "packaging" / "wix" / "Locksmith.wxs.in")
        .read_text(encoding="utf-8"),
        encoding="utf-8")
    (tmp_path / "src" / "locksmith" / "release").mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "brands" / "usurance",
                     tmp_path / "brands" / "usurance")
    shutil.copytree(REPO_ROOT / "brands" / "locksmith",
                     tmp_path / "brands" / "locksmith")
    return tmp_path


def _out(repo: Path) -> Path:
    return repo / "src" / "locksmith" / "release" / "usurance"


def test_brand_apply_usurance_writes_runtime_brand_json(tmp_path):
    repo = _fake_repo(tmp_path)
    out = _out(repo)

    report = brand_apply.apply("usurance", repo, out=out, check=False)
    assert report["brand"] == "usurance"
    assert report["out"] == str(out)

    bj = json.loads((out / "brand.json").read_text())
    assert bj["id"] == "usurance"
    assert bj["bootstrap"]["peel_core_pages"] is True
    assert bj["bootstrap"]["default_aid_alias"] == "default"
    assert bj["bootstrap"]["default_witnesses"] == []  # witnessless POC


def test_brand_apply_usurance_writes_bundle_to_out_and_leaves_tree_clean(tmp_path):
    repo = _fake_repo(tmp_path)
    out = _out(repo)

    brand_apply.apply("usurance", repo, out=out, check=False)

    # compiled rcc exists and is non-empty
    rcc = out / "assets.rcc"
    assert rcc.is_file() and rcc.stat().st_size > 0
    # app icons staged as files in <out>, byte-identical to the brand source
    staged = out / "AppIcon.icns"
    source = REPO_ROOT / "brands" / "usurance" / "AppIcon.icns"
    assert staged.read_bytes() == source.read_bytes()
    # NOTHING tracked/neutral was mutated
    assert (repo / "assets" / "custom" / "settings.png").read_bytes() == b"NEUTRAL"
    assert not (repo / "assets" / "custom" / "AppIcon.icns").exists()
    assert "@@NAME@@" in (repo / "packaging" / "wix" / "Locksmith.wxs.in").read_text()
    assert not (repo / "packaging" / "wix" / "Locksmith.wxs").exists()


def test_brand_apply_usurance_renders_wix_and_dmg_identity(tmp_path):
    repo = _fake_repo(tmp_path)
    out = _out(repo)

    brand_apply.apply("usurance", repo, out=out, check=False)

    wxs = (out / "Locksmith.wxs").read_text()
    assert 'Name="Usurance"' in wxs
    assert "@@" not in wxs  # every token substituted

    layout = json.loads((out / "dmg-layout.json").read_text())
    assert layout["volume_name"] == "Usurance"


def test_brand_apply_usurance_renders_its_own_wix_chrome(tmp_path):
    """The MSI's welcome dialog + banner must come out of THIS brand's bundle.

    v0.3.6 shipped a Usurance MSI wearing Locksmith's triquetra because the
    chrome was a single committed pair under packaging/wix/. brand_apply now
    renders it per brand, so the bytes must differ from locksmith's.
    """
    repo = _fake_repo(tmp_path)
    out = _out(repo)

    report = brand_apply.apply("usurance", repo, out=out, check=False)
    assert set(report["wix_images"]) == {"dialog.png", "banner.png"}

    lock_out = repo / "src" / "locksmith" / "release"
    brand_apply.apply("locksmith", repo, out=lock_out, check=False)
    for name in ("dialog.png", "banner.png"):
        assert (out / name).is_file(), f"usurance bundle missing {name}"
        assert (out / name).read_bytes() != (lock_out / name).read_bytes(), (
            f"usurance {name} is byte-identical to locksmith's")


def test_brand_apply_usurance_stages_egf_bundle(tmp_path):
    repo = _fake_repo(tmp_path)
    out = _out(repo)

    report = brand_apply.apply("usurance", repo, out=out, check=False)
    assert report["egf_staged"]  # usurance ships a bundled egf/ dir
    assert (out / "egf").is_dir()
    for name in report["egf_staged"]:
        assert (out / "egf" / name).is_file()


def test_check_mode_does_not_write_usurance_outputs(tmp_path):
    repo = _fake_repo(tmp_path)
    out = _out(repo)

    brand_apply.apply("usurance", repo, out=out, check=True)
    assert not (out / "brand.json").exists()
    assert not (out / "assets.rcc").exists()
    assert not (out / "Locksmith.wxs").exists()
