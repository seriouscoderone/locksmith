# LockSmith
This is  the KERI Foundation open port of the LockSmith wallet

to update assets, in locksmith directory run
```bash
python ./scripts/generate_qrc.py; pyside6-rcc resources.qrc -o resources_rc.py; mv resources_rc.py ./src/locksmith;
```

To run the app:
```bash
python ./src/locksmith/main.py
```

## KERI Foundation Plugin

This repo includes the KERI Foundation plugin. It adds a `KERI Foundation`
section in the vault sidebar for KERI Foundation witness management.

### Configure witness servers

The plugin reads witness server endpoints from environment variables.

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Set the environment you want to run:
   - `LOCKSMITH_ENVIRONMENT=development` uses `KF_DEV_*`
   - `LOCKSMITH_ENVIRONMENT=staging` or `production` uses `KF_PROD_*`

3. Configure one or more witness servers in `.env`:
   ```bash
   KF_DEV_WITNESS_URL_1=http://127.0.0.1:5632
   KF_DEV_BOOT_URL_1=http://127.0.0.1:5631
   KF_DEV_REGION_1=local
   KF_DEV_LABEL_1="Local Dev"
   ```

4. Additional servers can be added with contiguous numbering:
   ```bash
   KF_DEV_WITNESS_URL_2=http://127.0.0.1:5732
   KF_DEV_BOOT_URL_2=http://127.0.0.1:5731
   KF_DEV_REGION_2=west
   KF_DEV_LABEL_2="Local Dev 2"
   ```

Both `WITNESS_URL_N` and `BOOT_URL_N` are required for a server entry.
`REGION_N` and `LABEL_N` are optional. If a label contains spaces, quote it.

### Run with plugin configuration

The app does not load `.env` automatically, so load it into your shell before
starting Locksmith:

```bash
export LOCKSMITH_ENVIRONMENT=development
set -a
source .env
set +a
python ./src/locksmith/main.py
```
