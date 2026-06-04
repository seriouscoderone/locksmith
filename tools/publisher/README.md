# locksmith-publisher

The off-CI signing CLI for Locksmith releases. **Never installed in CI.** Only runs on custodian devices (laptop YubiKey, desktop YubiKey, air-gapped backup) that hold KERI signing keys for the publisher AID.

See [`docs/governance/publisher-ceremony.md`](../../docs/governance/publisher-ceremony.md) for the full ceremony runbook.

## Install (custodian devices only)

```bash
cd tools/publisher
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
locksmith-publisher --help
```

## Subcommands

| Command | Status (Phase 1) | Purpose |
|---------|------------------|---------|
| `incept` | implemented | One-time: bootstrap the 2-of-3 multisig publisher AID |
| `sign` | stub | Phase 4: signer 1 produces partial release anchor signature |
| `countersign` | stub | Phase 4: signer 2 adds second signature to reach 2-of-3 quorum |
| `submit` | stub | Phase 4: submit signed anchor + collect witness receipts, upload to S3 |
| `verify-ceremony` | stub | Phase 4: re-verify a finalized anchor against witnesses |
