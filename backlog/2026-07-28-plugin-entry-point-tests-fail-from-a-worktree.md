# Six plugin entry-point tests fail from a worktree

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
