from pathlib import Path

def generate_qrc(asset_dir, output_file):
    asset_path = Path(asset_dir)

    with open(output_file, 'w') as f:
        f.write('<RCC>\n')
        f.write('    <qresource prefix="/">\n')

        for file_path in asset_path.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(asset_path.parent)
                f.write(f'        <file>{relative_path.as_posix()}</file>\n')

        f.write('    </qresource>\n')
        f.write('</RCC>\n')

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


if __name__ == "__main__":
    assert Path("pyproject.toml").exists(), "Must be run from project root"
    generate_qrc('./assets', './resources.qrc')