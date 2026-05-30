# Publisher Custodian Devices

Physical inventory and location of the three signing devices that hold the publisher AID's 2-of-3 multisig key shares. **This document is sensitive — review access control before committing real location data.**

| Device label | Hardware | Serial | Physical location | Notes |
|--------------|----------|--------|-------------------|-------|
| Laptop signer | YubiKey 5 (model TBD) | TBD | TBD by operator | Daily-carry device. Replace YubiKey every 3 years or on suspected exposure. |
| Desktop signer | YubiKey 5 (model TBD) | TBD | TBD by operator | Office device. Keep physically secured when unattended. |
| Air-gapped backup | USB drive (model TBD) | TBD | Fireproof safe at TBD address | Powered on only during ceremonies. Never connected to a network. |

## Update procedure

1. Edit this file
2. Open a PR with the change
3. Two reviewers (the operator + one trusted reviewer) must approve
4. After merge, the operator confirms the physical state matches the recorded state

## Rotation triggers

- Annual scheduled rotation
- Device replacement (e.g. laptop refresh)
- Suspected compromise
- Operator change

When any of the above happens, follow the rotation procedure in `publisher-ceremony.md` Stage 1 with the new device(s), then update this file.
