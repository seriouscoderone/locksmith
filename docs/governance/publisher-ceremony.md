# Publisher AID Ceremony Runbook

Source of truth for bootstrapping and operating the KERI.host publisher AID that anchors every Locksmith release.

## Roles

- **Custodian operator** — runs the ceremony script on each device. Same person can operate all three devices, just one at a time.
- **Independent observer** (optional, recommended) — second physical person who watches the screen during the production ceremony. No keys; just a witness in the social sense.

## Custodian devices

| Device label | Storage | Slot |
|--------------|---------|------|
| Laptop signer | YubiKey 5 Series, FIDO2/PIV | PIV slot `9c` (Digital Signature) |
| Desktop signer | YubiKey 5 Series, FIDO2/PIV | PIV slot `9c` |
| Air-gapped backup | USB drive on a non-network device, key file encrypted with passphrase | n/a (software key) |

Document the physical location of each device in [`publisher-custodians.md`](publisher-custodians.md).

## Prerequisites

- `tools/publisher/` installed in a venv on the device performing each step
- All three devices enrolled (YubiKeys initialized with the chosen PIV PIN/PUK; air-gapped USB prepared)
- Confirmed witness pool: at least 3 distinct witness AIDs at `api.keri.host`. Query:
  ```
  curl https://api.keri.host/witness/pool | jq .witnesses
  ```
  If fewer than 3 are returned, stop and add witnesses to the pool before continuing.
- AWS credentials configured (only required for the final upload step)

## Stage 0 — Staging dry-run

Before any production keys are generated, run the full ceremony against staging witnesses with FakeYubiKeyDevice backends. **Do this at least once for every new operator.**

```bash
cd tools/publisher
source .venv/bin/activate
python ceremony/incept.py \
    --dry-run \
    --output-dir /tmp/locksmith-ceremony-dry-run \
    --witness-oobi https://staging.keri.host/witness/oobi/Bw1... \
    --witness-oobi https://staging.keri.host/witness/oobi/Bw2... \
    --witness-oobi https://staging.keri.host/witness/oobi/Bw3...
```

Expected outputs in `/tmp/locksmith-ceremony-dry-run/`:

- `publisher_anchor.json` — trust anchor (placeholder values; not for committing)
- `publisher-aid.json` — S3 summary file
- `kel-events/icp-sn-0.cesr` — inception event

Inspect the inception event. The dry-run is successful when the script exits cleanly and all three files exist.

## Stage 1 — Production inception

Perform on one device at a time, in this order. The script connects to real YubiKey devices via PIV.

1. **Laptop signer (signer 0):**
   - Insert laptop YubiKey
   - Run:
     ```bash
     python ceremony/incept.py \
         --production \
         --output-dir ~/locksmith-ceremony/01-laptop \
         --witness-oobi $(api-keri-host-oobi 1) \
         --witness-oobi $(api-keri-host-oobi 2) \
         --witness-oobi $(api-keri-host-oobi 3) \
         --yubikey-slot 9c
     ```
   - Enter PIV PIN when prompted
   - Confirm the AID prefix shown on screen
2. **Desktop signer (signer 1):** repeat on the desktop machine, contributing the second signature
3. **Air-gapped backup (signer 2):** boot the offline device, contribute the third signature, transfer signed event back via the USB drive

(The full *multi-device coordination* protocol — devices contributing partial signatures on separate machines that are merged later — is implemented in Phase 4 alongside the release-signing flow. In Phase 1 the inception event is built, signed, and submitted in a single run on one machine using all three devices physically attached. If only one YubiKey is available at ceremony time, run Stage 0 again and defer Stage 1 until both YubiKeys are present.)

## Stage 2 — Submit to witnesses

The ceremony script collects per-device signatures over the serialized inception event, attaches them as CESR signature blocks, and submits the signed stream to the api.keri.host witness pool. The pool returns one receipt per witness that accepted the event. The ceremony aborts if fewer than `toad` (default 2) receipts come back; the operator can retry the submission because witnesses are idempotent on event SAID.

After successful submission the publisher AID is **live**:

- Receipts are persisted alongside the inception event at `kel-events/icp-sn-0.receipts.json`
- `publisher-aid.json` is rewritten with `status: live` and the receipt count
- The publisher AID exists in the world and the KEL is now witnessed

Pass `--no-submit` to override this default (e.g. dry-run rehearsals on developer workstations).

## Stage 3 — Commit the trust anchor

After Stage 2 succeeds and witness receipts are gathered:

1. Copy `publisher_anchor.json` from the ceremony output directory to `src/locksmith/release/publisher_anchor.json` in a checkout of the repo
2. Inspect: confirm AID prefix is real (starts with `E`, not `PLACEHOLDER_`)
3. Commit:
   ```bash
   git add src/locksmith/release/publisher_anchor.json
   git commit -m "release: anchor production publisher AID"
   ```
4. Push and merge through normal review (this commit deserves a second pair of eyes — it is the trust root of every future release)

## Stage 4 — Publish to S3

After the trust anchor is committed:

```bash
aws s3 cp publisher-aid.json s3://releases.keri.host/publisher/v1/publisher-aid.json
aws s3 cp kel-events/ s3://releases.keri.host/publisher/v1/kel-events/ --recursive
```

CloudFront's `publisher/*` cache behavior is 60s TTL, so updates propagate quickly.

## Recovery procedures

| Scenario | Procedure |
|----------|-----------|
| One device lost or stolen | 2-of-3 quorum unaffected. Rotate keys (Phase 4 flow) to invalidate the missing device's key set. |
| Two devices lost | Quorum broken. Use air-gapped backup + emergency reissue. See `docs/governance/publisher-recovery.md` (deferred to Phase 4). |
| Suspected compromise | Immediate rotation. Pre-rotation digests in the most recent KEL event allow rotation within hours. |
| All three devices lost | Catastrophic. Publish abandonment notice via `keri.host` blog; users continue on the last verified version until a new AID + ceremony bootstraps trust. |

## Verification

After Stage 4 completes, any third party can independently verify the AID:

```bash
curl https://releases.keri.host/publisher/v1/publisher-aid.json
curl https://releases.keri.host/publisher/v1/kel-events/icp-sn-0.cesr -o icp.cesr
# Replay against api.keri.host witnesses to confirm inception event was witnessed
```
