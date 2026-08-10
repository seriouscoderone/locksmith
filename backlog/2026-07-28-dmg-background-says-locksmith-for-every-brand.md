# The macOS DMG background says "Locksmith" in every brand's installer

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** high (visible brand leak in a shipped artifact; same class as the v0.3.6 MSI dialog leak, macOS side)

## What we saw

Fixing the Windows WiX chrome leak (Usurance MSI wearing Locksmith's triquetra,
`packaging/wix/gen_ui_images.py` writing one shared committed pair) turned up the
identical bug on the macOS leg, still unfixed.

`packaging/dmg/background.png` is a single committed image whose baked-in text
reads **"Locksmith — drag to Applications"**. `packaging/build-macos.sh:126`
hands it to `create-dmg` unconditionally:

```bash
    --background "packaging/dmg/background.png" \
```

and `brandlib.render_dmg_layout()` (`packaging/brandlib.py:107-121`) even emits
`"background": "background.png"` into every brand's `dmg-layout.json`. So the
Usurance DMG mounts a window that tells the user to drag "Locksmith" to
Applications, next to an icon labelled `Usurance.app`.

Unlike the WiX pair there is **no generator at all** for this file — nothing in
`scripts/` or `packaging/` contains the string "drag to Applications". It is a
hand-made asset, so it cannot even be re-rendered for a brand today.

## The actual work

Mirror what `packaging/wix/gen_ui_images.py` now does for the MSI chrome:

* Render the DMG background per brand into `brandlib.brand_release_dir(brand)` —
  brand display name in the caption, brand palette, brand mark. Qt's `QPainter`
  can draw the text + arrow; run it as a subprocess from
  `scripts/brand_apply.py` alongside the WiX chrome (Qt's application object is
  a process-wide singleton — see `scripts/brand_apply._render_wix_images`).
* Point `packaging/build-macos.sh` at `$LOCKSMITH_RELEASE/background.png`
  (it already exports `LOCKSMITH_RELEASE` for `dmg-layout.json`).
* Stop committing `packaging/dmg/background.png`; gitignore it like
  `packaging/wix/banner.png` / `dialog.png` now are, so a shared copy cannot
  come back and silently win.
* Note the caption arrow must stay aligned with the icon coordinates in
  `dmg-layout.json` (`icons[].pos`) — generate both from the same constants.
* Unlike the MSI, this one is fully verifiable locally: render both brands and
  look at the PNGs; a real DMG build only confirms the mount geometry.

## Evidence / references

* `packaging/dmg/background.png` — committed, caption "Locksmith — drag to Applications"
* `packaging/build-macos.sh:126` — unconditional `--background`
* `packaging/brandlib.py:107-121` — `render_dmg_layout` emits the shared name
* Fixed sibling (the pattern to copy): `packaging/wix/gen_ui_images.py`,
  `scripts/brand_apply.py` (`_render_wix_images`), branch `fix/wix-brand-images`
* Regression cover for the Windows side: `tests/packaging/test_wix_brand_images.py`
