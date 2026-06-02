# Publisher AID Ceremony Runbook

Source of truth for bootstrapping and operating the KERI.host publisher AID that anchors every Locksmith release.

## Bootstrap option: software keys (when YubiKeys aren't available yet)

The ceremony script supports software-backed Ed25519 keys persisted to passphrase-encrypted PEM files. This is the right starting point if you don't yet have YubiKeys — bootstrap the publisher AID now, rotate to hardware later via KERI pre-rotation (Phase 4 flow). The publisher AID prefix is preserved across the rotation; every release signed under either keyset stays verifiable.

**Operational hygiene for software keys:**

| Concern | Mitigation |
|---------|-----------|
| Key files at rest | Encrypted PKCS#8 PEM with scrypt-derived AES-256 (industry standard) |
| File permissions | `0600` (owner read/write only) — enforced by the SoftwareKeyDevice writer |
| Key files in transit (e.g., moving to cold storage) | Always via encrypted channel; never plaintext over network |
| Passphrase strength | Minimum 12 characters; use diceware or a password manager generator |
| Distribution of the 3 keys | After inception, distribute the 3 encrypted files to 3 distinct storage locations |
| Loading 3 keys into one process | Inevitable for the inception ceremony (one-time event); accept the risk and run on a clean machine. For release signing (Phase 4), implement multi-machine partial-signing so the 3 keys never co-reside in memory again. |

**Recommended storage layout for the 3 software keys (LastPass-based):**

| Key | File storage | Passphrase storage |
|-----|--------------|--------------------|
| Key 1 (primary) | Laptop disk: `~/.locksmith-publisher/keys/key-1.enc.pem` | LastPass secure note: "Locksmith publisher key 1 passphrase" |
| Key 2 (secondary) | Desktop disk: `~/.locksmith-publisher/keys/key-2.enc.pem` | LastPass secure note: "Locksmith publisher key 2 passphrase" (DIFFERENT note, different passphrase from Key 1) |
| Key 3 (cold backup) | LastPass attachment in secure note "Locksmith publisher key 3 (cold)" | **Memorized OR written on paper, stored physically** — NOT in LastPass. This is your defense in depth: if both your laptop and LastPass are compromised, Key 3 is still safe. |

**LastPass-specific notes:**
- LastPass supports file attachments in Secure Notes (Advanced item type). For Key 3, upload the encrypted `key-3.enc.pem` file as an attachment.
- LastPass attachments are encrypted with your LastPass master password — but LastPass has been breached before (2022 incident exposed encrypted vaults). Keeping Key 3's passphrase outside LastPass is meaningful defense in depth.
- If you upgrade to 1Password or Bitwarden later, migrate using the password manager's export/import; same pattern applies.

**Recovery test (do this BEFORE relying on the keys):**

1. Run the ceremony in dry-run with software keys (see Stage 0 below)
2. Move the 3 key files to their respective storage locations (laptop, desktop, LastPass)
3. **Re-run the ceremony in `--dry-run` mode** with `--software-keys` pointing at a fresh directory + the keys downloaded back from each location
4. Confirm all three key files are loaded without error — proves you can recover. Note: the AID prefix will differ from the first run because KERI self-addressing identifiers bind the prefix to the full inception event (including freshly generated pre-rotation next-key digests). The real inception uses the keys only once; the recovery test validates that you can decrypt and reload each key file.

### Software-key ceremony invocation

Stage 0 (dry-run rehearsal) with software keys:
```bash
cd tools/publisher
source .venv/bin/activate
mkdir -p ~/.locksmith-publisher/keys-dry-run
python ceremony/incept.py \
    --dry-run \
    --output-dir /tmp/locksmith-ceremony-dry-run \
    --software-keys ~/.locksmith-publisher/keys-dry-run \
    --toad 3
# Prompts interactively for 3 passphrases.
```

Stage 1 (production inception) with software keys:
```bash
mkdir -p ~/.locksmith-publisher/keys-production
python ceremony/incept.py \
    --production \
    --output-dir ~/locksmith-ceremony/output \
    --software-keys ~/.locksmith-publisher/keys-production \
    --toad 3
# Prompts interactively for the 3 production passphrases.
# After this completes successfully, the publisher AID is live on the
# 5-witness federation. Immediately distribute the 3 encrypted key files
# to their respective storage locations (per table above).
```

---

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
- Confirmed availability of the KERI.host 5-witness federation:
  - `witness.keri.host` → `BE4B4CjpxNrCv8_HjLYvcwz-sui6AcJdygO-afEoTpmi`
  - `witness.legitim.us` → `BFuK9vjfkaGd5DdyAABzd00vmsxQ3bDDnUAAGpxc7ZGP`
  - `witness.goonei.com` → `BE7l4TEmGGpDAccj5Hc0bcIm5nABU2V2gFTrcF5NfT2j`
  - `witness.verdadero.me` → `BGR9eydkMxsAniqb3FSJwA24ADRM96STzWE_aaOeiyC5`
  - `witness.honest.town` → `BKCg06XEU80byz4ioN4Iim-7x2TzuklqKKuWRrViDqGV`

  Verify each is responsive:
  ```
  for w in witness.keri.host witness.legitim.us witness.goonei.com witness.verdadero.me witness.honest.town; do
    curl -sI "https://$w/witness" | head -1
  done
  ```

  toad=3 means we need at least 3 of the 5 to respond at submission time.
- AWS credentials configured (only required for the final upload step)

## Stage 0 — Staging dry-run

Before any production keys are generated, run the full ceremony against staging witnesses with FakeYubiKeyDevice backends. **Do this at least once for every new operator.**

```bash
cd tools/publisher
source .venv/bin/activate
python ceremony/incept.py \
    --dry-run \
    --output-dir /tmp/locksmith-ceremony-dry-run \
    --toad 3
# Uses the KERI.host 5-witness federation by default.
# Override with --witness-oobi <url> --witness-oobi <url> ... to use a different pool.
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
         --toad 3 \
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
