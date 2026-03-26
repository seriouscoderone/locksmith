# Locksmith

This repo is the KERI Foundation open port of the Locksmith wallet.

## Developer Setup

The package metadata currently allows Python `>=3.12.6`, but the team has already hit local issues with Python `3.14`. For now, prefer Python `3.13` until `3.14` is explicitly validated for this repo.

From the repo root:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Asset Regeneration

Qt resources are generated from `resources.qrc` into `src/locksmith/resources_rc.py`.

From the repo root:

```bash
python ./scripts/generate_qrc.py
pyside6-rcc resources.qrc -o resources_rc.py
mv resources_rc.py ./src/locksmith/
```

## Run The App

After installing the package in editable mode, start Locksmith from the repo root:

```bash
python -m locksmith.main
```

## Build The Docs

The first Sphinx pass is intentionally scoped to the plugin system, application lifecycle,
main window wiring, vault list pages, and the developer guide.

From the repo root:

```bash
python -m pip install -r docs/requirements.txt
sphinx-build -b html docs docs/_build/html
```

The docs now include a plugin-authoring guide with a minimal example plugin skeleton.

## Docs Map

The current Sphinx docs are intentionally scoped. Start here depending on what you need:

- `docs/developer-guide.rst`: local setup, runtime expectations, and docs build flow
- `docs/plugin-authoring.rst`: plugin lifecycle, page/menu registration, and account-provider setup branching
- `docs/vault-navigation.rst`: how `VaultPage` and `VaultNavMenu` coordinate the in-vault shell
- `docs/credential-pages.rst`: the built-in credentials list pages
- `docs/identifier-pages.rst`: the built-in remote and group identifier list pages
- `docs/remote-workflows.rst`: remote identifier dialog flows
- `docs/group-workflows.rst`: group identifier dialog flows
- `docs/credential-workflows.rst`: issued, received, and schema credential dialog flows
- `docs/api-reference.rst`: scoped autodoc surface for the documented host modules and list pages

## Plugin Contract

Locksmith discovers plugins through the Python entry-point group `locksmith.plugins`.

At startup, `LocksmithWindow` creates `LocksmithApplication`, then calls `PluginManager.discover_and_initialize(vault_page, vault_page.nav_menu)`. Each plugin is instantiated with no constructor arguments, receives the application object once through `initialize(app)`, and can then register pages and menu sections.

Every plugin must subclass `PluginBase` and implement:

- `plugin_id()`
- `initialize(app)`
- `on_vault_opened(vault)`
- `on_vault_closed(vault)`
- `get_menu_entry()`
- `get_menu_section()`
- `get_pages()`

Optional plugin capabilities include:

- `get_doers()` for background doers that are appended to `vault.doers` when a vault opens
- witness provisioning hooks such as `get_witness_batches()`, `get_witness_state()`, and witness-state update methods
- `after_identifier_authenticated()` for post-auth follow-up work

Locksmith also exposes marker mixins for narrower roles:

- `AccountProviderPlugin`
- `IdentifierUploadProviderPlugin`
- `WitnessProviderPlugin`
- `WatcherProviderPlugin`
- `CredentialProviderPlugin`

Minimal entry-point example in `pyproject.toml`:

```toml
[project.entry-points."locksmith.plugins"]
myplugin = "my_package.my_plugin:MyPlugin"
```

The plugin manager loads entry points by name, instantiates the plugin class, registers its pages into `VaultPage`, and registers its menu section into the vault navigation menu.
