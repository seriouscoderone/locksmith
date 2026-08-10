# Upstream v2 ACDC issuance now works — the v1 hold's original reason is gone

**Status:** backlog · **Raised:** 2026-08-10 · **Priority:** medium (no defect today; a stale rationale that will mislead the next reader)

## What changed

Bumping the `keri` pin for v0.4.0 (`1c127b59` → `dc88ea0d`) flipped the behaviour
of unpinned credential issuance. Probed directly against the new pin:

```
UNPINNED version field: ACDCCAACAAJSONAAGG.
has ri: False | has rd: True
```

`credentialing.Credentialer.create(...)` with no `version=` now produces a real
**v2 ACDC carrying `rd`**. It used to raise
`SerializeError: Unallowed extra field 'ri'`, because `proving.credential`
hardcoded the v1 `ri` field and the v2 `SerderACDC` rejected it.

This surfaced as a red test: `tests/test_credential_issuance_v1.py::
test_credential_create_default_rejects_ri_on_v2` asserted the `SerializeError`
that no longer happens. That test characterized an upstream *limitation*, not
Locksmith behaviour, so it was rewritten to characterize the new default
(`test_unpinned_create_now_yields_a_v2_acdc`).

## Why the pin still stands

Locksmith's shipped path is unaffected: `core/credentialing.py` always passes
`version=Vrsn_1_0` explicitly, so it still issues v1 `ACDC10JSON` credentials
with `ri`. The pin remains correct for a **different** reason than the one its
comment gave — the registry `vcp`/`iss` are still v1 (the VDR stack is v1-pinned
upstream), and issuing a v2 ACDC into a v1 registry is incoherent.

The comment at `src/locksmith/core/credentialing.py` has been corrected to say
so. This item tracks the actual follow-through.

## The actual work

* Determine whether the fork's VDR stack (`keri.vdr`) can now issue a v2
  registry (`vcp`/`iss`). If yes, the v1 hold can be lifted **as a unit** —
  registry and ACDC together, never one without the other.
* `grep -rn TRANSITIONAL src/` finds the other v1-hold sites; `keri_serviceaid`
  carries the matching hold on the Service-AID side and must move in the same
  cut (memory: `project_keri_v2_migration`).
* Any lift is a wire-format change for every already-issued credential. It needs
  a migration story for existing vaults before it ships, not just a green suite.

## Evidence / references

* `src/locksmith/core/credentialing.py` — the `version=Vrsn_1_0` call site + corrected comment
* `tests/test_credential_issuance_v1.py` — the rewritten characterization
* keri pin: `seriouscoderone/keripy@dc88ea0d1b7c310341242f679cc1c498b07cac4e`
* Prior context: `docs/superpowers/specs/` KERI v2 base reconciliation
