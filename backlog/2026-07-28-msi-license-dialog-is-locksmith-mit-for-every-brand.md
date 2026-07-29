# The MSI license dialog reads "Locksmith / Copyright (c) KERI.host" for every brand

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** medium (visible brand + legal text leak in a shipped installer; needs an owner decision, not just plumbing)

## What we saw

`packaging/wix/license.rtf` is a single committed file referenced by the WiX
authoring (`packaging/wix/Locksmith.wxs.in:130`,
`<WixVariable Id="WixUILicenseRtf" Value="license.rtf" />`) and it is
Locksmith-specific in three places:

```rtf
\b Locksmith\b0\par
Copyright (c) KERI.host\par
https://github.com/seriouscoderone/locksmith/blob/main/LICENSE\par
```

So the Usurance MSI's "End-User License Agreement" page presents the *Locksmith*
product name, KERI.host's copyright line, and a link to the Locksmith GitHub
repo — under an MIT grant that may or may not be what Usurance intends to offer.
Found while fixing the sibling leak in the same dialog set (the welcome-screen
artwork, `backlog/…` / branch `fix/wix-brand-images`).

The **plumbing** for a per-brand override already landed with that fix:
`scripts/brand_apply.py` copies `brands/<brand>/license.rtf` into the brand's
release dir when it exists, and `packaging/build-windows.ps1` now lists
`-bindpath $releaseDir` before `-bindpath $wixDir`, so a brand-supplied file wins
and the shared file is only the fallback. Nothing consumes that hook yet.

## The actual work

* Decide the licensing story per brand. Usurance is a commercial white-label of a
  repo whose root `LICENSE` is MIT — is the installer offering MIT, an EULA, or a
  terms-of-service pointer? That is an owner call, deliberately **not** made by
  find-and-replacing "Locksmith" → "Usurance" in an MIT grant.
* Drop the resulting RTF at `brands/usurance/license.rtf` (the hook picks it up
  with no code change) — or, if the text really is the same grant with only the
  product/holder/URL varying, templatize it the way `Locksmith.wxs.in` is
  (`@@NAME@@` / `@@MANUFACTURER@@` / repo URL) and render it in
  `brandlib.render_wxs`'s neighbourhood.
* Either way, add a check to `scripts/check-brand-complete.py` so a tagged
  non-locksmith release cannot ship the Locksmith license page: a brand either
  supplies its own `license.rtf` or explicitly opts into the shared one.
* Same question for the macOS leg: `packaging/build-macos.sh` does not show a
  license at all on the DMG, so there is nothing to fix there today — worth
  confirming that is intentional.

## Evidence / references

* `packaging/wix/license.rtf` — "Locksmith", "Copyright (c) KERI.host",
  `github.com/seriouscoderone/locksmith`
* `packaging/wix/Locksmith.wxs.in:130` — `WixUILicenseRtf`
* Hook already in place: `scripts/brand_apply.py` (`brand_license` staging),
  `packaging/build-windows.ps1` bindpath order
* Sibling leak (fixed): `backlog/2026-07-28-dmg-background-says-locksmith-for-every-brand.md`
  covers the macOS twin; the MSI welcome artwork was fixed on `fix/wix-brand-images`
