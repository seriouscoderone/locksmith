# IPEX `admit` cannot admit a real grant: stale `reg` embed **and** v2-only re-serialization of v1 embeds

**Filed:** 2026-07-16 (investigation complete; fixing now via TDD)
**Domain:** `src/locksmith/core/ipexing.py` (`Admitter.admit` and `AdmitDoer.admitDo`) × keripy `2.0.0-dev6` IPEX grant embed shape and v1/v2 wire format
**Severity:** neither admit path can admit a real credential during the current KERI v2 v1-hold. `Admitter.admit` raises `KeyError: 'reg'`; both paths then raise `ValueError: Unsupported version = 1.0`.

## Two defects (found together)

**Defect 1 — stale `reg` embed (`Admitter.admit` only).**
`Admitter.admit` iterates `("anc", "reg", "iss", "acdc")` and hard-indexes `ked = embeds[label]`. keripy `ipexGrantExn` builds the grant's `e` block with only `acdc` plus optional `iss`/`anc` — it **never** emits a `reg` embed (verified in the installed `keri` `2.0.0-dev6`, not just the fork). So `embeds["reg"]` raises `KeyError: 'reg'`. `AdmitDoer.admitDo` already skips `reg` and uses `.get` guards.

**Defect 2 — v2-only re-serialization of v1 embeds (BOTH paths).**
Both loops re-serialize each embed with `coring.Sadder(ked=ked)` (to prepend `sadder.raw` to the pathed attachments). In `2.0.0-dev6`, `coring.Sadder` is hard-wired to the library's current version (v2, via `sizeify` → `Version`) and raises `ValueError: Unsupported version = 1.0` on any v1 ked. During the deliberate v1-hold every real grant embed is v1 (`KERI10JSON`/`ACDC10JSON`), so both `Admitter.admit` and `AdmitDoer.admitDo` fail here. Verified by running `AdmitDoer`'s exact loop body on a real v1 grant — it fails on all three embeds. In the broken `Admitter.admit` the `anc` embed hits `Sadder` (defect 2) *before* the loop reaches `reg` (defect 1), so defect 1 alone was never observed at runtime — it was a code-reading finding in the HOA e2e work.

## Root cause
Both defects are "code written against a newer library/format assumption": defect 1 assumes the old 4-embed grant shape; defect 2 assumes the wire version equals the library's current default. `coring.Sadder` is the wrong tool because it is version-fixed, not version-agnostic.

## Fix (version-agnostic, end-state design — not a v1-hold workaround)
Add a shared `_embed_serder(label, ked)` helper that re-serializes an embed with a **version-agnostic** Serder (`serdering.SerderACDC` for the `acdc` embed, `serdering.SerderKERI` for `anc`/`iss`); each reads the protocol version from the ked's own version string, so it handles v1 today and v2 later with no further change. Apply it in **both** `Admitter.admit` and `AdmitDoer.admitDo`. In `Admitter.admit` also drop `reg` from the label tuple and adopt the `embeds.get`/`pathed.get(label, b'')` guards `AdmitDoer` already uses. `acdc = embeds["acdc"]` stays (always emitted; used for the saved-credential check). This matches the project's stated v1-compat strategy: version-agnostic read path.

## Discovery context
Surfaced while building the HOA carrier-license gate end-to-end test (locksmith branch `hoa-base-scaffold`, `tests/integration/test_carrier_gate_e2e.py`), which routed around admit rather than exercising a literal `Admitter.admit`.

## Tests
- New regression: `tests/unit/test_ipexing_admit.py` — fully issues a v1 credential, `Granter.grant`s it (real v1 grant, no `reg` embed), then `Admitter.admit`s it and asserts the admit completes (returns an admit exn) with no `KeyError` and no version error.
- `AdmitDoer` gets the same helper; a focused test exercises the shared version-agnostic re-serialization on a real v1 grant.
