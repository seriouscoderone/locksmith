# Locksmith
This is the KERI Foundation open port of the Locksmith wallet

to update assets, in locksmith directory run
```bash
python ./scripts/generate_qrc.py; pyside6-rcc resources.qrc -o resources_rc.py; mv resources_rc.py ./src/locksmith;
```

To run the app:
```bash
python ./src/locksmith/main.py
```
## To run with local witness, watchers

### in witness-hk

```
witopnet marshal start \
  --config-dir ./scripts \
  --host 0.0.0.0 \
  --http 5632 \
  --boothost 127.0.0.1 \
  --bootport 5631
```

### in watcher-hk

```
watopnet marshal start \
  --config-dir ./scripts \
  --host 0.0.0.0 \
  --http 7632 \
  --boothost 127.0.0.1 \
  --bootport 7631
```

### in locksmith

```
python ./src/locksmith/main.py
```

KERI Foundation plugin documentation lives in
[`docs/kerifoundation-plugin.rst`](docs/kerifoundation-plugin.rst).

## HOA build mode

Building with `LOCKSMITH_BRAND=usurance` produces the Higher-Order Application base —
the wallet pages are peeled (brand-gated) and the app boots into a single default
vault + AID, retaining KERI primitives and the plugin host. The default `locksmith`
brand is unchanged.
