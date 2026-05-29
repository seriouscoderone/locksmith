# Locksmith Deployment, Install & Update System — Design

**Date:** 2026-05-28
**Owner:** seriouscoderone (publishing under the KERI.host entity)
**Status:** Draft (brainstorming complete, awaiting user review before implementation planning)
**Branch:** `worktree-feat+deploy-update-design` (off `development`)

---

## 1. Summary

This document specifies how `seriouscoderone/locksmith` is built, signed, distributed, installed, updated, and cryptographically verified by end users on **macOS and Windows**. The goals are:

1. **Enterprise-grade UX** — install and update feel as polished as Slack, 1Password, Linear desktop. No OS warnings, no terminal commands, no console flashes, no "Allow this app" friction.
2. **KERI-anchored release authenticity** — every update is cryptographically tied back to a publisher KERI AID whose KEL is witnessed by `api.keri.host`. Users (and external auditors) can independently verify "is this update real?" against the same KERI infrastructure that anchors their other identifiers.
3. **AWS-native infrastructure** — release artifacts, CDN, DNS, CI auth all on AWS services already used by the user. Migrate away from the legacy DigitalOcean references inherited from the upstream `keri-foundation/locksmith` fork.

The system is composed of six independent subsystems with narrow interfaces. Each can be developed, tested, and reasoned about on its own.

---

## 2. Non-Goals (v1)

- Linux distribution. Mac + Windows only for v1; Linux is a follow-up.
- App store distribution (Mac App Store, Microsoft Store). Direct download only.
- MDM / Group Policy / enterprise configuration profiles. Deferred to a later release.
- Multiple release channels (beta, nightly). Single `stable` channel only.
- Per-release ACDC credentials. Releases are anchored as KEL interaction events; ACDC issuance is a future enhancement.
- Multi-witness attestation by third parties. Only `api.keri.host` witnesses (user-operated) attest releases.
- Delta updates / binary diffs. Full artifact download per release; revisit later if download size is a problem.

---

## 3. Locked-In Decisions

| Area | Decision |
|------|----------|
| Distribution | Direct download only, no app stores |
| macOS package | DMG (drag-to-Applications), Apple Developer ID signed, notarized + stapled |
| Windows package | MSI authored with WiX Toolset, signed via Azure Trusted Signing |
| Updater (macOS) | Sparkle 2.x — used as orchestrator only, native signature verification **disabled** |
| Updater (Windows) | WinSparkle — used as orchestrator only, native signature verification **disabled** |
| Update UX | Hybrid: minor/patch installs silently on quit; major versions show "What's New" modal; critical security updates surface a banner with 24h deferral cap |
| Trust model | Approach B-practical: KERI is the sole trust mechanism. Sparkle/WinSparkle download and stage; a Python verifier gates installation. |
| Publisher entity | **KERI.host** (user-owned, future non-profit) — see `project_keri_host_publisher_entity` memory |
| Publisher AID custodian model | Solo developer, 2-of-3 multisig across devices: laptop YubiKey, desktop YubiKey, air-gapped USB backup |
| Witness pool | `api.keri.host/witness/*` (already operated by the user) |
| Release anchoring | KEL interaction events with anchored seals — **no separate TEL**. Each release = one `ixn` event in the publisher KEL. |
| Trust anchor bootstrap | `publisher_aid` prefix + KEL hash embedded in each build at build time; OS code signing attests the embedded values |
| CDN domain | `releases.keri.host` (AWS Route 53 + CloudFront + ACM cert) |
| Object storage | AWS S3 (replaces inherited DigitalOcean Spaces) |
| CI auth to AWS | GitHub Actions OIDC → IAM role (no long-lived access keys) |
| App bundle ID | `host.keri.locksmith` (reverse-DNS under keri.host) |
| Versioning | Strict semver; `is_major` derived from semver bump and drives UX path |
| Release channel | Single `stable` channel for v1 |
| Appcast history | Full history retained (every published version stays in the appcast `releases` array) |

---

## 4. System Architecture

Six subsystems, each with one clear purpose:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Build & Package (CI)                            │
│   PyInstaller → codesign/notarize/Sparkle-stage → DMG (mac) / MSI (win)  │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ artifacts + SHA256s
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       KERI Publisher Service                             │
│   tools/publisher/ CLI — 2-of-3 multisig ceremony, emits signed ixn      │
│   event anchored in publisher AID KEL (witnessed by api.keri.host)       │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ release-anchor-X.Y.Z.cesr
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        CDN / Distribution (AWS)                          │
│   S3 (releases.keri.host bucket) ← CloudFront ← ACM cert ← Route 53      │
│   Appcast JSON (60s TTL) + immutable artifact URLs (forever TTL)         │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ HTTPS
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Updater (client-side orchestrator)                  │
│   Sparkle (macOS) / WinSparkle (Windows) — signature checks OFF          │
│   Downloads + stages artifact, invokes verifier before install           │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ staged_path
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  KERI Verifier (client-side, in-app Python)              │
│   locksmith.update.verify — fetches publisher KEL via OOBI,              │
│   replays from embedded hash forward, checks witness receipts,           │
│   matches artifact SHA256 against anchored seal. Gates install.          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Trust chain at runtime

```
OS code signature (Apple Developer ID / Authenticode via Azure Trusted Signing)
    └─ proves the installed Locksmith binary was published by KERI.host
        └─ inside that binary: embedded publisher_aid prefix + KEL hash at build time
            └─ each update is KERI-verified against this AID via api.keri.host
                └─ KEL is replayed from the embedded hash forward
                    └─ witness receipts verified for each event up to the release ixn
                        └─ artifact SHA256 matched against the anchored seal
```

The first install's trust is bootstrapped by the OS code signature. After that, every update's trust flows through KERI. The OS code signature on each subsequent update is still required (Gatekeeper / SmartScreen need it) but **is not load-bearing for our integrity model** — if Apple's or Microsoft's signing infrastructure were compromised, KERI verification would still catch a malicious update.

---

## 5. Build & Package Pipeline

### 5.1 Bundling (both platforms)

PyInstaller produces platform-native binaries from the PySide6 app. Two committed spec files:

- `packaging/Locksmith.macos.spec` → `dist/Locksmith.app`
- `packaging/Locksmith.windows.spec` → `dist/Locksmith/Locksmith.exe` + dependencies

Both spec files:

- Read version from `pyproject.toml` (single source of truth, enforced by `scripts/check-version.py` as a CI pre-flight)
- Embed `src/locksmith/release/publisher_anchor.json` (committed; contains `publisher_aid` prefix + KEL hash at build time + witness OOBI URLs)
- Bundle libsodium dylibs/DLLs and Qt plugins required by PySide6
- Output is hidden-import-clean (any pinned hidden imports discovered during initial spec authoring are listed in the spec file with comments)

### 5.2 macOS pipeline

Replaces the stubbed step in `.github/workflows/release.ci.yml`. Sequence:

1. PyInstaller → `dist/Locksmith.app`
2. `scripts/signLibs.sh` signs nested dylibs (libsodium — already in repo)
3. `codesign --deep --options runtime --entitlements entitlements.plist --sign "$DEVELOPER_ID_APP_CERT"` on the `.app`
4. `create-dmg` produces `Locksmith-X.Y.Z.dmg` with a designed background image, Applications symlink, and properly positioned icon layout. Assets committed to `packaging/dmg/background.png` and `packaging/dmg/layout.json`.
5. `xcrun notarytool submit --wait` notarizes; `xcrun stapler staple` attaches the ticket
6. Output: `Locksmith-X.Y.Z.dmg`, signed + notarized + stapled

### 5.3 Windows pipeline

New flow, replaces the stub in CI:

1. PyInstaller → `dist/Locksmith/`
2. WiX Toolset authored from `packaging/wix/Locksmith.wxs`:
   - `heat` harvests the PyInstaller output directory into a fragment
   - `candle` compiles WXS → WIXOBJ
   - `light` links → `Locksmith-X.Y.Z.msi`
3. `Locksmith.exe` (the main executable inside the MSI payload) is signed via Azure Trusted Signing **before** MSI authoring, so the MSI bundles a signed binary
4. The MSI itself is then signed via Azure Trusted Signing using the official `Azure/trusted-signing-action@v0.x` GitHub Action
5. Output: `Locksmith-X.Y.Z.msi`, signed

### 5.4 Publisher signing step

A separate CI job (`anchor-release`) runs after both platform builds succeed:

- Takes the SHA256s of `Locksmith-X.Y.Z.dmg` and `Locksmith-X.Y.Z.msi`
- Emits a `release-candidate.json` to a staging S3 prefix (e.g., `s3://releases-staging.keri.host/candidates/X.Y.Z/`) containing the metadata to be anchored
- **Stops there.** Final signing happens off-CI, on the publisher's devices, via `tools/publisher/` (see §7)
- Once the signing ceremony completes, a follow-up job (`publish`) picks up the signed `release-anchor-X.Y.Z.cesr` artifact, uploads to `releases.keri.host`, and refreshes the appcast

This split is **intentional**: CI cannot sign releases on its own. The signing keys never touch the CI environment.

### 5.5 Versioning

- Tags are `vX.Y.Z` (strict semver). CI pre-flight verifies `pyproject.toml`'s `version` matches the tag.
- `is_major` is computed from semver bump: `1.x → 2.x` is major; `1.2.x → 1.3.x` is minor; patch bumps are patch.
- Two build-time constants are baked into the binary:
  - `LOCKSMITH_VERSION` — used by Sparkle/WinSparkle's `Info.plist`/version resource
  - `LOCKSMITH_RELEASE_CHANNEL` — currently always `"stable"`; reserved for future multi-channel support

### 5.6 CI structure

```yaml
jobs:
  preflight:           # version sanity, lint, fast unit tests
  build-macos:         # produces Locksmith-X.Y.Z.dmg, parallel with build-windows
  build-windows:       # produces Locksmith-X.Y.Z.msi, parallel with build-macos
  anchor-release:      # needs: build-macos, build-windows. Emits release-candidate.json
  # — manual gap: publisher runs tools/publisher/ signing ceremony off-CI —
  publish:             # triggered separately by signed-anchor upload to S3
                       # uploads artifacts to releases.keri.host, refreshes appcast
```

CI auth uses GitHub Actions OIDC → an IAM role (`gha-locksmith-release-publisher`). No long-lived AWS access keys in repository secrets.

---

## 6. Distribution & Appcast

### 6.1 S3 bucket layout

Bucket: `releases.keri.host` (origin-access-identity restricted; public access only via CloudFront).

```
/
├─ appcast/
│  ├─ v1/
│  │  ├─ macos.json
│  │  └─ windows.json
│  └─ archive/
│     └─ {date}/...                       # historical snapshots, written before each appcast update
├─ releases/
│  ├─ 1.0.0/
│  │  ├─ Locksmith-1.0.0.dmg
│  │  ├─ Locksmith-1.0.0.msi
│  │  └─ release-anchor-1.0.0.cesr        # signed KEL ixn event + witness receipts
│  ├─ 1.0.1/...
│  └─ latest/                             # CloudFront redirects (not real S3 objects)
│     ├─ macos.dmg  → 1.0.1/Locksmith-1.0.1.dmg
│     └─ windows.msi → 1.0.1/Locksmith-1.0.1.msi
└─ publisher/
   └─ v1/
      ├─ publisher-aid.json               # publisher AID prefix + latest KEL summary
      └─ kel-events/                      # full KEL history (CESR streams) for independent audit
```

### 6.2 CloudFront distribution

Domain: `releases.keri.host` (CNAME via Route 53, ACM cert).

Behavior settings:
- `releases/*` — long TTL (cache forever; URLs are immutable per version). Compression off (binaries don't compress).
- `appcast/v1/*` — short TTL (60 seconds) so new releases propagate quickly. Compression on (JSON).
- `publisher/v1/*` — short TTL (60 seconds). KEL changes infrequently, but rotations must propagate.
- `latest/*` — short TTL (60 seconds). Used as a fallback for "download the latest" links from the website.
- HTTP → HTTPS redirect at edge. HTTP/2 + HTTP/3 enabled. TLS 1.2+.
- Custom 404 page (branded, not raw CloudFront default).

### 6.3 Appcast schema (`appcast/v1/macos.json`)

```json
{
  "schema_version": 1,
  "channel": "stable",
  "publisher_aid": "EAbc...XYZ",
  "publisher_kel_url": "https://releases.keri.host/publisher/v1/publisher-aid.json",
  "current_version": "1.2.3",
  "releases": [
    {
      "version": "1.2.3",
      "released_at": "2026-05-28T14:30:00Z",
      "platform": "macos",
      "minimum_system_version": "13.0",
      "artifact_url": "https://releases.keri.host/releases/1.2.3/Locksmith-1.2.3.dmg",
      "artifact_sha256": "abc123...",
      "artifact_size": 87654321,
      "anchor_url": "https://releases.keri.host/releases/1.2.3/release-anchor-1.2.3.cesr",
      "anchor_said": "EHsh...",
      "release_notes_url": "https://locksmith.app/releases/1.2.3",
      "is_major": false,
      "is_critical": false
    },
    { "version": "1.2.2", ... },
    { "version": "1.2.1", ... }
  ]
}
```

`appcast/v1/windows.json` has the same schema with Windows-specific values.

### 6.4 Schema field semantics

| Field | Purpose |
|-------|---------|
| `schema_version` | Lets us evolve the appcast format without breaking older clients |
| `publisher_aid` | AID prefix the client embeds; appcast restates it so verifier can fail fast on mismatch |
| `publisher_kel_url` | Where the verifier fetches the publisher KEL summary |
| `anchor_url` | Where the verifier fetches the KEL `ixn` event + witness receipts for this release |
| `anchor_said` | The KERI SAID of the anchored event — verifier confirms downloaded `.cesr` matches before signature checks |
| `is_major` | Drives the silent-vs-prompt update UX |
| `is_critical` | Triggers urgent UI surface + shortened deferral window for security patches |
| `minimum_system_version` | Sparkle/WinSparkle honor this natively |

### 6.5 No appcast-level signature

The appcast itself is **not signed**. Per Approach B-practical, trust flows entirely from the KERI anchor event. An attacker who tampers with `appcast/v1/macos.json` to point at a malicious artifact causes the KERI verifier to abort install when the artifact hash doesn't match the anchored seal. The worst an appcast-tampering attacker can do is denial-of-service (404s, version downgrade attempts that the verifier rejects), not silent compromise.

---

## 7. KERI Publisher AID + KEL Anchoring

### 7.1 Publisher AID identity

A single dedicated AID — `publisher_aid` — owned by the KERI.host entity. Separate from any other AIDs operated by KERI.host (e.g., witness AIDs, blog AID).

Operational characteristics:

- **Multisig: 2-of-3 weighted threshold.** Three signers, each on a separate device:
  1. **Laptop signer** — YubiKey 5 Series with FIDO2 + OpenPGP, signing key in OpenPGP slot
  2. **Desktop signer** — YubiKey 5 Series, same configuration
  3. **Cold backup signer** — Air-gapped USB drive in a fireproof safe; signing key on a non-network device
- 2-of-3 quorum is required to publish a release. Loss of any single device does not require an emergency rotation.
- **Pre-rotated keys** — every KEL event commits to the next signing key set. Standard KERI practice; non-negotiable for cold-stored AIDs.

### 7.2 Witness configuration

Witnesses are the existing `api.keri.host/witness/*` infrastructure (already operated by the user; documented in `~/KERI/code/kerihost`).

- Inception event lists ≥3 witness AIDs (currently the api.keri.host witness pool has its own AID; if there are not yet 3 distinct witness AIDs at api.keri.host, this is a prerequisite to be tracked in the implementation plan).
- `toad` (threshold of accountable duplicity) = 2 — i.e., 2 of 3 witness receipts required for each KEL event.
- Witness OOBIs are written into `publisher_anchor.json` and embedded in the build at build time.

### 7.3 Release anchoring via KEL interaction events

Each release is a single **interaction (`ixn`)** event in the publisher AID's KEL, with the release metadata as the anchored seal. Example KEL progression:

```
sn=0   icp   (inception: publisher_aid created, witnesses=[w1, w2, w3], toad=2)
sn=1   ixn   anchored seal: { release: { v: "1.0.0", artifacts: {...} } }
sn=2   ixn   anchored seal: { release: { v: "1.0.1", artifacts: {...} } }
sn=3   rot   (routine key rotation — 12 months elapsed)
sn=4   ixn   anchored seal: { release: { v: "1.1.0", artifacts: {...} } }
sn=5   ixn   anchored seal: { release: { v: "1.1.1", artifacts: {...}, is_critical: true } }
```

The KEL itself is the audit log of all releases. No separate TEL or registry is required.

### 7.4 Anchored seal schema

The seal anchored in each release `ixn` event:

```json
{
  "release": {
    "v": "1.2.3",
    "channel": "stable",
    "released_at": "2026-05-28T14:30:00Z",
    "is_major": false,
    "is_critical": false,
    "previous_version": "1.2.2",
    "minimum_system_versions": { "macos": "13.0", "windows": "10.0.19041" },
    "artifacts": [
      {
        "platform": "macos",
        "filename": "Locksmith-1.2.3.dmg",
        "sha256": "abc123...",
        "size": 87654321
      },
      {
        "platform": "windows",
        "filename": "Locksmith-1.2.3.msi",
        "sha256": "def456...",
        "size": 92345678
      }
    ],
    "release_notes_said": "EHsh..."
  }
}
```

Both platform artifacts are anchored in **one event** — atomic. Either both ship for a version or neither does.

### 7.5 Signing workflow (`tools/publisher/` CLI)

A small Python CLI that runs on a custodian device, **never in CI**. The CLI is the only software with access to publisher signing keys.

Ceremony for release X.Y.Z:

1. CI uploads candidate metadata to `s3://releases-staging.keri.host/candidates/X.Y.Z/release-candidate.json`
2. **Signer 1 (laptop)** runs:
   ```
   locksmith-publisher sign --version 1.2.3 \
       --candidates-url s3://releases-staging.keri.host/candidates/1.2.3/
   ```
   - Verifies the candidate's artifact SHA256s against actual S3 objects
   - Constructs the `ixn` event
   - Signs with YubiKey
   - Outputs `release-anchor-1.2.3.partial.cesr` (one signature attached)
3. **Signer 2 (desktop or backup)** runs:
   ```
   locksmith-publisher countersign --partial release-anchor-1.2.3.partial.cesr
   ```
   - Verifies the partial, adds second signature
   - Outputs `release-anchor-1.2.3.cesr` (2-of-3 quorum reached)
4. Either signer runs:
   ```
   locksmith-publisher submit --signed release-anchor-1.2.3.cesr
   ```
   - Submits the signed `ixn` event to the publisher AID's witnesses (api.keri.host)
   - Waits for witness receipts (2-of-3)
   - Uploads the final `release-anchor-1.2.3.cesr` (event + receipts) to `s3://releases.keri.host/releases/1.2.3/`
   - Updates `publisher/v1/publisher-aid.json` and pushes the new event to `publisher/v1/kel-events/`
   - Triggers the `publish` CI job (refreshes appcast)

The CLI is small, audited, and lives under `tools/publisher/` so it can be reviewed independently of the application code.

### 7.6 Key rotation

- **Routine:** every 12 months OR after any device replacement, OR after any suspected exposure
- **Emergency:** on confirmed compromise — pre-rotation lets us rotate within hours
- Each rotation publishes a `rot` event in the publisher KEL with witness receipts
- Clients pick up new key state on their next update check by fetching the publisher KEL from the appcast's `publisher_kel_url` and replaying from their embedded KEL hash forward

### 7.7 Bootstrap trust (first install)

The embedded `publisher_anchor.json` in each build contains:

```json
{
  "publisher_aid": "EAbc...XYZ",
  "embedded_kel_hash": "EHsh...",      // SAID of latest KEL event at build time
  "embedded_kel_sn": 17,               // sequence number at build time
  "witness_oobis": [
    "https://api.keri.host/witness/oobi/Bwit1...",
    "https://api.keri.host/witness/oobi/Bwit2...",
    "https://api.keri.host/witness/oobi/Bwit3..."
  ]
}
```

On first update check, the verifier:
1. Fetches `publisher_kel_url` from the appcast
2. Confirms the AID prefix matches `publisher_anchor.json`
3. Replays the KEL from `embedded_kel_sn` forward, validating each event's witness receipts
4. If any event in the chain fails validation, the entire update is rejected
5. If valid, the current key state is accepted and the release `ixn` event signature is verified against it

The very first install's trust in `publisher_anchor.json` is bootstrapped by the OS code signature on the install image — Apple/Microsoft attest "this binary is from KERI.host" and `publisher_anchor.json` is part of that binary.

### 7.8 TOCTOU mitigation

Between Sparkle/WinSparkle's "downloaded" event and "installer launched" event, the staged artifact sits on disk. Approach B-practical's known small risk is a hostile local process swapping the artifact in that window. Mitigations:

- The verifier writes the staged artifact to a per-user, `0700`-permissioned staging directory (Mac: `~/Library/Application Support/Locksmith/staging/`; Win: `%LOCALAPPDATA%\Locksmith\staging\`).
- An exclusive `flock` / `LockFileEx` is held on the staged file for the entire verify → install window.
- Immediately before handing off to the OS installer process, the verifier re-hashes the file and compares to the anchored seal. A second hash mismatch at this point aborts the install.

These three defenses (restricted staging directory, exclusive lock, re-hash before exec) are nested. An attacker would have to defeat all three; a process with that level of local access could already do worse things to the user's machine.

---

## 8. Update Flow UX

### 8.1 Check cadence

- App checks the appcast at launch, with a 30-second delay so launch is never gated on network
- Subsequent background checks every 4 hours while running
- All checks are async, off the UI thread
- Failed checks (network errors, CDN issues) are silent. Manual "Check now" in Settings surfaces the actual error message

### 8.2 Decision tree on a successful check

```
Update available?
├─ No  → silent, no UI
└─ Yes → is_critical?
         ├─ Yes → "Security update ready" banner in main window
         │        Install on quit; deferral capped at 24h
         └─ No  → is_major?
                  ├─ Yes → "What's New" modal next time app gains focus
                  │        Buttons: [Install on Quit] / [Remind Me Tomorrow]
                  │        Dismiss = same as "Remind Me Tomorrow"
                  │        Sliding 24h deferral, capped at 7 days then mandatory prompt
                  └─ No  → silent download + install on next quit
                           Subtle "Locksmith will update on restart" in About / Settings
```

### 8.3 "What's New" modal (major version)

- Native window — no embedded web view, no Electron-feeling DOM rendering
- Shows: version number, hero summary line, 3–5 bullet highlights, "Full release notes" link (opens browser)
- Tone follows the KERI.host voice — anti-hype, calm, factual. No "🚀 amazing new release!" language.
- Two buttons: primary `Install on Quit`, secondary `Remind Me Tomorrow`
- Dismissing (X / Esc) = "Remind Me Tomorrow"

### 8.4 Install-on-quit mechanics

- Triggered when user quits Locksmith (Cmd+Q / File→Exit / window close)
- KERI verifier runs between "user quit" and "installer launched":
  - If verification passes: Sparkle/WinSparkle install flow proceeds; app relaunches into new version
  - If verification fails: install aborted; user sees no install attempt at all on this quit; staging dir is cleaned up

### 8.5 First-launch experience (fresh install)

- No update check on the very first launch — already current
- App writes embedded `publisher_anchor.json` state into its local KERI store
- One-time consent screen: brief explanation that updates are KERI-verified and install on quit. Dismissible. Same content also surfaced in About → Updates.

### 8.6 In-app surfaces

**Settings → Updates tab:**

- Status line:
  - "You're up to date" (green dot)
  - "Update X.Y.Z ready — will install on quit" (blue dot)
  - "Security update X.Y.Z ready" (orange dot, for critical)
  - "Couldn't check for updates" (yellow dot, with last-successful timestamp)
- Toggle: "Check automatically" (default on)
- Button: "Check now"
- Button: "View verification log" — opens the verification history page

**About dialog:**

- Version number prominently
- "Updates: auto" / "Updates: off" status
- Link to release notes URL for current version

**Verification log page (Settings → Updates → "View verification log"):**

```
Version    │ Verified at        │ Status         │ Action
1.2.3      │ 2026-05-28 14:31   │ ✓ Verified     │ [details ►]
1.2.2      │ 2026-05-15 09:12   │ ✓ Verified     │ [details ►]
1.2.1-bad  │ 2026-05-08 11:04   │ ✗ Hash mismatch│ [details ►]
1.2.1      │ 2026-05-08 11:06   │ ✓ Verified     │ [details ►]
1.2.0      │ 2026-05-01 16:22   │ ✓ Verified     │ [details ►]
```

`details` opens a read-only view with the full KERI trace: publisher AID, KEL sequence number, event SAID, witness receipts (which witnesses signed and when), artifact hash, comparison to the seal. Exportable to JSON for support tickets.

This page is **part of the product**, not a debug afterthought. It is the user-visible realization of the "is this update real?" promise.

### 8.7 What users never see

- "App is restarting…" full-screen takeovers
- Version-number splash flashes during update
- Console windows during install (Windows)
- UAC prompts for per-user installs (MSI is per-user-scoped where possible; per-machine installs are an MDM decision deferred to a later version)
- "Allow this developer's app to run" Gatekeeper warnings (Apple notarization handles this)
- "Downgrade detected" warnings during normal operation (rollback is a separate intentional flow, also deferred)

---

## 9. Error Handling & Failure Modes

### 9.1 Network failure during update check

- Symptom: appcast unreachable, witness query timeout, OOBI resolution fails
- Behavior: silent retry on the normal 4-hour cadence
- After 48h with no successful check: yellow dot on Settings → Updates with "Last checked: N days ago"
- Manual "Check now" surfaces the actual error string
- Rationale: KERI verification depends on live witness queries. Offline users defer updates — that's correct.

### 9.2 Verification failure (signature, witness threshold, hash mismatch, replay, superseding)

- Symptom: downloaded artifact's anchored event doesn't verify, or seal hash doesn't match the artifact, or publisher KEL has gone backwards
- Behavior: install aborted, staged artifact deleted, single in-app toast on next focus: "An update was downloaded but couldn't be verified. It's been discarded."
- Verification log records: timestamp, failed verification step, the SAID/event involved
- No automatic retry of the same version
- Never offer "Install anyway." Verification is not optional.

### 9.3 Witness disagreement (key state divergence)

- Symptom: queried witnesses return inconsistent key states for the publisher AID — witness duplicity
- Behavior: install aborted, same UI as 9.2 but with explicit "Witness duplicity detected" log entry
- This is a serious condition implying either compromise or infrastructure incident
- Verification log surfaces enough detail (witness AIDs, the events they disagree on) for a technical user or auditor to independently investigate

### 9.4 Publisher key rotation in flight

- Symptom: embedded `publisher_anchor.json` has older KEL hash than what witnesses currently report
- Behavior: **expected**, not an error. Verifier replays the KEL forward from the embedded hash, validates each rotation event against witness receipts, accepts the current key state.
- Logged at INFO, not WARNING
- Hard-fail only if: a rotation event isn't witnessed, or the new key set isn't consistent with the pre-rotation commitment in the prior event.

### 9.5 Sparkle / WinSparkle internal failure

- Symptom: updater framework crashes, installer can't be applied, relaunch fails
- Behavior: generic "Update couldn't be applied. Please reinstall from releases.keri.host." with link
- Underlying logs in `~/Library/Logs/Locksmith/` (Mac) or `%LOCALAPPDATA%\Locksmith\logs\` (Win) for support analysis

### 9.6 Logging philosophy

- All update-related lines tagged `[update]` plus `[verify]` or `[install]` as appropriate
- Structured (key=value) per the project's [[feedback-testing-automated]] memory rule, so log-driven test automation can assert state
- Three user-visible levels: ERROR (red), WARNING (yellow), INFO (gray). DEBUG is on-disk only.
- **Never** includes private key material or vault contents

---

## 10. Testing Strategy

### 10.1 Tier 1: Unit tests (Python, pytest, every PR)

Fast suite covering pure-logic components:

- `locksmith.update.appcast` — parsing, schema validation, version ordering, channel filtering
- `locksmith.update.verify` — KEL replay, seal hash matching, witness threshold checks, rotation acceptance. Heavy use of golden fixtures.
- `locksmith.update.staging` — TOCTOU defenses, file locking, permission checks
- `tools/publisher/` CLI — multisig ceremony state machine, partial-signature aggregation, error paths

Adversarial unit cases (table-driven):

| Scenario | Expected Result |
|----------|-----------------|
| Tampered binary (hash mismatch) | Reject; log "hash mismatch" |
| Tampered KEL event (signature fails) | Reject; log "signature invalid" |
| Witness threshold not met | Reject; log "insufficient receipts" |
| Stale appcast pointing at superseded release | Reject; log "superseded" |
| Replay of older release as newer | Reject; log "version downgrade" |
| Pre-rotation commitment violated | Reject; log "rotation mismatch" |
| CDN serves 1.0.0 when 1.2.0 is current at witnesses | Reject; log "stale appcast" |

Each adversarial case asserts both that install was aborted AND that the verification log records the specific failure mode.

**Coverage target:** 95%+ line coverage on `locksmith.update.*` and `tools/publisher/`. These are security-critical, low-noise modules.

### 10.2 Tier 2: Integration tests (per-platform CI)

Slower; build full artifacts and run the verifier against them using a real test-only publisher AID against a local witness emulator.

- `tests/integration/test_real_pyinstaller_build.py` — invoke PyInstaller, sign with self-signed cert, run resulting binary's `--verify-update` entry point against fixtures
- `tests/integration/test_full_update_cycle.py` — spawn a v1.0.0 build, publish a v1.0.1 appcast pointing at a v1.0.1 build, drive Sparkle's test harness, assert v1.0.1 binary is the running process after restart
- `tests/integration/test_witness_disagreement.py` — boot two local witness instances with divergent state, point verifier at both, assert duplicity detection fires

Runs on every PR in parallel with unit tests. CI matrix: `macos-latest` + `windows-latest`.

### 10.3 Tier 3: Release dry-run (before every public release)

Manual checklist driven by an automated harness:

1. Build candidate artifacts (X.Y.Z)
2. Run multisig signing ceremony with 2-of-3 devices targeting **staging** (`releases-staging.keri.host`, separate S3 bucket, separate publisher AID, identical verification code)
3. Publish to staging CDN
4. On fresh VMs (one macOS, one Windows, kept around for this purpose), install a prior version of Locksmith pointed at the staging appcast
5. Trigger silent update check, observe install on quit, verify staging publisher AID's KEL appears in the verification log, verify new version runs cleanly
6. Specifically check after update: window position preserved, vault re-opens with same passcode, peer mode reconnects to known peers, plugin state preserved

The dry-run produces a signed checklist artifact attesting "release X.Y.Z passed dry-run on YYYY-MM-DD." This artifact lives alongside the release in S3 for external auditors.

**Gate:** No public release without a passing dry-run on both platforms.

### 10.4 Test fixtures

Fixtures live in `tests/fixtures/update/` and are generated by a committed script `tests/fixtures/update/generate.py` so they are reproducible from scratch. The script uses keripy directly so fixtures are real KERI events, not hand-crafted JSON.

Each fixture set includes:
- Synthetic publisher AID inception event
- A few interaction events (release anchors)
- Corresponding witness receipts
- Matching binary stubs with known hashes

### 10.5 Not tested

- Apple notarization end-to-end — we test that notarization was performed (stapled ticket present) but not Apple's validation
- Azure Trusted Signing internals — we test signature was applied and binary loads on a clean Windows VM
- SmartScreen reputation — nothing to test; accrues passively
- KERI.host non-profit incorporation status — out of scope for the deployment system

---

## 11. Migration Notes

### 11.1 What's currently in the repo that this replaces or evolves

| Existing | What happens |
|----------|--------------|
| `.github/workflows/release.ci.yml` | Rewritten — keeps the existing Apple cert import + notarytool credentials + create-dmg, replaces stubbed build steps with PyInstaller, adds Windows MSI flow, swaps DigitalOcean Spaces upload for S3 |
| `scripts/sign.sh` | Reused and extended for the new PyInstaller `.app` |
| `scripts/signLibs.sh` | Reused unchanged |
| `entitlements.plist` | **Modified — sandbox must be removed.** Sparkle 2.x cannot run inside a sandboxed app (Sparkle writes to `/Applications` and execs helper processes). `com.apple.security.app-sandbox` must be set to `false` (or the key removed). Sandbox is not required for direct-distributed Mac apps — only for Mac App Store, which is out of scope (§2). The hardened runtime is kept (`--options runtime` on `codesign`); JIT, unsigned-executable-memory, dyld-environment-variables, and network entitlements stay. |
| `scripts/upload.py` | Adapted to use S3 endpoint via OIDC role rather than Spaces access keys |
| `APP_ID = com.CHANGEME.locksmith` (placeholder in CI) | Replaced with `host.keri.locksmith` |

### 11.2 What's new and committed in this work

- `packaging/Locksmith.macos.spec` — PyInstaller spec for macOS
- `packaging/Locksmith.windows.spec` — PyInstaller spec for Windows
- `packaging/wix/Locksmith.wxs` — WiX MSI authoring
- `packaging/dmg/background.png` + `layout.json` — DMG visual design
- `src/locksmith/update/` — Python package containing appcast parser, verifier, staging manager, in-app UI surfaces
- `src/locksmith/release/publisher_anchor.json` — embedded trust anchor metadata
- `tools/publisher/` — multisig signing CLI (separate package, not shipped with the app)
- `tests/fixtures/update/` + `generate.py`
- `tests/integration/test_*.py` for the update system
- `infrastructure/` (or extend existing if any) — AWS CDK code for S3 bucket, CloudFront distribution, ACM cert, Route 53 records, IAM role for GitHub OIDC

### 11.3 Prerequisites tracked outside this design

- **Apple Developer ID certificate** — already in CI secrets (`APPLE_DEVELOPER_CERTIFICATE_P12_BASE64`). Verify enrollment is under the entity that will become the KERI.host non-profit; if currently under personal Apple ID, plan a re-enrollment when the non-profit incorporates.
- **Azure Trusted Signing account** — to be created under the KERI.host entity. ~$10/month. CI integration via `Azure/trusted-signing-action`.
- **Custodian hardware** — 2× YubiKey 5 Series (laptop + desktop). Already in user's possession or to be procured.
- **Air-gapped backup signer device** — USB drive in fireproof safe; one-time setup.
- **Witness pool** — `api.keri.host` is live; confirm ≥3 distinct witness AIDs available, or plan to add witnesses to the pool.
- **DNS** — `releases.keri.host` to be added to Route 53 zone for `keri.host`.
- **Bundle ID claim** — `host.keri.locksmith` to be claimed in Apple Developer Program.

---

## 12. Open Questions / TBD

These are items intentionally left for implementation planning, not gaps in the design:

1. **Domain verification for releases.keri.host** — need to confirm Route 53 zone exists for `keri.host` and ACM cert provisioning is automatable via CDK. If not yet, prerequisite step.
2. **Witness count at api.keri.host** — design assumes ≥3 witness AIDs at api.keri.host; verify current count and plan additions if needed.
3. **Sparkle 2 ↔ disabled signature verification configuration** — exact `Info.plist` keys (`SUExpectsDSASignature = NO`, etc.) and Sparkle 2 equivalents to be confirmed during implementation.
4. **WinSparkle equivalent** — WinSparkle's API for disabling signature verification needs implementation-time verification.
5. **Sparkle / WinSparkle installer-hook integration point** — exact lifecycle hook used to invoke our Python verifier between "downloaded" and "install" is platform-specific and will be confirmed during the spike phase.
6. **Existing `root_aid` / `api_aid` naming clarification** — separate concern, but worth a follow-up to consider renaming `root_aid` → `provider_aid` to avoid future confusion with the new `publisher_aid`. Not in scope for this design.
7. **Publish CI job trigger mechanism** — §7.5 step 4 says the publisher CLI's `submit` action "triggers the publish CI job." Implementation choices: (a) CLI calls `gh workflow run` via a fine-scoped PAT, (b) CLI uploads a sentinel file to S3 that an EventBridge rule watches, (c) workflow polls S3 for new signed anchors on a schedule. Implementation plan picks one — leaning (a) for synchronous feedback, but (b) is the more "infrastructure-pure" option.
8. **Critical-release fast path** — §9 covers verification failures but the spec doesn't address how a critical security patch bypasses the normal release dry-run cadence. For v1, we treat critical releases identically to non-critical (full dry-run gate is non-negotiable). If real-world ops show this is too slow, a "critical-release express dry-run" subset will be designed in a follow-up.

---

## 13. Out of Scope (Future Work)

- Linux distribution (AppImage + AppImageUpdate; or Snap/Flatpak)
- Mac App Store + Microsoft Store distribution (requires sandbox + MAS-specific updater path)
- MDM / Group Policy / enterprise configuration profiles
- Beta and nightly release channels
- Per-release ACDC credentials (richer than KEL ixn seals)
- Multi-witness attestation by third parties (community witnesses, board members)
- Delta updates / binary diffs to reduce download size
- Rollback / downgrade as an explicit user flow
- Self-hosted enterprise appcast (private CDN for air-gapped enterprise deployments)
- Per-machine MSI installation with UAC

---

## 14. Acceptance criteria

This design is implemented and ready for first public release when:

1. A user can download `Locksmith.dmg` from `releases.keri.host`, drag to Applications, and launch without seeing any OS warning
2. A user can download `Locksmith.msi` from `releases.keri.host`, double-click, and install without UAC for per-user install
3. Installed app checks for updates silently, downloads them in background, verifies them via KERI, and installs them on quit — without any user action required for minor/patch updates
4. A major version update presents a polished "What's New" modal that lets the user choose Install or Remind Tomorrow
5. The Settings → Updates → Verification log shows a real KERI verification trace for every update the user has applied
6. The release dry-run process passes on both macOS and Windows
7. An independent auditor can replay the publisher KEL from witnesses on `api.keri.host` and verify every release matches the artifacts served by `releases.keri.host`

---

**Related memory:** [[user-identity-and-fork]], [[project-keri-host-publisher-entity]], [[project-aws-infrastructure]], [[feedback-ux-first-deployment]], [[feedback-testing-automated]], [[reference-mailbox-keri-host]]
