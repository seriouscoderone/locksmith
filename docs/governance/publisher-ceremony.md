# Publisher AID Ceremony Runbook

Source of truth for bootstrapping and operating the KERI.host publisher AID that anchors every Locksmith release.

## v1 design: single-sig with pre-rotation

The v1 publisher AID uses a **single signing key** (`signers=1`, `quorum=1`). Multi-device multisig (2-of-3 etc.) is a **Phase 4 upgrade** delivered via KERI key rotation — the publisher AID prefix is unchanged across the rotation, so every release signed before and after stays verifiable. Single-sig in v1 is not a security compromise: it reflects that running three keys in one process provides no meaningful security over one key (an attacker who compromises the process gets all keys). True multisig defense requires keys on separate, isolated devices communicating via a partial-signing protocol, which is Phase 4 work.

## Bootstrap option: software keys (when YubiKeys aren't available yet)

The ceremony script supports software-backed Ed25519 keys persisted to passphrase-encrypted PEM files. This is the right starting point if you don't yet have YubiKeys — bootstrap the publisher AID now, rotate to hardware later via KERI pre-rotation (Phase 4 flow). The publisher AID prefix is preserved across the rotation; every release signed under either keyset stays verifiable.

The ceremony generates **two** key files per signer slot:

| File | Purpose |
|------|---------|
| `<keys-dir>/current/key-1.enc.pem` | Current signing key — used to sign the inception event |
| `<keys-dir>/next/key-1.enc.pem` | Pre-rotated next key — committed via its Blake2b-256 digest in `n:` |

The `next/` key is the essential pre-rotation material: it is the key you will sign the *rotation* event with later. Keep it as securely as the current key. Both files use the same passphrase (simpler operationally; both are in the same operator's custody).

**Operational hygiene for software keys:**

| Concern | Mitigation |
|---------|-----------|
| Key files at rest | Encrypted PKCS#8 PEM with scrypt-derived AES-256 (industry standard) |
| File permissions | `0600` (owner read/write only) — enforced by the SoftwareKeyDevice writer |
| Key files in transit (e.g., moving to cold storage) | Always via encrypted channel; never plaintext over network |
| Passphrase strength | Minimum 12 characters; use diceware or a password manager generator |
| Storing both current and next keys | Keep them in separate, distinct storage locations. The `current/` key can be on your working machine; the `next/` key should go to cold storage immediately after inception. |

**Recommended storage layout for the single-signer software keys (LastPass-based):**

| File | Storage | Passphrase storage |
|------|---------|--------------------|
| `current/key-1.enc.pem` | Laptop disk: `~/.locksmith-publisher/keys-production/current/key-1.enc.pem` | LastPass secure note: "Locksmith publisher current key passphrase" |
| `next/key-1.enc.pem` | Cold storage: LastPass attachment in secure note "Locksmith publisher next key (cold)" | **Memorized OR written on paper, stored physically** — NOT in LastPass. This is your defense in depth for the future rotation event. |

**LastPass-specific notes:**
- LastPass supports file attachments in Secure Notes (Advanced item type). Upload the `next/key-1.enc.pem` file as an attachment.
- LastPass attachments are encrypted with your LastPass master password — but LastPass has been breached before (2022 incident exposed encrypted vaults). Keeping the next-key's passphrase outside LastPass is meaningful defense in depth.
- If you upgrade to 1Password or Bitwarden later, migrate using the password manager's export/import; same pattern applies.

**Recovery test (do this BEFORE relying on the keys):**

1. Run the ceremony in dry-run with software keys (see Stage 0 below)
2. Move the `next/` key file to cold storage
3. **Re-run the ceremony in `--dry-run` mode** with `--software-keys` pointing at a fresh directory + the keys retrieved back from storage
4. Confirm both key files are loaded without error — proves you can recover. Note: the AID prefix will differ from the first run because KERI self-addressing identifiers bind the prefix to the full inception event content. The real inception uses the keys only once; the recovery test validates that you can decrypt and reload each key file.

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
# Prompts interactively for 1 passphrase (single-sig default).
# Creates: keys-dry-run/current/key-1.enc.pem  (current signing key)
#          keys-dry-run/next/key-1.enc.pem      (pre-rotated next key)
```

Stage 1 (production inception) with software keys:
```bash
mkdir -p ~/.locksmith-publisher/keys-production
python ceremony/incept.py \
    --production \
    --output-dir ~/locksmith-ceremony/output \
    --software-keys ~/.locksmith-publisher/keys-production \
    --toad 3
# Prompts interactively for the production passphrase.
# After this completes successfully, the publisher AID is live on the
# 5-witness federation. Immediately move next/key-1.enc.pem to cold storage.
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

Inspect the inception event. The dry-run is successful when the script exits cleanly and all expected files exist.

## Stage 1 — Production inception

The v1 ceremony is a **single-sig, single-machine** run. Multi-device multisig coordination is a Phase 4 upgrade (see "v1 design" section above).

For software-key inception (recommended for v1):

```bash
mkdir -p ~/.locksmith-publisher/keys-production
python ceremony/incept.py \
    --production \
    --output-dir ~/locksmith-ceremony/output \
    --software-keys ~/.locksmith-publisher/keys-production \
    --toad 3
# Prompts for one passphrase.
# Confirm the AID prefix shown on screen before proceeding.
```

Expected files after completion:
- `~/.locksmith-publisher/keys-production/current/key-1.enc.pem` — signing key
- `~/.locksmith-publisher/keys-production/next/key-1.enc.pem` — pre-rotation next key
- `~/locksmith-ceremony/output/kel-events/icp-sn-0.cesr` — inception event (signed)
- `~/locksmith-ceremony/output/publisher-aid.json` — `status: live`, `receipt_count: 5`

Immediately after the ceremony: move `next/key-1.enc.pem` to cold storage.

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
| Current key lost or stolen | Rotate immediately (Phase 4 flow) using the `next/key-1.enc.pem` pre-rotation key. The rotation event signed with the next key is the only valid continuation of the KEL. |
| Both current and next keys lost | Catastrophic loss of the AID. Publish abandonment notice via `keri.host` blog; users continue on the last verified version until a new AID + ceremony bootstraps trust. |
| Suspected compromise of current key only | Rotate immediately using the next key (same as key-lost scenario). |
| Suspected compromise of next key (without use) | Do NOT rotate yet — rotating uses the next key and exposes a new pre-rotation commitment. Instead, treat this as current-key-compromised: rotate from current key to invalidate the compromised next key, which requires knowing the *current* key. Consult `docs/governance/publisher-recovery.md` (Phase 4). |

## Verification

After Stage 4 completes, any third party can independently verify the AID:

```bash
curl https://releases.keri.host/publisher/v1/publisher-aid.json
curl https://releases.keri.host/publisher/v1/kel-events/icp-sn-0.cesr -o icp.cesr
# Replay against api.keri.host witnesses to confirm inception event was witnessed
```
