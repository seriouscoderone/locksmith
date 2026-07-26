# Plugin Origin Strategy — separating *where a plugin comes from* from *whether it activates*

**Date:** 2026-07-25
**Status:** design, for review
**Motivating incidents:** three shipped user-visible bugs (KF plugin invisible in frozen builds,
fixed 0.2.21; the whole HOA surface missing so Usurance opened to the vault picker, fixed 0.3.1;
and the blank HOA home screen, 0.3.4 — the last one a different root cause but the same
"the loader's assumptions are implicit" family).

## TL;DR

`PluginManager.discover()` hardcodes two discovery paths and inlines four unrelated activation
policies into them. This spec extracts **origins** (how a plugin is discovered and imported) behind
a strategy protocol, lifts **activation policy** into an explicit ordered chain, and makes
"this origin's code must be collected at build time" a **declared property** that the packaging test
derives from the registry — so the recurring frozen-build class of bug becomes structurally
impossible rather than something a maintainer must remember.

It also **corrects two assumptions** in the framing that prompted it (see
§"Corrections to the initiating analysis"): `BUNDLED_ONLY_PLUGIN_IDS` is *not* dead residue, and
"source" is the wrong name for the new abstraction.

## Where we are today

`src/locksmith/plugins/manager.py`:

```python
def discover(self) -> None:
    excluded = set(storage.read_enable_list(self._keri_base).get("excluded", []))
    self._discover_from_index(excluded)          # ~line 130
    self._discover_from_entry_points(excluded)   # ~line 164
    self._call_initialize_on_all()
```

Two hardcoded private methods, and policy braided through both:

| Policy | Where it lives now | Applies to |
|---|---|---|
| User exclude list | `excluded` set threaded as a parameter; checked at `:141` (index) and `:190` (entry-point) | both origins |
| HOA peel | `HOA_PEELED_PLUGIN_IDS` frozenset + `brand().peel_core_pages` at `:172` | entry-point only |
| Brand composition | `BUNDLED_ONLY_PLUGIN_IDS` frozenset + `brand().bundled_plugins` at `:177` | entry-point only |
| Compatibility | `_compat_ok()` at `:145` (currently always True) | index only |
| Credential gate | `credential_gate.gate_satisfied` — later, at vault-UI time | role plugins |

Four kinds of plugin exist, but only **two** discovery mechanisms; the third and fourth kinds are
policy variations layered on the entry-point mechanism:

| Kind | Discovered by | Activation policy | Example |
|---|---|---|---|
| Bundled in-tree, default-on | entry-points | peel exclusion only | `kerifoundation` |
| Bundled in-tree, brand-composed | entry-points | brand must list it | `hoa_shell`, `actuary`, `product_designer`, `carrier` |
| Installed clone | `~/.locksmith/plugins/index.json` | exclude + compat + files-present | `designer`, `ui_tester` |
| Gated remote (unbuilt) | future | install-time gate | `plugin.usurance.com` |

## Two defects this design fixes (beyond tidiness)

### D1 — Policy is applied *after* import for entry-point plugins

`_discover_from_entry_points` calls `ep.load()` and instantiates the class at `:183-184`, then
checks the exclude list at `:190` and the index-wins precedence at `:186`. So a plugin the user
**excluded**, or one **overridden by an installed clone**, still has its module imported and its
constructor run. Any import-time or `__init__` side effect happens regardless of exclusion. The peel
and brand-composition checks *are* pre-import (they match on `ep.name`), so this is inconsistent
as well as wrong.

**Requirement:** every policy that can be decided from a plugin's *identity* must be decided
**before** its module is imported.

### D2 — "Must be collected into the frozen build" is tribal knowledge

Entry-point plugins are reached only via `ep.load()`, which PyInstaller's static analysis cannot
see. Nothing in the code says so; the knowledge lived in a maintainer's head, and twice it did not.
`tests/unit/test_specs_bundle_kf_plugin.py` now guards it by reading `pyproject` and string-matching
the specs — a good stopgap, but it hardcodes the group name and the collected package, so it
re-encodes the same knowledge in a second place rather than deriving it.

**Requirement:** the packaging requirement is a property of the origin, and the test derives what
the specs must contain from the origin registry.

## Design

### Vocabulary: `PluginOrigin` (not `PluginSource`)

**"Source" is already taken.** The Stage-1 loader design
(`2026-05-16-locksmith-plugin-loader-design.md` §A.3) defines a *source descriptor* —
`{type: "github", user_repo: ...}` / `{type: "local", path: ...}` — describing **where a plugin's
code was fetched from**, and `PluginState.source` stores exactly that. Reusing "source" for
"how the loader finds and imports it" would overload a live term in the same module.

- **source** (existing) — provenance of the code: which GitHub repo / local path it was installed from.
- **origin** (new) — the discovery-and-import channel: in-tree entry point vs installed clone vs
  future remote.

One installed clone has *both*: origin = `index-clone`, source = `{github, user/repo}`.

### The protocol

```python
# src/locksmith/plugins/origins.py

@dataclass(frozen=True)
class Candidate:
    """A plugin discovered but NOT yet imported. Policy is decided on this."""
    plugin_id: str
    origin_id: str                       # "entry-point" | "entry-point-composed" | "index-clone"
    load: Callable[[], PluginCore]       # deferred import+instantiate
    source: dict[str, Any] = field(default_factory=dict)      # installer descriptor (may be {})
    manifest_snapshot: dict[str, Any] = field(default_factory=dict)
    in_tree: bool = False
    record: dict[str, Any] | None = None  # index record, for compat/files checks


class PluginOrigin(Protocol):
    origin_id: str
    #: True when this origin's plugin code is reached only by dynamic import and
    #: therefore MUST be collected into frozen builds by the PyInstaller specs.
    requires_build_collection: bool
    #: Package roots the specs must collect_submodules() when the above is True.
    collected_packages: tuple[str, ...]

    def candidates(self) -> Iterable[Candidate]: ...
```

Key point: `candidates()` yields **unimported** candidates carrying a deferred `load`. That is what
makes D1 fixable — the manager runs policy on identity, then calls `load()` only for survivors.

Implementations:

| Origin | `origin_id` | `requires_build_collection` | Notes |
|---|---|---|---|
| `EntryPointOrigin` | `entry-point` | `True` — `collected_packages=("locksmith.plugins",)` | group `locksmith.plugins`; default-on |
| `ComposedEntryPointOrigin` | `entry-point-composed` | `True` — same package root | group `locksmith.plugins.composed`; opt-in |
| `IndexCloneOrigin` | `index-clone` | `False` | code lives outside the bundle, in `~/.locksmith/plugins/` |

`IndexCloneOrigin.requires_build_collection = False` is not a technicality — it is the statement
that clone plugins are *deliberately* outside the frozen bundle, which is why they kept working
when the bundled ones broke.

### Activation policy as an ordered chain

```python
# src/locksmith/plugins/activation_policy.py

class ActivationRule(Protocol):
    def veto(self, c: Candidate) -> str | None:
        """Return a skip reason, or None to allow."""
```

| Rule | Reason string | Replaces |
|---|---|---|
| `ExcludedByUser` | `excluded` | the threaded `excluded` set |
| `HoaPeeled` | `hoa_peel` | `HOA_PEELED_PLUGIN_IDS` check |
| `NotBrandComposed` | `not_bundled` | `BUNDLED_ONLY_PLUGIN_IDS` check |
| `Incompatible` | `incompatible` | `_compat_ok` |
| `FilesMissing` | `files_missing` | clone-exists check |

Existing log lines (`plugin.skipped reason=<reason> plugin_id=<id>`) and `PluginState.status` values
are preserved verbatim — they are the observability contract the HOA tests assert on.

Credential gating deliberately stays where it is: it is not a *load* decision but a *reveal*
decision, already cleanly handled by `RoleActivationStrategy` at vault-UI time. This spec extends
that separation to loading; it does not merge the two.

### Retiring `BUNDLED_ONLY_PLUGIN_IDS` — correctly

The opt-in/default-on distinction is real and must be decidable **pre-import** (D1). It cannot be a
class attribute, because reading one requires importing the module we are trying not to import.

So move the distinction into the **entry-point group**, which is metadata and free to read:

```toml
[project.entry-points."locksmith.plugins"]           # default-on
kerifoundation = "locksmith.plugins.kerifoundation.plugin:KeriFoundationPlugin"

[project.entry-points."locksmith.plugins.composed"]  # opt-in: brand must list it
carrier          = "locksmith.plugins.carrier.plugin:CarrierPlugin"
hoa_shell        = "locksmith.plugins.hoa_shell.plugin:HoaShellPlugin"
actuary          = "locksmith.plugins.actuary.plugin:ActuaryPlugin"
product_designer = "locksmith.plugins.product_designer.plugin:ProductDesignerPlugin"
```

The group *is* the policy, available before import, and **adding a plugin no longer requires editing
the framework** — the actual defect in the frozenset. Both groups live under `locksmith.plugins`, so
the specs' existing `collect_submodules("locksmith.plugins")` and `copy_metadata("Locksmith")` cover
both unchanged.

`HOA_PEELED_PLUGIN_IDS` **stays** a framework constant. It is a genuine framework statement — "the
built-in wallet-provider surface is what an HOA peel removes" — not per-plugin config, and the
backlog note records that expressing it in `pyproject` broke the default build.

### Precedence

Registry order defines precedence, preserving today's "index wins over in-tree":

```python
ORIGINS = (IndexCloneOrigin(), EntryPointOrigin(), ComposedEntryPointOrigin())
```

First origin to claim a `plugin_id` wins; later duplicates are skipped (now *before* import, per D1).

## Migration / compatibility

1. `pyproject` regroups the four composed plugins. **Requires a reinstall** (`pip install -e .`) for
   the new group to appear in dev metadata — note in CLAUDE.md.
2. `BUNDLED_ONLY_PLUGIN_IDS` deleted; the stale cross-reference comments in
   `core/branding.py:65` and `plugins/hoa_shell/plugin.py:76` updated.
3. `tests/plugins/roles/test_role_plugins.py:50` reads `entry_points(group="locksmith.plugins")` and
   must read the composed group for the role plugins.
4. `tests/unit/test_specs_bundle_kf_plugin.py` rewritten to derive from `ORIGINS`, and renamed to
   reflect that it is no longer KF-specific.
5. Behavior is otherwise unchanged: same plugins load, same skip reasons, same statuses, both brands.

## Verification

- Every existing plugin (`kerifoundation`, `carrier`, `hoa_shell`, `actuary`, `product_designer`,
  cloned `designer`/`ui_tester`) loads, gates, and activates exactly as before, for both brands —
  the existing `tests/plugins/` suite is the oracle and must pass unmodified except for the two
  mechanical updates above.
- **D1 regression test:** an excluded entry-point plugin's module is never imported (assert via a
  sentinel that its `load` callable was not invoked). This test fails against the pre-change code.
- **D2 structural test:** for every origin with `requires_build_collection`, each of its
  `collected_packages` appears in a `collect_submodules(...)` call in both specs, and
  `copy_metadata("Locksmith")` is present — all derived from `ORIGINS`, nothing hardcoded.
- Adding a hypothetical new origin with `requires_build_collection=True` and an uncollected package
  must fail the D2 test (proves the guard is live, not vacuous).

## Corrections to the initiating analysis

1. **`BUNDLED_ONLY_PLUGIN_IDS` is not dead residue.** The Locksmith brand has **no `[plugins]`
   section**, so `brand().bundled_plugins == ()`. Naively requiring brand listing for all
   entry-point plugins would stop `kerifoundation` loading on Locksmith — reproducing the regression
   in `backlog/2026-07-09-kerifoundation-plugin-brand-leak-and-onboarding-crash.md`. The frozenset
   encodes a load-bearing *default-on vs opt-in* distinction. Its defect is only that it lives in a
   framework id list; the fix is relocation (to the entry-point group), not deletion.
2. **`PluginSource` is the wrong name** — "source" already means the installer's provenance
   descriptor in this very module. Using `PluginOrigin` for the discovery channel.
3. **Loading and activation should not share one strategy vocabulary.** `RoleActivationStrategy`
   answers "what does unlock *do*"; the policy chain here answers "should this load at all". Reusing
   the same protocol would conflate a boolean gate with a behavioral strategy.

## Non-goals

- Sandboxing, signing, or runtime capability enforcement (still per the Stage-1 trust model:
  install-time confirmation, full permissions thereafter).
- Building the gated-remote origin. This design makes it an additive `PluginOrigin`; that is the point.
- Changing the credential gate or `RoleActivationStrategy`.
- Brand-scoping plugin storage (see `backlog/2026-07-25-vault-namespace-not-brand-scoped.md`).
