# A brand missing an asset slot silently ships Locksmith's art

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** medium (leak-by-design fallback; today masked because both real brands are complete)

## What we saw

`scripts/generate_qrc._slot_source()` resolves each of the eight `:/`-accessed
logo slots and, when the brand does not supply one, ends with:

```python
    # reference default
    return (repo_root / "brands" / "locksmith" / canonical).relative_to(repo_root).as_posix()
```

So any brand that omits (or misnames) `full_logo`, `name_logo`, `splash`, … gets
**Locksmith's** file compiled into its `assets.rcc` under the canonical alias,
with no warning. The running app then renders Locksmith art inside the
white-label UI, and it looks intentional because the alias resolved fine.

This is the same failure mode as the v0.3.6 Usurance MSI welcome dialog (fixed on
`fix/wix-brand-images`): a brand-selected source silently resolving to the
reference brand. That fix deliberately went the other way — the new WiX chrome
renderer falls back only *within* the brand and raises otherwise:

```python
# packaging/wix/gen_ui_images.resolve_symbol
raise SystemExit(f"gen_ui_images: no symbol art for slot {slot!r} in {brand_dir} — "
                 "refusing to fall back to another brand's mark")
```

Those two policies now disagree inside one build. What partly covers the qrc path
today is `scripts/check-brand-complete.py`, but only for brands that are neither
`locksmith` nor `example`, and only for keys the brand actually *declares*: it
walks `m.get("assets", {})` and checks each declared filename exists. A brand that
simply omits `full_logo` from `[assets]` passes the check and silently inherits
Locksmith's.

## The actual work

* Decide the policy once and apply it in both resolvers: either "a brand must
  declare every slot" (fail loud) or "documented reference fallback, and say so
  loudly in the build log".
* Preferred: make `check-brand-complete.py` require the full slot set
  (`generate_qrc._QRC_SLOTS` keys) for every non-`example` brand, then keep the
  qrc fallback only as a belt-and-braces path that prints a warning naming the
  slot and the brand.
* Extend the variant fallback table intent: `symbol_logo_white`/`_black` falling
  back to the brand's own `symbol_logo` is fine and should stay — it is a
  within-brand fallback, like the WiX renderer's.
* Cover it: a brand fixture missing one slot should either fail
  `check-brand-complete` or produce a build-log warning that a test can assert.

## Evidence / references

* `scripts/generate_qrc.py:38-50` — `_slot_source` reference-brand fallback
* `scripts/generate_qrc.py:21-35` — `_QRC_SLOTS` / `_QRC_VARIANT_FALLBACK`
* `scripts/check-brand-complete.py` — validates only *declared* `[assets]` values
* Contrasting (fixed) policy: `packaging/wix/gen_ui_images.py::resolve_symbol`
