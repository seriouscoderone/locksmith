# Plugin entry-point tests fail from a worktree — six under tests/plugins, eight more under tests/integration

**Status:** open · **Raised:** 2026-07-28 · **Priority:** low (test-environment defect, not a product defect) — but it makes "is the suite green?" unanswerable from a worktree

## What we saw

Noticed while running the full suite during the AID-salt audit
(`2026-07-28-derived-aids-collide-across-vaults.md`). Six tests fail, all under
`tests/plugins/`, and all fail **identically on the pristine base** — confirmed
by stashing the audit's changes and re-running — so none is a regression:

```
FAILED tests/plugins/carrier/test_carrier_plugin.py::test_carrier_loads_when_brand_lists_it
FAILED tests/plugins/roles/test_role_plugins.py::test_entry_points_registered
FAILED tests/plugins/test_brand_plugin_parity.py::test_brand_loads_exactly_its_declared_surfaces[usurance]
FAILED tests/plugins/test_brand_plugin_parity.py::test_usurance_gets_the_hoa_shell_that_0_3_1_was_missing
FAILED tests/plugins/test_hoa_plugin_exclusion.py::test_bundled_only_plugin_skipped_when_brand_omits_it
FAILED tests/plugins/test_hoa_plugin_exclusion.py::test_bundled_only_plugin_loads_when_brand_lists_it
```

They share one shape — `PluginManager.discover()` finds nothing:

```
    assert "carrier" in mgr.loaded_ids()
E   AssertionError: assert 'carrier' in []
```

The remaining 116 tests in `tests/plugins/` pass; only the ones asserting a
plugin actually *loads* (or that entry points are registered) fail.

The likely cause is the shared-venv layout rather than the tests. Plugin
discovery reads entry points from *installed distribution metadata*, and there is
one venv at the main checkout whose editable install resolves `locksmith` to the
main checkout, not to the worktree. `pyproject.toml`'s `pythonpath` puts the
worktree's `src/` on `sys.path` for imports, but it cannot change what
`importlib.metadata` reports for the installed dist. So a worktree run executes
the worktree's *code* against the main checkout's *entry-point table*.

An editable reinstall from a worktree is exactly what the venv isolation rule
forbids (it repoints every checkout at the worktree's branch), so these cannot be
made to pass by reinstalling — which is what makes this worth fixing rather than
working around.

Cost of leaving it: six standing failures mean any future worktree run has to
re-derive that these six are expected, and a genuine plugin regression hides
among them.

## The actual work

1. Confirm the diagnosis: compare
   `importlib.metadata.entry_points(group="locksmith.plugins")` from a worktree
   against the same call from the main checkout.
2. Decide whether these tests should read installed metadata at all. If plugin
   *discovery logic* is what's under test, inject the entry-point table (a
   fixture yielding fake `EntryPoint`s) instead of reading the ambient
   environment; the tests then assert the logic and pass from anywhere.
3. If a test must exercise real metadata, skip it when the resolved `locksmith`
   dist location differs from the repo root under test, so a worktree run reports
   "skipped, needs an installed checkout" instead of a bare failure that reads
   like a product bug.

## Evidence / references

- `tests/plugins/carrier/test_carrier_plugin.py:132`,
  `tests/plugins/roles/test_role_plugins.py`,
  `tests/plugins/test_brand_plugin_parity.py`,
  `tests/plugins/test_hoa_plugin_exclusion.py`
- `src/locksmith/plugins/manager.py` (`discover`, `loaded_ids`)
- `CLAUDE.md` — "Worktree venv isolation"; sibling entry
  `backlog/2026-07-28-peer-integration-tests-worktree-venv.md` (same class of
  problem, fixed for the peer integration fixture)
- Memory: `project_plugin_origin_strategy` ("MUST `pip install -e .` after
  changing entry point groups"), `reference_test_env_importlib`

## Eight more, under tests/integration (found 2026-07-29)

The count above is incomplete: the same discovery failure takes out eight
integration tests as well, which went unnoticed because `tests/integration/` is
routinely excluded for cost (see `2026-07-28-ci-runs-no-tests-at-all.md` — CI
would not have caught them either). Confirmed identical on the pristine base
`348d2bcf` from a worktree, so none is a regression:

```
FAILED tests/integration/test_carrier_gate_e2e.py::test_admitting_carrier_license_activates_carrier_plugin
FAILED tests/integration/test_carrier_gate_e2e.py::test_escrowed_license_with_unresolvable_edge_does_not_activate
FAILED tests/integration/test_carrier_gate_e2e.py::test_wrong_issuer_license_does_not_activate
FAILED tests/integration/test_carrier_gate_e2e.py::test_revoking_application_edge_target_leaves_gate_satisfied
FAILED tests/integration/test_exchange_roundtrip_e2e.py::test_return_grant_auto_admits_carrier_to_licensed_surface
FAILED tests/integration/test_exchange_roundtrip_e2e.py::test_revoked_license_deactivates_surface_and_shows_revoked
FAILED tests/integration/test_multi_role_e2e.py::test_two_roles_coexist_and_revoke_removes_exactly_one
FAILED tests/integration/test_onboarding_e2e.py::test_onboarding_e2e_persona_pick_to_licensed_surface
```

Same shape — discovery returns nothing:

```
    assert ep is not None, "carrier entry point must be discoverable"
E   AssertionError: carrier entry point must be discoverable
```

So the worktree baseline is **14** known failures, not six, and the fix for the
six should clear all fourteen. Worth re-checking from the main checkout to
confirm they pass there (the six are known to).

**Why this matters beyond bookkeeping.** An undercounted baseline hides real
regressions. On 2026-07-29 a genuine regression in
`test_exchange_roundtrip_e2e.py::test_first_contact_registers_unknown_carrier_and_delivers_grant`
was caught only by explicitly diffing failure lists against the base — a
"6 known failures" baseline plus a habitually skipped directory would have let
it through. Until the fourteen are fixed, the only sound check from a worktree
is a base-vs-branch diff of the FAILED list, not a count.
