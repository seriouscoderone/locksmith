# Locksmith TODO

## We Must Implement

- Configure root AID, API AID, OOBIs, and API URLs in `core/configing.py` (all currently empty strings with TODO comments)
- Deploy witnesses and watchers infrastructure
- Build and register a KERI Foundation plugin — see `plugins/base.py` for contracts, `plugins/manager.py` for discovery via `importlib.metadata.entry_points(group="locksmith.plugins")`
- Re-implement watcher management, witness account lifecycle, and ESSR integration in a KERI Foundation plugin (removed healthKERI-specific implementation from core)
- Implement auth mechanism for turret browser plugin — `turret/authing.py` delegation check currently returns False without a configured root AID
    - This is only if we are creating a browser plugin to be used with locksmith
- Register new plugin entry point in `pyproject.toml` and run `pip install -e .`
- reconcile essr vs http for witnesses
- Plan for how to load custom assets from plugins