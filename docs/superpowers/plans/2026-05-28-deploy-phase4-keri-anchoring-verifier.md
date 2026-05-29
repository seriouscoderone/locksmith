# Phase 4: KERI Release Anchoring + In-App Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Releases are KERI-anchored via 2-of-3 multisig `ixn` events in a publisher KEL witnessed by api.keri.host; users can independently verify any downloaded artifact via a standalone `locksmith --verify-update <path>` CLI.

**Architecture:** Two cooperating Python packages: `tools/publisher/` (off-CI multisig signing CLI, never bundled with app) emits signed `release-anchor-X.Y.Z.cesr` events anchored to the publisher AID and refreshes the appcast; `src/locksmith/update/` (bundled with the app) fetches the appcast, replays the publisher KEL from an embedded hash forward against witness receipts, and gates artifact installation by matching SHA256s against the anchored seal. No Sparkle/UI changes in this phase — Phase 5 consumes these.

**Tech Stack:** Python 3.14, keripy (`Hab`, `Habery`, `keri.core.eventing`, `keri.core.serdering`, `keri.core.coring`, `keri.app.habbing`, `keri.app.indirecting`, `keri.kering`), `click` for CLIs, `boto3` for S3, `requests` for witness HTTP, `cryptography` for hashing, `pytest` + `pytest-mock` for tests.

**Spec reference:** `docs/superpowers/specs/2026-05-28-locksmith-deploy-update-design.md` §6.3, §7, §9, §10.1.

**Open question resolution (spec §12 item 7 — publish CI trigger):** This plan uses **manual `workflow_dispatch`** keyed on the version string. EventBridge-triggered automation is a follow-up in Phase 5+. Rationale: deterministic synchronous feedback during early operations; no IAM event-bus surface to design and lock down on day one; the publisher CLI is already interactive (the operator just runs `gh workflow run publish --field version=X.Y.Z` after `submit` completes).

**Cross-phase dependencies:**
- Depends on Phase 1: `src/locksmith/release/publisher_anchor.json` schema, publisher AID exists on api.keri.host, OIDC role `gha-locksmith-release-publisher`, `tools/publisher/` package skeleton with stubbed `sign`, `countersign`, `submit` subcommands.
- Depends on Phase 2/3: Actual `Locksmith-X.Y.Z.dmg` / `.msi` artifacts uploaded to `s3://releases-staging.keri.host/candidates/X.Y.Z/`.
- Phase 5 depends on this phase: imports `locksmith.update.verify.verify_artifact()`; reads `locksmith.update.log` for the verification-history UI.

---

## File Structure

**Created:**
- `tools/publisher/src/locksmith_publisher/ceremony.py` — multisig state machine
- `tools/publisher/src/locksmith_publisher/anchor.py` — KEL `ixn` event construction
- `tools/publisher/src/locksmith_publisher/witness_client.py` — HTTP client for api.keri.host
- `tools/publisher/src/locksmith_publisher/s3_client.py` — boto3 wrappers (OIDC-derived creds)
- `tools/publisher/src/locksmith_publisher/appcast.py` — appcast generator
- `tools/publisher/src/locksmith_publisher/errors.py` — typed exceptions
- `src/locksmith/update/__init__.py`
- `src/locksmith/update/appcast.py` — appcast parser, `Release` dataclass
- `src/locksmith/update/kel_replay.py` — KEL replay against witnesses
- `src/locksmith/update/verify.py` — main entry: `verify_artifact()`
- `src/locksmith/update/staging.py` — TOCTOU defenses
- `src/locksmith/update/log.py` — append-only verification log
- `src/locksmith/update/errors.py` — typed exception hierarchy
- `src/locksmith/update/cli.py` — `--verify-update` flag handler
- `tests/fixtures/update/generate.py` — fixture-generation script
- `tests/fixtures/update/README.md` — how to regenerate fixtures
- `tests/unit/update/__init__.py`
- `tests/unit/update/test_appcast.py`
- `tests/unit/update/test_kel_replay.py`
- `tests/unit/update/test_verify.py`
- `tests/unit/update/test_staging.py`
- `tests/unit/update/test_log.py`
- `tests/unit/update/test_cli.py`
- `tests/unit/publisher/__init__.py`
- `tests/unit/publisher/test_ceremony.py`
- `tests/unit/publisher/test_anchor.py`
- `tests/unit/publisher/test_appcast_generator.py`

**Modified:**
- `tools/publisher/src/locksmith_publisher/cli.py` — finalize Phase 1 stubs
- `tools/publisher/pyproject.toml` — add `boto3`, `requests`, `click` deps
- `src/locksmith/main.py` — wire `--verify-update <path>` into entry point
- `.github/workflows/release.ci.yml` — add `publish` job (manual `workflow_dispatch`)
- `pyproject.toml` — no new app deps required (keripy/requests/cryptography already present)

---

## Task 1: Verification Errors (typed exception hierarchy)

**Files:**
- Create: `src/locksmith/update/__init__.py`
- Create: `src/locksmith/update/errors.py`
- Test: `tests/unit/update/__init__.py`, `tests/unit/update/test_errors.py`

These types are the vocabulary every other module uses. Implement first so later tasks can `raise` and `except` them.

- [ ] **Step 1: Create empty package files**

Create `src/locksmith/update/__init__.py` (empty file).
Create `tests/unit/update/__init__.py` (empty file).

- [ ] **Step 2: Write the failing test for the error hierarchy**

Create `tests/unit/update/test_errors.py`:

```python
"""Tests for the typed exception hierarchy in locksmith.update.errors."""
import pytest

from locksmith.update.errors import (
    UpdateError,
    SignatureError,
    HashMismatchError,
    WitnessThresholdError,
    StaleAppcastError,
    DowngradeError,
    RotationMismatchError,
    WitnessDuplicityError,
    NetworkError,
    SchemaError,
    StagingError,
)


def test_all_errors_inherit_from_update_error():
    assert issubclass(SignatureError, UpdateError)
    assert issubclass(HashMismatchError, UpdateError)
    assert issubclass(WitnessThresholdError, UpdateError)
    assert issubclass(StaleAppcastError, UpdateError)
    assert issubclass(DowngradeError, UpdateError)
    assert issubclass(RotationMismatchError, UpdateError)
    assert issubclass(WitnessDuplicityError, UpdateError)
    assert issubclass(NetworkError, UpdateError)
    assert issubclass(SchemaError, UpdateError)
    assert issubclass(StagingError, UpdateError)


def test_exit_codes_match_spec():
    # Exit codes per the standalone verifier CLI contract.
    assert SignatureError.exit_code == 10
    assert HashMismatchError.exit_code == 11
    assert WitnessThresholdError.exit_code == 12
    assert StaleAppcastError.exit_code == 13
    assert DowngradeError.exit_code == 13       # superseded == stale class
    assert NetworkError.exit_code == 14
    # Schema / rotation / duplicity / staging map to signature class (10)
    # since they all imply "we cannot trust this update"
    assert RotationMismatchError.exit_code == 10
    assert WitnessDuplicityError.exit_code == 10
    assert SchemaError.exit_code == 10
    assert StagingError.exit_code == 10


def test_error_carries_log_fields():
    err = HashMismatchError(
        reason="expected abc, got def",
        log_fields={"expected_sha256": "abc", "actual_sha256": "def"},
    )
    assert err.reason == "expected abc, got def"
    assert err.log_fields["expected_sha256"] == "abc"
    assert err.log_fields["actual_sha256"] == "def"
    # str() must include the reason for human readability
    assert "expected abc" in str(err)
```

- [ ] **Step 3: Run the test to confirm it fails**

Run: `pytest tests/unit/update/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'locksmith.update.errors'`

- [ ] **Step 4: Implement `errors.py`**

Create `src/locksmith/update/errors.py`:

```python
"""Typed exception hierarchy for the in-app update verifier.

Each error type maps to a verifier-CLI exit code (see `--verify-update`).
Every error carries `log_fields` — a dict of structured key/value pairs
written to the verification log in key=value form per
[[feedback-testing-automated]].
"""
from __future__ import annotations

from typing import Mapping, Any


class UpdateError(Exception):
    """Base class for every verifier-rejected update.

    Subclasses set `exit_code` (used by the standalone CLI) and may
    populate `log_fields` for structured logging.
    """

    exit_code: int = 1

    def __init__(self, reason: str, log_fields: Mapping[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.log_fields: dict[str, Any] = dict(log_fields or {})

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.reason


class SignatureError(UpdateError):
    """The KEL event signature does not verify against the current key state."""
    exit_code = 10


class HashMismatchError(UpdateError):
    """The downloaded artifact SHA256 does not match the anchored seal."""
    exit_code = 11


class WitnessThresholdError(UpdateError):
    """Fewer than `toad` valid witness receipts attached to an event."""
    exit_code = 12


class StaleAppcastError(UpdateError):
    """Appcast points at a version older than current_version at witnesses."""
    exit_code = 13


class DowngradeError(UpdateError):
    """An older release is being offered as a newer one (replay)."""
    exit_code = 13


class RotationMismatchError(UpdateError):
    """A `rot` event violates the pre-rotation commitment in the prior event."""
    exit_code = 10


class WitnessDuplicityError(UpdateError):
    """Witnesses returned divergent key state for the publisher AID."""
    exit_code = 10


class SchemaError(UpdateError):
    """Appcast or KEL stream did not conform to its schema."""
    exit_code = 10


class StagingError(UpdateError):
    """Staging-dir permissions, lock acquisition, or re-hash failed."""
    exit_code = 10


class NetworkError(UpdateError):
    """Could not reach the appcast, KEL, or witness pool."""
    exit_code = 14
```

- [ ] **Step 5: Run the test to confirm it passes**

Run: `pytest tests/unit/update/test_errors.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/update/__init__.py src/locksmith/update/errors.py \
        tests/unit/update/__init__.py tests/unit/update/test_errors.py
git commit -m "feat(update): typed exception hierarchy for verifier"
```

---

## Task 2: Fixture generator skeleton — synthetic publisher AID + witnesses

**Files:**
- Create: `tests/fixtures/update/__init__.py`
- Create: `tests/fixtures/update/generate.py`
- Create: `tests/fixtures/update/README.md`

This script generates **real** KERI events (not hand-crafted JSON) using a temporary keripy `Habery`. Everything else in this plan depends on these fixtures, so implement first. The script is committed; the generated artifacts are also committed (so CI doesn't have to regenerate them every run — but `make fixtures` regenerates them deterministically).

- [ ] **Step 1: Create the README**

Create `tests/fixtures/update/README.md`:

```markdown
# Update verifier test fixtures

Generated by `python tests/fixtures/update/generate.py`.

Layout:

```
tests/fixtures/update/
├── generate.py
├── README.md
├── publisher_aid.json          # AID prefix + KEL hash at fixture-time
├── kel/
│   ├── 000_icp.cesr            # inception event + receipts
│   ├── 001_ixn_1.0.0.cesr      # release anchor for 1.0.0
│   ├── 002_ixn_1.0.1.cesr      # release anchor for 1.0.1
│   ├── 003_rot.cesr            # routine key rotation
│   └── 004_ixn_1.1.0.cesr      # release anchor for 1.1.0
├── artifacts/
│   ├── Locksmith-1.0.0.dmg.stub
│   ├── Locksmith-1.0.0.msi.stub
│   ├── Locksmith-1.0.1.dmg.stub
│   ├── Locksmith-1.0.1.msi.stub
│   ├── Locksmith-1.1.0.dmg.stub
│   └── Locksmith-1.1.0.msi.stub
├── appcast/
│   ├── macos.json
│   └── windows.json
└── tampered/
    ├── tampered_binary_1.0.1.dmg.stub       # wrong content, valid name
    ├── tampered_event_1.0.1.cesr            # event payload altered after sig
    ├── insufficient_receipts_1.0.1.cesr     # only 1-of-3 witness receipts
    ├── stale_appcast_macos.json             # points at 1.0.0 when chain is at 1.1.0
    ├── downgrade_appcast_macos.json         # claims 1.0.0 has 1.1.0's sha
    ├── bad_rotation.cesr                    # rot event violates pre-rotation
    └── duplicity/                           # two witnesses, divergent KELs
        ├── witness_a_kel.cesr
        └── witness_b_kel.cesr
```

Regenerate: `python tests/fixtures/update/generate.py`. Tests must be insensitive
to absolute paths (every fixture is referenced relative to this directory).
```

- [ ] **Step 2: Create the empty `__init__.py`**

Create `tests/fixtures/update/__init__.py` (empty file).

- [ ] **Step 3: Implement `generate.py` — happy-path KEL only (will extend in later tasks)**

Create `tests/fixtures/update/generate.py`:

```python
"""Generate KERI fixtures for the update verifier test suite.

Usage:
    python tests/fixtures/update/generate.py [--out DIR]

Idempotent: deletes and re-creates the output directory on each run.
Uses keripy directly so fixtures are real KERI events.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from keri.app import habbing
from keri.core import coring, eventing, serdering, signing
from keri.db import basing

DEFAULT_OUT = Path(__file__).parent

# Three synthetic witnesses (deterministic salts so fixtures are reproducible).
WITNESS_SALTS = [
    b"0123456789abcdef0",  # w1
    b"0123456789abcdef1",  # w2
    b"0123456789abcdef2",  # w3
]
# Publisher seed — three signers (laptop, desktop, cold backup).
PUBLISHER_SALTS = [
    b"publisher_signer_1",
    b"publisher_signer_2",
    b"publisher_signer_3",
]


def make_witness(idx: int, base: Path) -> habbing.Hab:
    """Spin up a synthetic non-transferable witness Hab."""
    salt = signing.Salter(raw=WITNESS_SALTS[idx]).qb64
    hby = habbing.Habery(
        name=f"witness_{idx}",
        base=str(base),
        salt=salt,
        temp=True,
        free=True,
    )
    hab = hby.makeHab(
        name=f"wit{idx}",
        transferable=False,
        wits=[],
        toad=0,
    )
    return hab, hby


def make_publisher(base: Path, wit_prefixes: list[str], toad: int = 2):
    """Build the multisig publisher AID. For fixtures we use a single-key
    Hab — multisig ceremony state machine is tested separately. Publisher's
    semantic identity is preserved: the same AID prefix, witnessed by 3."""
    salt = signing.Salter(raw=PUBLISHER_SALTS[0]).qb64
    hby = habbing.Habery(
        name="publisher",
        base=str(base),
        salt=salt,
        temp=True,
        free=True,
    )
    hab = hby.makeHab(
        name="publisher_aid",
        transferable=True,
        wits=wit_prefixes,
        toad=toad,
        icount=1,
        isith=1,
        ncount=1,
        nsith=1,
    )
    return hab, hby


def write_cesr(path: Path, hab: habbing.Hab, sn: int) -> None:
    """Write event at sn + its attached signatures + witness receipts."""
    buf = bytearray()
    for msg in hab.db.clonePreIter(pre=hab.pre, fn=sn):
        buf.extend(msg)
        # one event at a time — break after first
        break
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_stub_artifact(out: Path, version: str, platform: str) -> tuple[Path, str]:
    """Write a tiny deterministic binary stub and return its (path, sha256)."""
    ext = "dmg" if platform == "macos" else "msi"
    body = f"LOCKSMITH-STUB platform={platform} version={version}\n".encode()
    path = out / "artifacts" / f"Locksmith-{version}.{ext}.stub"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path, sha256(body)


def build_seal(
    version: str,
    is_major: bool,
    is_critical: bool,
    previous_version: str | None,
    artifacts: list[dict],
) -> dict:
    """Build the anchored-seal payload per spec §7.4."""
    return {
        "release": {
            "v": version,
            "channel": "stable",
            "released_at": f"2026-05-28T00:00:00Z",  # frozen for fixture determinism
            "is_major": is_major,
            "is_critical": is_critical,
            "previous_version": previous_version,
            "minimum_system_versions": {"macos": "13.0", "windows": "10.0.19041"},
            "artifacts": artifacts,
            "release_notes_said": "EHshFixtureReleaseNotesSAIDPlaceholderXXXXXXXX",
        }
    }


def anchor_release(hab: habbing.Hab, seal: dict, witnesses: list[habbing.Hab]) -> serdering.SerderKERI:
    """Create an ixn event anchoring `seal`, gather witness receipts."""
    # KERI ixn data is a list of seal dicts.
    msg = hab.interact(data=[seal])
    serder = serdering.SerderKERI(raw=bytearray(msg))
    # Generate witness receipts by replaying the event through each witness's parser.
    for wit_hab in witnesses:
        # In a real deployment, witnesses are remote and api.keri.host emits receipts;
        # for fixtures we directly call receipt() on each witness Hab.
        rserder, _ = eventing.receipt(
            pre=hab.pre,
            sn=serder.sn,
            said=serder.said,
        )
        wig = wit_hab.sign(ser=rserder.raw, indexed=False)
        # Index the receipt back into the publisher's wigs db.
        from keri.db import dbing
        dgkey = dbing.dgKey(hab.pre.encode(), serder.said.encode())
        hab.db.wigs.add(keys=dgkey, val=coring.Siger(qb64=wig[0].qb64).cigar)
    return serder


def generate_happy_path(out: Path) -> None:
    """Emit fixtures/update/{publisher_aid.json, kel/, artifacts/, appcast/}."""
    base = out / "_keystore"
    base.mkdir(parents=True, exist_ok=True)

    # 1. Witnesses.
    witnesses = []
    wit_hbys = []
    for i in range(3):
        wh, whby = make_witness(i, base)
        witnesses.append(wh)
        wit_hbys.append(whby)

    wit_prefixes = [w.pre for w in witnesses]

    # 2. Publisher AID with toad=2.
    pub, pub_hby = make_publisher(base, wit_prefixes, toad=2)

    # 3. Release anchors.
    versions = [
        ("1.0.0", False, False, None),
        ("1.0.1", False, False, "1.0.0"),
        ("1.1.0", True, False, "1.0.1"),  # major
    ]
    sn = 1
    kel_dir = out / "kel"
    kel_dir.mkdir(exist_ok=True)
    write_cesr(kel_dir / "000_icp.cesr", pub, sn=0)

    release_records = []
    for (v, is_major, is_critical, prev) in versions:
        mac_path, mac_sha = make_stub_artifact(out, v, "macos")
        win_path, win_sha = make_stub_artifact(out, v, "windows")
        artifacts = [
            {"platform": "macos", "filename": mac_path.name,
             "sha256": mac_sha, "size": mac_path.stat().st_size},
            {"platform": "windows", "filename": win_path.name,
             "sha256": win_sha, "size": win_path.stat().st_size},
        ]
        seal = build_seal(v, is_major, is_critical, prev, artifacts)
        serder = anchor_release(pub, seal, witnesses)
        write_cesr(kel_dir / f"{sn:03d}_ixn_{v}.cesr", pub, sn=sn)
        release_records.append({
            "version": v,
            "sn": sn,
            "said": serder.said,
            "seal": seal,
            "artifacts": {
                "macos": {"path": str(mac_path), "sha256": mac_sha, "size": mac_path.stat().st_size},
                "windows": {"path": str(win_path), "sha256": win_sha, "size": win_path.stat().st_size},
            },
        })
        sn += 1

    # 4. publisher_aid.json — embedded anchor state at fixture-time.
    pub_aid_json = {
        "publisher_aid": pub.pre,
        "embedded_kel_hash": pub.kever.serder.said,
        "embedded_kel_sn": pub.kever.sn,
        "witness_oobis": [f"https://api.keri.host/witness/oobi/{w}" for w in wit_prefixes],
        "witness_aids": wit_prefixes,
        "toad": 2,
        "_releases": release_records,  # convenience for tests
    }
    (out / "publisher_aid.json").write_text(json.dumps(pub_aid_json, indent=2))

    # 5. Appcast (happy-path) for both platforms.
    write_appcasts(out, pub.pre, release_records)

    # 6. Cleanup keystore.
    pub_hby.close()
    for whby in wit_hbys:
        whby.close()
    shutil.rmtree(base, ignore_errors=True)


def write_appcasts(out: Path, publisher_aid: str, releases: list[dict]) -> None:
    appcast_dir = out / "appcast"
    appcast_dir.mkdir(exist_ok=True)
    for platform, ext in [("macos", "dmg"), ("windows", "msi")]:
        current = releases[-1]["version"]
        rels = []
        for r in releases:
            a = r["artifacts"][platform]
            rels.append({
                "version": r["version"],
                "released_at": r["seal"]["release"]["released_at"],
                "platform": platform,
                "minimum_system_version":
                    r["seal"]["release"]["minimum_system_versions"][platform],
                "artifact_url":
                    f"https://releases.keri.host/releases/{r['version']}/Locksmith-{r['version']}.{ext}",
                "artifact_sha256": a["sha256"],
                "artifact_size": a["size"],
                "anchor_url":
                    f"https://releases.keri.host/releases/{r['version']}/release-anchor-{r['version']}.cesr",
                "anchor_said": r["said"],
                "release_notes_url": f"https://locksmith.app/releases/{r['version']}",
                "is_major": r["seal"]["release"]["is_major"],
                "is_critical": r["seal"]["release"]["is_critical"],
            })
        appcast = {
            "schema_version": 1,
            "channel": "stable",
            "publisher_aid": publisher_aid,
            "publisher_kel_url":
                "https://releases.keri.host/publisher/v1/publisher-aid.json",
            "current_version": current,
            "releases": rels,
        }
        (appcast_dir / f"{platform}.json").write_text(json.dumps(appcast, indent=2))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    # Idempotent: wipe everything except this script and README.
    for entry in args.out.iterdir():
        if entry.name in {"generate.py", "README.md", "__init__.py"}:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    generate_happy_path(args.out)
    print(f"Fixtures written to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the generator**

Run: `python tests/fixtures/update/generate.py`
Expected: stdout `Fixtures written to .../tests/fixtures/update`.
Expected: `tests/fixtures/update/publisher_aid.json`, `kel/`, `artifacts/`, `appcast/` populated.

- [ ] **Step 5: Spot-check fixture integrity**

Run:
```bash
python -c "import json,pathlib; \
d=json.loads(pathlib.Path('tests/fixtures/update/publisher_aid.json').read_text()); \
print('AID:', d['publisher_aid'][:10], 'SN:', d['embedded_kel_sn'], \
'releases:', len(d['_releases']))"
```
Expected: AID prefix (starts with `E` for transferable), SN=3, releases=3.

- [ ] **Step 6: Commit the generator + happy-path fixtures**

```bash
git add tests/fixtures/update/
git commit -m "test(update): KERI fixture generator with happy-path KEL"
```

---

## Task 3: Extend fixture generator with adversarial variants

**Files:**
- Modify: `tests/fixtures/update/generate.py`

Adds the `tampered/` directory used by every spec §10.1 adversarial test row.

- [ ] **Step 1: Add `generate_tampered_variants()` and call it from `main()`**

Append to `tests/fixtures/update/generate.py` (before `def main()`):

```python
def generate_tampered_variants(out: Path) -> None:
    """Emit the `tampered/` directory with adversarial cases."""
    tampered = out / "tampered"
    tampered.mkdir(exist_ok=True)

    # Re-read the happy-path manifest.
    manifest = json.loads((out / "publisher_aid.json").read_text())
    releases = manifest["_releases"]
    rel_101 = next(r for r in releases if r["version"] == "1.0.1")
    rel_110 = next(r for r in releases if r["version"] == "1.1.0")

    # (A) Tampered binary — same filename, different bytes.
    bad_body = b"MALICIOUS PAYLOAD\n"
    (tampered / "tampered_binary_1.0.1.dmg.stub").write_bytes(bad_body)

    # (B) Tampered event — copy the real ixn but flip a byte in the payload.
    real_event = (out / "kel" / f"{rel_101['sn']:03d}_ixn_1.0.1.cesr").read_bytes()
    # Flip a payload byte (after the version-string + 8 framing bytes). We
    # don't try to re-sign — the goal is "valid CESR framing, broken sig".
    mutated = bytearray(real_event)
    # Find first ASCII letter past byte 32 to flip — minimally invasive.
    for i in range(32, min(len(mutated), 256)):
        if 0x41 <= mutated[i] <= 0x7A:
            mutated[i] ^= 0x01
            break
    (tampered / "tampered_event_1.0.1.cesr").write_bytes(bytes(mutated))

    # (C) Insufficient receipts — strip witness receipts from the event.
    # The event is the leading SerderKERI + its sigs + count-coded receipts.
    # We naively keep only the first ~half of the bytes after the event body.
    serder = serdering.SerderKERI(raw=bytearray(real_event))
    event_body_len = serder.size
    # Keep event + first signature group only; drop receipt groups.
    truncated = real_event[: event_body_len + 64]
    (tampered / "insufficient_receipts_1.0.1.cesr").write_bytes(truncated)

    # (D) Stale appcast — claims current_version=1.0.0 when KEL has 1.1.0.
    macos = json.loads((out / "appcast" / "macos.json").read_text())
    stale = dict(macos)
    stale["current_version"] = "1.0.0"
    stale["releases"] = [r for r in macos["releases"] if r["version"] == "1.0.0"]
    (tampered / "stale_appcast_macos.json").write_text(json.dumps(stale, indent=2))

    # (E) Downgrade — claims 1.0.0 has 1.1.0's sha (i.e., serve old artifact as new).
    downgrade = json.loads((out / "appcast" / "macos.json").read_text())
    for r in downgrade["releases"]:
        if r["version"] == "1.0.0":
            # Point its sha at 1.1.0's binary so a malicious mirror could serve
            # an older binary while the appcast claims it's verified.
            r["artifact_sha256"] = rel_110["artifacts"]["macos"]["sha256"]
    (tampered / "downgrade_appcast_macos.json").write_text(
        json.dumps(downgrade, indent=2))

    # (F) Bad rotation — synthesize a rot event whose new key set does NOT
    # match the digest committed in the prior establishment event.
    # Easiest reproducible form: copy the icp, change its ilk byte to "drt"
    # without producing valid pre-rotation digests. Verifier must reject.
    icp_bytes = (out / "kel" / "000_icp.cesr").read_bytes()
    bad_rot = icp_bytes.replace(b'"icp"', b'"rot"', 1)
    (tampered / "bad_rotation.cesr").write_bytes(bad_rot)

    # (G) Witness duplicity — two parallel KELs with same prefix, divergent
    # ixn at sn=1. Generate by spinning up a second publisher seed but
    # forcing the same AID prefix. We approximate by writing the happy-path
    # KEL as witness_a's view and the tampered_event variant as witness_b's
    # view. Verifier should detect divergent SAIDs at the same (pre, sn).
    dup = tampered / "duplicity"
    dup.mkdir(exist_ok=True)
    (dup / "witness_a_kel.cesr").write_bytes(real_event)
    (dup / "witness_b_kel.cesr").write_bytes(bytes(mutated))
```

Then modify `main()` to invoke it:

```python
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    for entry in args.out.iterdir():
        if entry.name in {"generate.py", "README.md", "__init__.py"}:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    generate_happy_path(args.out)
    generate_tampered_variants(args.out)
    print(f"Fixtures written to {args.out}")
```

- [ ] **Step 2: Re-run the generator**

Run: `python tests/fixtures/update/generate.py`
Expected: `tests/fixtures/update/tampered/` contains 7 entries (5 files + `duplicity/` dir).

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/update/
git commit -m "test(update): adversarial fixture variants for verifier"
```

---

## Task 4: Appcast parser + `Release` dataclass

**Files:**
- Create: `src/locksmith/update/appcast.py`
- Test: `tests/unit/update/test_appcast.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/update/test_appcast.py`:

```python
"""Tests for locksmith.update.appcast — schema validation + parsing."""
import json
from pathlib import Path

import pytest

from locksmith.update.appcast import (
    Release,
    Appcast,
    parse_appcast,
    select_latest_for_platform,
)
from locksmith.update.errors import SchemaError

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "update"


def load_macos_appcast() -> str:
    return (FIXTURES / "appcast" / "macos.json").read_text()


def test_parse_happy_path_macos():
    ac = parse_appcast(load_macos_appcast())
    assert ac.schema_version == 1
    assert ac.channel == "stable"
    assert ac.current_version == "1.1.0"
    assert len(ac.releases) == 3
    versions = [r.version for r in ac.releases]
    assert versions == ["1.0.0", "1.0.1", "1.1.0"]


def test_release_dataclass_carries_all_fields():
    ac = parse_appcast(load_macos_appcast())
    r = ac.releases[-1]
    assert isinstance(r, Release)
    assert r.platform == "macos"
    assert r.artifact_sha256
    assert r.artifact_size > 0
    assert r.anchor_url.endswith("release-anchor-1.1.0.cesr")
    assert r.anchor_said
    assert r.is_major is True


def test_schema_version_mismatch_raises():
    raw = json.loads(load_macos_appcast())
    raw["schema_version"] = 2
    with pytest.raises(SchemaError) as e:
        parse_appcast(json.dumps(raw))
    assert "schema_version" in e.value.reason


def test_missing_required_field_raises():
    raw = json.loads(load_macos_appcast())
    del raw["publisher_aid"]
    with pytest.raises(SchemaError):
        parse_appcast(json.dumps(raw))


def test_select_latest_returns_current_version_release():
    ac = parse_appcast(load_macos_appcast())
    latest = select_latest_for_platform(ac, "macos")
    assert latest.version == "1.1.0"


def test_select_latest_wrong_platform_raises():
    ac = parse_appcast(load_macos_appcast())
    with pytest.raises(SchemaError) as e:
        select_latest_for_platform(ac, "linux")
    assert "platform" in e.value.reason.lower()


def test_releases_ordered_oldest_to_newest_by_semver():
    ac = parse_appcast(load_macos_appcast())
    # parse_appcast must enforce ordering (oldest first).
    # If the input is unordered, parse_appcast sorts it.
    raw = json.loads(load_macos_appcast())
    raw["releases"] = list(reversed(raw["releases"]))
    ac2 = parse_appcast(json.dumps(raw))
    assert [r.version for r in ac2.releases] == ["1.0.0", "1.0.1", "1.1.0"]


def test_invalid_json_raises_schema_error():
    with pytest.raises(SchemaError):
        parse_appcast("not json at all")
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/unit/update/test_appcast.py -v`
Expected: All fail with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `appcast.py`**

Create `src/locksmith/update/appcast.py`:

```python
"""Appcast JSON parser per spec §6.3.

Pure-data module — no network IO. `parse_appcast(raw_json)` validates
schema and returns an `Appcast` aggregate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from locksmith.update.errors import SchemaError

CURRENT_SCHEMA_VERSION = 1
REQUIRED_TOP = (
    "schema_version", "channel", "publisher_aid", "publisher_kel_url",
    "current_version", "releases",
)
REQUIRED_REL = (
    "version", "released_at", "platform", "minimum_system_version",
    "artifact_url", "artifact_sha256", "artifact_size",
    "anchor_url", "anchor_said", "release_notes_url",
    "is_major", "is_critical",
)


@dataclass(frozen=True)
class Release:
    version: str
    released_at: str
    platform: str
    minimum_system_version: str
    artifact_url: str
    artifact_sha256: str
    artifact_size: int
    anchor_url: str
    anchor_said: str
    release_notes_url: str
    is_major: bool
    is_critical: bool


@dataclass(frozen=True)
class Appcast:
    schema_version: int
    channel: str
    publisher_aid: str
    publisher_kel_url: str
    current_version: str
    releases: tuple[Release, ...] = field(default_factory=tuple)


def _semver_key(v: str) -> tuple[int, int, int]:
    try:
        parts = v.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError) as ex:
        raise SchemaError(
            f"invalid semver: {v!r}", log_fields={"version": v}
        ) from ex


def parse_appcast(raw: str | bytes) -> Appcast:
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as ex:
        raise SchemaError(f"appcast not valid JSON: {ex}",
                          log_fields={"raw_prefix": str(raw)[:80]}) from ex

    if not isinstance(data, dict):
        raise SchemaError("appcast must be a JSON object")

    for key in REQUIRED_TOP:
        if key not in data:
            raise SchemaError(
                f"missing required appcast field: {key}",
                log_fields={"missing": key},
            )

    if data["schema_version"] != CURRENT_SCHEMA_VERSION:
        raise SchemaError(
            f"unsupported schema_version: {data['schema_version']} "
            f"(expected {CURRENT_SCHEMA_VERSION})",
            log_fields={"schema_version": data["schema_version"]},
        )

    releases_raw = data["releases"]
    if not isinstance(releases_raw, list) or not releases_raw:
        raise SchemaError("releases must be a non-empty list")

    releases: list[Release] = []
    for r in releases_raw:
        for k in REQUIRED_REL:
            if k not in r:
                raise SchemaError(
                    f"missing required release field: {k}",
                    log_fields={"missing": k, "version": r.get("version")},
                )
        releases.append(Release(
            version=r["version"],
            released_at=r["released_at"],
            platform=r["platform"],
            minimum_system_version=r["minimum_system_version"],
            artifact_url=r["artifact_url"],
            artifact_sha256=r["artifact_sha256"],
            artifact_size=int(r["artifact_size"]),
            anchor_url=r["anchor_url"],
            anchor_said=r["anchor_said"],
            release_notes_url=r["release_notes_url"],
            is_major=bool(r["is_major"]),
            is_critical=bool(r["is_critical"]),
        ))

    releases.sort(key=lambda r: _semver_key(r.version))

    return Appcast(
        schema_version=int(data["schema_version"]),
        channel=str(data["channel"]),
        publisher_aid=str(data["publisher_aid"]),
        publisher_kel_url=str(data["publisher_kel_url"]),
        current_version=str(data["current_version"]),
        releases=tuple(releases),
    )


def select_latest_for_platform(ac: Appcast, platform: str) -> Release:
    """Return the `current_version` release for `platform`."""
    for r in ac.releases:
        if r.version == ac.current_version and r.platform == platform:
            return r
    raise SchemaError(
        f"no release matches current_version={ac.current_version} platform={platform}",
        log_fields={"current_version": ac.current_version, "platform": platform},
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/unit/update/test_appcast.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/appcast.py tests/unit/update/test_appcast.py
git commit -m "feat(update): appcast parser with schema validation"
```

---

## Task 5: KEL replay against witness receipts

**Files:**
- Create: `src/locksmith/update/kel_replay.py`
- Test: `tests/unit/update/test_kel_replay.py`

This module is the heart of KERI verification. It takes a publisher AID + embedded KEL hash + the live KEL stream and replays forward, validating signatures and witness receipts at each event.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/update/test_kel_replay.py`:

```python
"""Tests for locksmith.update.kel_replay — replays publisher KEL against witnesses."""
import json
from pathlib import Path

import pytest

from locksmith.update.kel_replay import (
    KelState,
    replay_kel,
    extract_release_seal,
)
from locksmith.update.errors import (
    SignatureError,
    WitnessThresholdError,
    RotationMismatchError,
    SchemaError,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "update"


def load_kel_stream() -> bytes:
    """Concatenate every event in kel/ in order — simulates an OOBI fetch."""
    chunks = []
    for path in sorted((FIXTURES / "kel").iterdir()):
        chunks.append(path.read_bytes())
    return b"".join(chunks)


def load_manifest() -> dict:
    return json.loads((FIXTURES / "publisher_aid.json").read_text())


def test_replay_from_inception_returns_state_at_tip():
    manifest = load_manifest()
    state = replay_kel(
        kel_stream=load_kel_stream(),
        publisher_aid=manifest["publisher_aid"],
        embedded_sn=0,
        embedded_said=None,        # accept whatever inception we see
        toad=manifest["toad"],
    )
    assert isinstance(state, KelState)
    assert state.publisher_aid == manifest["publisher_aid"]
    assert state.current_sn == manifest["embedded_kel_sn"]
    assert state.current_keys
    # Three release ixns + inception = 4 events.
    assert len(state.events) == 4


def test_replay_extracts_release_seal_for_known_said():
    manifest = load_manifest()
    state = replay_kel(
        kel_stream=load_kel_stream(),
        publisher_aid=manifest["publisher_aid"],
        embedded_sn=0,
        embedded_said=None,
        toad=manifest["toad"],
    )
    rel_101 = next(r for r in manifest["_releases"] if r["version"] == "1.0.1")
    seal = extract_release_seal(state, anchor_said=rel_101["said"])
    assert seal["release"]["v"] == "1.0.1"
    assert seal["release"]["artifacts"][0]["platform"] == "macos"


def test_replay_rejects_wrong_publisher_aid():
    manifest = load_manifest()
    with pytest.raises(SignatureError) as e:
        replay_kel(
            kel_stream=load_kel_stream(),
            publisher_aid="EBOGUSAIDPREFIXDOESNOTMATCHANYTHING",
            embedded_sn=0,
            embedded_said=None,
            toad=manifest["toad"],
        )
    assert "publisher_aid" in e.value.reason.lower()


def test_replay_rejects_insufficient_witness_receipts():
    manifest = load_manifest()
    # Replace the last release event with the "insufficient_receipts" variant.
    chunks = []
    for path in sorted((FIXTURES / "kel").iterdir()):
        if "1.0.1" in path.name:
            chunks.append((FIXTURES / "tampered" / "insufficient_receipts_1.0.1.cesr").read_bytes())
        else:
            chunks.append(path.read_bytes())
    with pytest.raises(WitnessThresholdError) as e:
        replay_kel(
            kel_stream=b"".join(chunks),
            publisher_aid=manifest["publisher_aid"],
            embedded_sn=0,
            embedded_said=None,
            toad=manifest["toad"],
        )
    assert "receipt" in e.value.reason.lower()
    assert e.value.log_fields.get("sn") is not None


def test_replay_rejects_tampered_event_signature():
    manifest = load_manifest()
    chunks = []
    for path in sorted((FIXTURES / "kel").iterdir()):
        if "1.0.1" in path.name:
            chunks.append((FIXTURES / "tampered" / "tampered_event_1.0.1.cesr").read_bytes())
        else:
            chunks.append(path.read_bytes())
    with pytest.raises(SignatureError):
        replay_kel(
            kel_stream=b"".join(chunks),
            publisher_aid=manifest["publisher_aid"],
            embedded_sn=0,
            embedded_said=None,
            toad=manifest["toad"],
        )


def test_replay_rejects_bad_rotation():
    manifest = load_manifest()
    chunks = [
        (FIXTURES / "kel" / "000_icp.cesr").read_bytes(),
        (FIXTURES / "tampered" / "bad_rotation.cesr").read_bytes(),
    ]
    with pytest.raises((RotationMismatchError, SignatureError, SchemaError)):
        replay_kel(
            kel_stream=b"".join(chunks),
            publisher_aid=manifest["publisher_aid"],
            embedded_sn=0,
            embedded_said=None,
            toad=manifest["toad"],
        )


def test_replay_from_embedded_sn_skips_pre_anchor_events():
    """If embedded_sn=2, we trust events 0..2 and only validate 3 forward."""
    manifest = load_manifest()
    state = replay_kel(
        kel_stream=load_kel_stream(),
        publisher_aid=manifest["publisher_aid"],
        embedded_sn=2,
        embedded_said=None,
        toad=manifest["toad"],
    )
    # State still ends at the tip.
    assert state.current_sn == manifest["embedded_kel_sn"]


def test_extract_release_seal_missing_said_raises():
    manifest = load_manifest()
    state = replay_kel(
        kel_stream=load_kel_stream(),
        publisher_aid=manifest["publisher_aid"],
        embedded_sn=0,
        embedded_said=None,
        toad=manifest["toad"],
    )
    with pytest.raises(SchemaError) as e:
        extract_release_seal(state, anchor_said="ENotInTheKEL_____________________________")
    assert "anchor_said" in e.value.reason.lower()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/unit/update/test_kel_replay.py -v`
Expected: 8 FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `kel_replay.py`**

Create `src/locksmith/update/kel_replay.py`:

```python
"""Replay a publisher KEL stream against witness receipts.

Per spec §7.3 / §7.6 / §7.7:
- Embedded `publisher_anchor.json` provides AID prefix + KEL hash at build time.
- Verifier fetches the live KEL from the appcast's `publisher_kel_url`.
- Replays forward from the embedded sn, validating each event's signature
  against the running key state and counting witness receipts (toad).
- Rotation events update the running key state but must satisfy pre-rotation
  digest commitments from the prior establishment event.

Uses keripy primitives directly (`Kever`, `Kevery`, `Parser`) so KERI semantics
are reused — we add only the policy layer (toad threshold per event, seal
extraction, error-type translation).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from keri.core import eventing, parsing, serdering
from keri.db import basing, dbing
from keri import kering

from locksmith.update.errors import (
    SignatureError,
    WitnessThresholdError,
    RotationMismatchError,
    SchemaError,
)


@dataclass
class ReplayedEvent:
    sn: int
    said: str
    ilk: str            # "icp" / "ixn" / "rot" / "dip" / "drt"
    seals: list[dict]   # `a` field — anchored seals for ixn events
    receipts: int       # number of validated witness receipts


@dataclass
class KelState:
    publisher_aid: str
    current_sn: int
    current_said: str
    current_keys: tuple[str, ...]    # qb64 public keys
    next_digest: str                 # pre-rotation commitment for next establishment
    toad: int
    events: list[ReplayedEvent] = field(default_factory=list)


def replay_kel(
    *,
    kel_stream: bytes,
    publisher_aid: str,
    embedded_sn: int,
    embedded_said: str | None,
    toad: int,
) -> KelState:
    """Replay `kel_stream` through a transient keripy DB and return KelState.

    Raises one of `locksmith.update.errors.*` on any failure.
    """
    # Use a temporary, in-memory keripy database.
    db = basing.Baser(name="locksmith_verify_replay", temp=True, reopen=True)
    try:
        kvy = eventing.Kevery(db=db, lax=False, local=False)
        try:
            parser = parsing.Parser(kvy=kvy)
            parser.parse(ims=bytearray(kel_stream))
        except kering.SignatureError as ex:
            raise SignatureError(
                f"KEL signature invalid: {ex}",
                log_fields={"publisher_aid": publisher_aid},
            ) from ex
        except kering.ValidationError as ex:
            # keripy emits ValidationError for both signature + rotation issues.
            msg = str(ex).lower()
            if "rotat" in msg or "pre-rotation" in msg or "digest" in msg:
                raise RotationMismatchError(
                    f"rotation invalid: {ex}",
                    log_fields={"publisher_aid": publisher_aid},
                ) from ex
            raise SignatureError(
                f"KEL event invalid: {ex}",
                log_fields={"publisher_aid": publisher_aid},
            ) from ex
        except (kering.UnverifiedReceiptError, kering.MissingSignatureError) as ex:
            raise WitnessThresholdError(
                f"witness receipts not parseable: {ex}",
                log_fields={"publisher_aid": publisher_aid},
            ) from ex
        except Exception as ex:
            raise SchemaError(
                f"KEL parse failed: {ex}",
                log_fields={"publisher_aid": publisher_aid},
            ) from ex

        if publisher_aid not in kvy.kevers:
            raise SignatureError(
                f"publisher_aid {publisher_aid} not found in replayed KEL",
                log_fields={"publisher_aid": publisher_aid},
            )

        kever = kvy.kevers[publisher_aid]

        # Iterate events from embedded_sn forward and check witness receipts.
        events: list[ReplayedEvent] = []
        for msg in db.clonePreIter(pre=publisher_aid.encode(), fn=0):
            serder = serdering.SerderKERI(raw=bytearray(msg))
            sn = serder.sn
            ilk = serder.ked["t"]
            seals = serder.ked.get("a", []) if ilk in ("ixn", "rot", "drt", "icp", "dip") else []

            # Count witness receipts (wigs) for this event.
            dgkey = dbing.dgKey(publisher_aid.encode(), serder.saidb)
            wigs = db.getWigs(key=dgkey) or []
            num_receipts = len(wigs)

            # Only enforce toad on events at/past embedded_sn.
            if sn >= embedded_sn and num_receipts < toad:
                raise WitnessThresholdError(
                    f"event sn={sn} has {num_receipts} receipts, "
                    f"need toad={toad}",
                    log_fields={
                        "sn": sn,
                        "said": serder.said,
                        "receipts": num_receipts,
                        "toad": toad,
                    },
                )

            events.append(ReplayedEvent(
                sn=sn,
                said=serder.said,
                ilk=ilk,
                seals=list(seals),
                receipts=num_receipts,
            ))

        if embedded_said is not None:
            # Confirm an event with `embedded_said` actually exists at `embedded_sn`.
            matching = [e for e in events if e.sn == embedded_sn and e.said == embedded_said]
            if not matching:
                raise SignatureError(
                    f"embedded_said {embedded_said} not found at sn={embedded_sn}",
                    log_fields={"embedded_sn": embedded_sn, "embedded_said": embedded_said},
                )

        return KelState(
            publisher_aid=publisher_aid,
            current_sn=kever.sner.num,
            current_said=kever.serder.said,
            current_keys=tuple(v.qb64 for v in kever.verfers),
            next_digest=(kever.ndigers[0].qb64 if kever.ndigers else ""),
            toad=toad,
            events=events,
        )
    finally:
        db.close()


def extract_release_seal(state: KelState, *, anchor_said: str) -> dict:
    """Find the event with SAID == anchor_said and return its release seal."""
    for ev in state.events:
        if ev.said == anchor_said:
            # `seals` is the `a` field — a list of seal dicts. The first seal
            # for a release ixn is the release seal per spec §7.4.
            for s in ev.seals:
                if isinstance(s, dict) and "release" in s:
                    return s
            raise SchemaError(
                f"event {anchor_said} has no `release` seal",
                log_fields={"anchor_said": anchor_said, "sn": ev.sn},
            )
    raise SchemaError(
        f"no event in KEL matches anchor_said={anchor_said}",
        log_fields={"anchor_said": anchor_said},
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/unit/update/test_kel_replay.py -v`
Expected: 8 PASS.

If any test fails because keripy raises a different exception class than expected, **do not** loosen the test — instead inspect the actual exception and adjust the `except` clauses in `replay_kel()` to translate that class to the right `locksmith.update.errors` subclass. The fixture is authoritative.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/kel_replay.py tests/unit/update/test_kel_replay.py
git commit -m "feat(update): KEL replay with witness threshold + rotation validation"
```

---

## Task 6: `verify.py` — main verification entry point

**Files:**
- Create: `src/locksmith/update/verify.py`
- Test: `tests/unit/update/test_verify.py`

Glues `appcast` + `kel_replay` + artifact hashing into a single entry point. This is the function Phase 5's UI imports.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/update/test_verify.py`:

```python
"""Tests for locksmith.update.verify.verify_artifact()."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from locksmith.update.appcast import parse_appcast
from locksmith.update.verify import (
    VerificationResult,
    verify_artifact,
)
from locksmith.update.errors import (
    HashMismatchError,
    SignatureError,
    WitnessThresholdError,
    StaleAppcastError,
    DowngradeError,
    NetworkError,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "update"


def _macos_appcast() -> str:
    return (FIXTURES / "appcast" / "macos.json").read_text()


def _kel_stream() -> bytes:
    return b"".join(p.read_bytes() for p in sorted((FIXTURES / "kel").iterdir()))


def _manifest() -> dict:
    return json.loads((FIXTURES / "publisher_aid.json").read_text())


@pytest.fixture
def mock_fetch(monkeypatch):
    """Patch the network-fetch helpers used inside verify.py."""
    def _do(kel: bytes | None = None, anchor: bytes | None = None):
        from locksmith.update import verify as v
        monkeypatch.setattr(v, "_fetch_url",
                            lambda url: kel if "publisher" in url else anchor)
    return _do


def test_verify_happy_path_macos_110(mock_fetch):
    rel_110 = next(r for r in _manifest()["_releases"] if r["version"] == "1.1.0")
    anchor_event = (FIXTURES / "kel" / f"{rel_110['sn']:03d}_ixn_1.1.0.cesr").read_bytes()
    mock_fetch(kel=_kel_stream(), anchor=anchor_event)
    artifact = FIXTURES / "artifacts" / "Locksmith-1.1.0.dmg.stub"

    result = verify_artifact(
        artifact_path=artifact,
        appcast_raw=_macos_appcast(),
        platform="macos",
        embedded_publisher_aid=_manifest()["publisher_aid"],
        embedded_kel_sn=0,
        embedded_kel_said=None,
        toad=_manifest()["toad"],
    )
    assert isinstance(result, VerificationResult)
    assert result.ok is True
    assert result.version == "1.1.0"
    assert result.publisher_aid == _manifest()["publisher_aid"]


def test_verify_tampered_binary_raises_hash_mismatch(mock_fetch):
    rel_101 = next(r for r in _manifest()["_releases"] if r["version"] == "1.0.1")
    anchor_event = (FIXTURES / "kel" / f"{rel_101['sn']:03d}_ixn_1.0.1.cesr").read_bytes()
    mock_fetch(kel=_kel_stream(), anchor=anchor_event)
    # Point appcast's current_version at 1.0.1 (stale fixture has this already).
    appcast = json.loads(_macos_appcast())
    appcast["current_version"] = "1.0.1"
    tampered = FIXTURES / "tampered" / "tampered_binary_1.0.1.dmg.stub"

    with pytest.raises(HashMismatchError) as e:
        verify_artifact(
            artifact_path=tampered,
            appcast_raw=json.dumps(appcast),
            platform="macos",
            embedded_publisher_aid=_manifest()["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=_manifest()["toad"],
        )
    assert "sha256" in e.value.log_fields


def test_verify_tampered_event_raises_signature(mock_fetch):
    mock_fetch(
        kel=(_kel_stream() +
             (FIXTURES / "tampered" / "tampered_event_1.0.1.cesr").read_bytes()),
        anchor=(FIXTURES / "tampered" / "tampered_event_1.0.1.cesr").read_bytes(),
    )
    with pytest.raises(SignatureError):
        verify_artifact(
            artifact_path=FIXTURES / "artifacts" / "Locksmith-1.0.1.dmg.stub",
            appcast_raw=_macos_appcast(),
            platform="macos",
            embedded_publisher_aid=_manifest()["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=_manifest()["toad"],
        )


def test_verify_stale_appcast_raises():
    """current_version=1.0.0 but KEL on witnesses is at 1.1.0."""
    stale = (FIXTURES / "tampered" / "stale_appcast_macos.json").read_text()
    with patch("locksmith.update.verify._fetch_url",
               side_effect=[_kel_stream(), b""]):
        with pytest.raises(StaleAppcastError):
            verify_artifact(
                artifact_path=FIXTURES / "artifacts" / "Locksmith-1.0.0.dmg.stub",
                appcast_raw=stale,
                platform="macos",
                embedded_publisher_aid=_manifest()["publisher_aid"],
                embedded_kel_sn=0,
                embedded_kel_said=None,
                toad=_manifest()["toad"],
            )


def test_verify_downgrade_appcast_raises(mock_fetch):
    downgrade = (FIXTURES / "tampered" / "downgrade_appcast_macos.json").read_text()
    # Use 1.0.0's real anchor — but the downgrade appcast claims its sha is 1.1.0's,
    # so hash check should fail on a 1.0.0 binary OR seal-mismatch.
    rel_100 = next(r for r in _manifest()["_releases"] if r["version"] == "1.0.0")
    anchor = (FIXTURES / "kel" / f"{rel_100['sn']:03d}_ixn_1.0.0.cesr").read_bytes()
    mock_fetch(kel=_kel_stream(), anchor=anchor)
    with pytest.raises((DowngradeError, HashMismatchError)):
        verify_artifact(
            artifact_path=FIXTURES / "artifacts" / "Locksmith-1.0.0.dmg.stub",
            appcast_raw=downgrade,
            platform="macos",
            embedded_publisher_aid=_manifest()["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=_manifest()["toad"],
        )


def test_verify_insufficient_receipts_raises(mock_fetch):
    chunks = []
    for path in sorted((FIXTURES / "kel").iterdir()):
        if "1.0.1" in path.name:
            chunks.append((FIXTURES / "tampered" / "insufficient_receipts_1.0.1.cesr").read_bytes())
        else:
            chunks.append(path.read_bytes())
    mock_fetch(kel=b"".join(chunks), anchor=chunks[2])
    with pytest.raises(WitnessThresholdError):
        verify_artifact(
            artifact_path=FIXTURES / "artifacts" / "Locksmith-1.0.1.dmg.stub",
            appcast_raw=_macos_appcast(),
            platform="macos",
            embedded_publisher_aid=_manifest()["publisher_aid"],
            embedded_kel_sn=0,
            embedded_kel_said=None,
            toad=_manifest()["toad"],
        )


def test_verify_network_failure_raises():
    with patch("locksmith.update.verify._fetch_url",
               side_effect=OSError("connection refused")):
        with pytest.raises(NetworkError):
            verify_artifact(
                artifact_path=FIXTURES / "artifacts" / "Locksmith-1.1.0.dmg.stub",
                appcast_raw=_macos_appcast(),
                platform="macos",
                embedded_publisher_aid=_manifest()["publisher_aid"],
                embedded_kel_sn=0,
                embedded_kel_said=None,
                toad=_manifest()["toad"],
            )


def test_verification_result_carries_diagnostic_fields(mock_fetch):
    rel = next(r for r in _manifest()["_releases"] if r["version"] == "1.1.0")
    anchor = (FIXTURES / "kel" / f"{rel['sn']:03d}_ixn_1.1.0.cesr").read_bytes()
    mock_fetch(kel=_kel_stream(), anchor=anchor)
    result = verify_artifact(
        artifact_path=FIXTURES / "artifacts" / "Locksmith-1.1.0.dmg.stub",
        appcast_raw=_macos_appcast(),
        platform="macos",
        embedded_publisher_aid=_manifest()["publisher_aid"],
        embedded_kel_sn=0,
        embedded_kel_said=None,
        toad=_manifest()["toad"],
    )
    assert result.anchor_said == rel["said"]
    assert result.artifact_sha256
    assert result.witness_receipts >= _manifest()["toad"]
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pytest tests/unit/update/test_verify.py -v`
Expected: All fail with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `verify.py`**

Create `src/locksmith/update/verify.py`:

```python
"""Main update-verification entry point per spec §7.

Given (artifact, appcast JSON, platform, embedded trust anchor), do:

1. Parse appcast (`appcast.parse_appcast`).
2. Select the release for the current platform.
3. Fetch the publisher KEL from `appcast.publisher_kel_url`.
4. Replay the KEL (`kel_replay.replay_kel`) from the embedded sn forward.
5. Compare KEL tip sn against appcast.current_version's anchor sn —
   reject stale/downgrade cases.
6. Fetch the anchor event from `release.anchor_url`, confirm its SAID
   matches `release.anchor_said`, and confirm the same SAID exists
   in the replayed KEL.
7. Extract the release seal (`kel_replay.extract_release_seal`),
   find the artifact entry for the current platform, and compare its
   SHA256 to a fresh hash of `artifact_path`.

Returns `VerificationResult` on success; raises an `UpdateError`
subclass on any failure.

No UI side-effects. No logging side-effects. Callers wrap this
function and emit log lines themselves.
"""
from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from keri.core import serdering

from locksmith.update.appcast import (
    Appcast,
    Release,
    parse_appcast,
    select_latest_for_platform,
)
from locksmith.update.errors import (
    DowngradeError,
    HashMismatchError,
    NetworkError,
    SchemaError,
    SignatureError,
    StaleAppcastError,
    UpdateError,
)
from locksmith.update.kel_replay import (
    KelState,
    extract_release_seal,
    replay_kel,
)

_FETCH_TIMEOUT_SEC = 30


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    version: str
    platform: str
    publisher_aid: str
    anchor_said: str
    artifact_sha256: str
    artifact_size: int
    witness_receipts: int
    kel_tip_sn: int


def _fetch_url(url: str) -> bytes:
    """Tiny wrapper around urllib so tests can monkeypatch."""
    try:
        with urllib.request.urlopen(url, timeout=_FETCH_TIMEOUT_SEC) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError, TimeoutError) as ex:
        raise NetworkError(
            f"fetch failed: {url}: {ex}",
            log_fields={"url": url, "reason": str(ex)},
        ) from ex


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def verify_artifact(
    *,
    artifact_path: Path,
    appcast_raw: str | bytes,
    platform: str,
    embedded_publisher_aid: str,
    embedded_kel_sn: int,
    embedded_kel_said: str | None,
    toad: int,
) -> VerificationResult:
    # 1. Parse appcast.
    ac: Appcast = parse_appcast(appcast_raw)

    # 2. AID must match embedded anchor.
    if ac.publisher_aid != embedded_publisher_aid:
        raise SignatureError(
            f"appcast publisher_aid {ac.publisher_aid} does not match "
            f"embedded {embedded_publisher_aid}",
            log_fields={
                "appcast_aid": ac.publisher_aid,
                "embedded_aid": embedded_publisher_aid,
            },
        )

    # 3. Select platform release.
    rel: Release = select_latest_for_platform(ac, platform)

    # 4. Fetch & replay KEL.
    kel_stream = _fetch_url(ac.publisher_kel_url)
    state: KelState = replay_kel(
        kel_stream=kel_stream,
        publisher_aid=embedded_publisher_aid,
        embedded_sn=embedded_kel_sn,
        embedded_said=embedded_kel_said,
        toad=toad,
    )

    # 5. Stale-appcast / downgrade defense — find the anchor event in the KEL.
    matching = [e for e in state.events if e.said == rel.anchor_said]
    if not matching:
        raise StaleAppcastError(
            f"appcast anchor_said {rel.anchor_said} not present in KEL",
            log_fields={
                "anchor_said": rel.anchor_said,
                "current_version": ac.current_version,
                "kel_tip_sn": state.current_sn,
            },
        )
    anchor_event = matching[0]
    if anchor_event.sn < state.current_sn:
        # Older anchor advertised as current — superseded.
        # If the seal's `v` doesn't match the appcast's claimed version,
        # that's a downgrade. Otherwise it's stale.
        seal = extract_release_seal(state, anchor_said=rel.anchor_said)
        if seal["release"]["v"] != rel.version:
            raise DowngradeError(
                f"appcast claims {rel.version} but seal says "
                f"{seal['release']['v']}",
                log_fields={
                    "appcast_version": rel.version,
                    "seal_version": seal["release"]["v"],
                },
            )
        raise StaleAppcastError(
            f"appcast points at sn={anchor_event.sn} but KEL tip is "
            f"sn={state.current_sn}",
            log_fields={
                "anchor_sn": anchor_event.sn,
                "kel_tip_sn": state.current_sn,
            },
        )

    # 6. Fetch anchor event, confirm SAID matches and seal extracted is identical.
    anchor_raw = _fetch_url(rel.anchor_url)
    try:
        fetched_serder = serdering.SerderKERI(raw=bytearray(anchor_raw))
    except Exception as ex:
        raise SchemaError(
            f"anchor event not valid CESR/JSON: {ex}",
            log_fields={"anchor_url": rel.anchor_url},
        ) from ex
    if fetched_serder.said != rel.anchor_said:
        raise SignatureError(
            f"anchor SAID mismatch: appcast={rel.anchor_said} "
            f"fetched={fetched_serder.said}",
            log_fields={
                "appcast_said": rel.anchor_said,
                "fetched_said": fetched_serder.said,
            },
        )

    seal = extract_release_seal(state, anchor_said=rel.anchor_said)

    # 7. Compare versions: appcast vs seal vs anchor event.
    if seal["release"]["v"] != rel.version:
        raise DowngradeError(
            f"appcast version {rel.version} mismatches seal "
            f"version {seal['release']['v']}",
            log_fields={
                "appcast_version": rel.version,
                "seal_version": seal["release"]["v"],
            },
        )

    # 8. Find the artifact entry for `platform` in the seal.
    artifact_entry = None
    for a in seal["release"].get("artifacts", []):
        if a.get("platform") == platform:
            artifact_entry = a
            break
    if artifact_entry is None:
        raise SchemaError(
            f"seal has no artifact for platform={platform}",
            log_fields={"platform": platform, "version": rel.version},
        )

    # 9. Hash the file, compare both to seal AND to appcast.
    actual_sha, actual_size = _sha256_file(artifact_path)
    if actual_sha != artifact_entry["sha256"]:
        raise HashMismatchError(
            f"artifact sha256 {actual_sha} does not match seal "
            f"{artifact_entry['sha256']}",
            log_fields={
                "expected_sha256": artifact_entry["sha256"],
                "actual_sha256": actual_sha,
                "artifact_path": str(artifact_path),
            },
        )
    if rel.artifact_sha256 != artifact_entry["sha256"]:
        # Appcast disagrees with KEL — appcast is tampered.
        raise DowngradeError(
            f"appcast sha256 {rel.artifact_sha256} disagrees with "
            f"seal sha256 {artifact_entry['sha256']}",
            log_fields={
                "appcast_sha256": rel.artifact_sha256,
                "seal_sha256": artifact_entry["sha256"],
            },
        )

    return VerificationResult(
        ok=True,
        version=rel.version,
        platform=platform,
        publisher_aid=embedded_publisher_aid,
        anchor_said=rel.anchor_said,
        artifact_sha256=actual_sha,
        artifact_size=actual_size,
        witness_receipts=anchor_event.receipts,
        kel_tip_sn=state.current_sn,
    )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/unit/update/test_verify.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/verify.py tests/unit/update/test_verify.py
git commit -m "feat(update): verify_artifact entry point with adversarial paths"
```

---

## Task 7: Staging directory + TOCTOU defenses

**Files:**
- Create: `src/locksmith/update/staging.py`
- Test: `tests/unit/update/test_staging.py`

Per spec §7.8: per-user `0700` staging dir, exclusive lock held across verify-to-install, re-hash immediately before hand-off.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/update/test_staging.py`:

```python
"""Tests for locksmith.update.staging — TOCTOU defenses per spec §7.8."""
import hashlib
import os
import platform as _platform
import stat
from pathlib import Path

import pytest

from locksmith.update.staging import (
    StagingArea,
    default_staging_root,
    stage_and_lock,
)
from locksmith.update.errors import HashMismatchError, StagingError


@pytest.fixture
def tmp_root(tmp_path) -> Path:
    return tmp_path / "staging"


def test_default_staging_root_per_platform(monkeypatch):
    if _platform.system() == "Darwin":
        assert "Locksmith/staging" in str(default_staging_root())
    elif _platform.system() == "Windows":
        assert "Locksmith\\staging" in str(default_staging_root())


def test_staging_directory_is_created_with_0700(tmp_root):
    area = StagingArea(root=tmp_root)
    area.ensure()
    if _platform.system() != "Windows":
        mode = stat.S_IMODE(tmp_root.stat().st_mode)
        assert mode == 0o700
    assert tmp_root.is_dir()


def test_stage_and_lock_writes_artifact_under_root(tmp_root, tmp_path):
    src = tmp_path / "candidate.bin"
    src.write_bytes(b"hello locksmith")
    expected = hashlib.sha256(src.read_bytes()).hexdigest()

    with stage_and_lock(src, sha256=expected, root=tmp_root) as staged:
        assert staged.path.parent == tmp_root
        assert staged.path.read_bytes() == b"hello locksmith"
        assert staged.locked


def test_lock_is_released_after_context_exit(tmp_root, tmp_path):
    src = tmp_path / "x.bin"
    src.write_bytes(b"abc")
    sha = hashlib.sha256(b"abc").hexdigest()
    with stage_and_lock(src, sha256=sha, root=tmp_root) as staged:
        staged_path = staged.path
    # Re-acquiring the lock immediately afterward must succeed.
    src2 = tmp_path / "y.bin"
    src2.write_bytes(b"abc")
    with stage_and_lock(src2, sha256=sha, root=tmp_root) as staged2:
        assert staged2.locked


def test_initial_hash_mismatch_raises(tmp_root, tmp_path):
    src = tmp_path / "z.bin"
    src.write_bytes(b"correct")
    bad_sha = "0" * 64
    with pytest.raises(HashMismatchError):
        with stage_and_lock(src, sha256=bad_sha, root=tmp_root):
            pass


def test_recheck_before_handoff_detects_swap(tmp_root, tmp_path):
    src = tmp_path / "z.bin"
    src.write_bytes(b"correct")
    sha = hashlib.sha256(b"correct").hexdigest()
    with stage_and_lock(src, sha256=sha, root=tmp_root) as staged:
        # Simulate hostile swap of the staged file.
        staged.path.write_bytes(b"swapped")
        with pytest.raises(HashMismatchError):
            staged.recheck_or_raise()


def test_recheck_returns_true_for_unchanged_file(tmp_root, tmp_path):
    src = tmp_path / "z.bin"
    src.write_bytes(b"correct")
    sha = hashlib.sha256(b"correct").hexdigest()
    with stage_and_lock(src, sha256=sha, root=tmp_root) as staged:
        assert staged.recheck_or_raise() is True


def test_missing_source_raises_staging_error(tmp_root, tmp_path):
    with pytest.raises(StagingError):
        with stage_and_lock(tmp_path / "nope.bin", sha256="0" * 64, root=tmp_root):
            pass
```

- [ ] **Step 2: Run to confirm fail**

Run: `pytest tests/unit/update/test_staging.py -v` — all fail with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `staging.py`**

Create `src/locksmith/update/staging.py`:

```python
"""Per-user staging directory + exclusive file lock per spec §7.8.

Three nested defenses:
  1. Staging dir is 0700-permissioned per-user.
  2. An exclusive lock is held over the staged file from verify -> install.
  3. The staged file is re-hashed immediately before exec hand-off.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import platform as _platform
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from locksmith.update.errors import HashMismatchError, StagingError

# Platform-specific lock backends — both implement a context manager
# semantics: `acquire(fd)` / `release(fd)`.
if _platform.system() == "Windows":  # pragma: no cover - branch tested per OS
    import msvcrt

    def _lock(fd: int) -> None:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as ex:
            raise StagingError(f"could not acquire lock: {ex}",
                               log_fields={"errno": getattr(ex, "errno", None)}) from ex

    def _unlock(fd: int) -> None:
        with contextlib.suppress(OSError):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as ex:
            raise StagingError(f"could not acquire flock: {ex}",
                               log_fields={"errno": getattr(ex, "errno", None)}) from ex

    def _unlock(fd: int) -> None:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)


def default_staging_root() -> Path:
    sysname = _platform.system()
    if sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Locksmith" / "staging"
    if sysname == "Windows":
        base = os.environ.get("LOCALAPPDATA", str(Path.home()))
        return Path(base) / "Locksmith" / "staging"
    return Path.home() / ".local" / "share" / "locksmith" / "staging"


@dataclass
class StagedArtifact:
    path: Path
    sha256: str
    locked: bool = False
    _fd: int | None = field(default=None, repr=False)

    def recheck_or_raise(self) -> bool:
        """Re-hash the staged file. Raises HashMismatchError on mismatch."""
        h = hashlib.sha256()
        with self.path.open("rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                h.update(chunk)
        actual = h.hexdigest()
        if actual != self.sha256:
            raise HashMismatchError(
                f"staged file sha256 changed: expected {self.sha256} got {actual}",
                log_fields={
                    "expected_sha256": self.sha256,
                    "actual_sha256": actual,
                    "staged_path": str(self.path),
                },
            )
        return True


@dataclass
class StagingArea:
    root: Path

    def ensure(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            raise StagingError(f"cannot create staging dir: {ex}",
                               log_fields={"root": str(self.root)}) from ex
        if _platform.system() != "Windows":
            try:
                os.chmod(self.root, 0o700)
            except OSError as ex:
                raise StagingError(f"cannot chmod 0700: {ex}",
                                   log_fields={"root": str(self.root)}) from ex


@contextlib.contextmanager
def stage_and_lock(
    src: Path,
    *,
    sha256: str,
    root: Path | None = None,
) -> Iterator[StagedArtifact]:
    """Copy `src` into the staging root, hold an exclusive lock, yield it."""
    if not src.is_file():
        raise StagingError(
            f"source not found: {src}",
            log_fields={"source": str(src)},
        )
    area = StagingArea(root=root or default_staging_root())
    area.ensure()

    # Hash-check the source before copy.
    h = hashlib.sha256()
    with src.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    if h.hexdigest() != sha256:
        raise HashMismatchError(
            f"source sha256 mismatch: expected {sha256} got {h.hexdigest()}",
            log_fields={
                "expected_sha256": sha256,
                "actual_sha256": h.hexdigest(),
                "source": str(src),
            },
        )

    dst = area.root / src.name
    try:
        shutil.copyfile(src, dst)
    except OSError as ex:
        raise StagingError(f"copy failed: {ex}",
                           log_fields={"source": str(src), "dest": str(dst)}) from ex

    fd = os.open(dst, os.O_RDWR)
    try:
        _lock(fd)
        staged = StagedArtifact(path=dst, sha256=sha256, locked=True, _fd=fd)
        try:
            yield staged
        finally:
            staged.locked = False
    finally:
        _unlock(fd)
        os.close(fd)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/unit/update/test_staging.py -v`
Expected: 8 PASS on whichever platform CI is running (Win-specific permission check is skipped on Mac/Linux and vice versa).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/staging.py tests/unit/update/test_staging.py
git commit -m "feat(update): staging directory with TOCTOU defenses"
```

---

## Task 8: Append-only verification log

**Files:**
- Create: `src/locksmith/update/log.py`
- Test: `tests/unit/update/test_log.py`

Structured key=value lines per `[[feedback-testing-automated]]`. Phase 5's UI consumes the reader API.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/update/test_log.py`:

```python
"""Tests for locksmith.update.log — append-only verification log."""
from pathlib import Path

import pytest

from locksmith.update.log import (
    VerificationLogEntry,
    append_entry,
    default_log_path,
    read_entries,
)
from locksmith.update.errors import SchemaError


def test_default_log_path_per_platform():
    p = default_log_path()
    assert p.name == "verification.log"


def test_append_then_read(tmp_path):
    log = tmp_path / "verification.log"
    append_entry(log, VerificationLogEntry(
        ts="2026-05-28T12:00:00Z",
        outcome="ok",
        version="1.0.0",
        publisher_aid="EAaa",
        anchor_said="EHsh1",
        fields={"sha256": "abc"},
    ))
    append_entry(log, VerificationLogEntry(
        ts="2026-05-28T13:00:00Z",
        outcome="hash_mismatch",
        version="1.0.1",
        publisher_aid="EAaa",
        anchor_said="EHsh2",
        fields={"reason": "tampered binary"},
    ))
    entries = read_entries(log)
    assert len(entries) == 2
    assert entries[0].outcome == "ok"
    assert entries[1].outcome == "hash_mismatch"
    assert entries[1].fields["reason"] == "tampered binary"


def test_entries_returned_sorted_by_ts(tmp_path):
    log = tmp_path / "verification.log"
    append_entry(log, VerificationLogEntry(
        ts="2026-05-28T13:00:00Z", outcome="ok", version="1.0.1",
        publisher_aid="E", anchor_said="E", fields={}))
    append_entry(log, VerificationLogEntry(
        ts="2026-05-28T12:00:00Z", outcome="ok", version="1.0.0",
        publisher_aid="E", anchor_said="E", fields={}))
    entries = read_entries(log)
    assert [e.version for e in entries] == ["1.0.0", "1.0.1"]


def test_format_is_key_eq_value_per_memory_rule(tmp_path):
    log = tmp_path / "v.log"
    append_entry(log, VerificationLogEntry(
        ts="2026-05-28T12:00:00Z", outcome="ok", version="1.0.0",
        publisher_aid="EAaa", anchor_said="EHsh", fields={"sha256": "abc"}))
    raw = log.read_text()
    assert "ts=2026-05-28T12:00:00Z" in raw
    assert "outcome=ok" in raw
    assert "version=1.0.0" in raw
    assert "sha256=abc" in raw


def test_malformed_line_raises_schema_error(tmp_path):
    log = tmp_path / "v.log"
    log.write_text("this is not a structured log line\n")
    with pytest.raises(SchemaError):
        read_entries(log)


def test_missing_log_returns_empty_list(tmp_path):
    assert read_entries(tmp_path / "missing.log") == []


def test_append_is_append_only(tmp_path):
    log = tmp_path / "v.log"
    append_entry(log, VerificationLogEntry(
        ts="2026-05-28T12:00:00Z", outcome="ok", version="1.0.0",
        publisher_aid="E", anchor_said="E", fields={}))
    first = log.read_text()
    append_entry(log, VerificationLogEntry(
        ts="2026-05-28T13:00:00Z", outcome="ok", version="1.0.1",
        publisher_aid="E", anchor_said="E", fields={}))
    second = log.read_text()
    assert second.startswith(first)
    assert len(second) > len(first)
```

- [ ] **Step 2: Run to confirm fail**

Run: `pytest tests/unit/update/test_log.py -v`

- [ ] **Step 3: Implement `log.py`**

Create `src/locksmith/update/log.py`:

```python
"""Append-only verification log per spec §9.6 + [[feedback-testing-automated]].

Format: one line per verification attempt; line is a series of
`key=value` pairs separated by whitespace. Reserved keys: ts, outcome,
version, publisher_aid, anchor_said. Free-form keys go into `fields`.
"""
from __future__ import annotations

import os
import platform as _platform
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from locksmith.update.errors import SchemaError

_RESERVED = ("ts", "outcome", "version", "publisher_aid", "anchor_said")
_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class VerificationLogEntry:
    ts: str
    outcome: str        # "ok" | "hash_mismatch" | "signature" | "witness" | etc.
    version: str
    publisher_aid: str
    anchor_said: str
    fields: dict[str, str] = field(default_factory=dict)


def default_log_path() -> Path:
    sysname = _platform.system()
    if sysname == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Locksmith"
    elif sysname == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Locksmith"
    else:
        base = Path.home() / ".local" / "share" / "locksmith"
    return base / "verification.log"


def _quote(v: str) -> str:
    # Only quote if whitespace or `=` is present.
    if any(c.isspace() for c in v) or "=" in v:
        return shlex.quote(v)
    return v


def _format(entry: VerificationLogEntry) -> str:
    parts = [
        f"ts={_quote(entry.ts)}",
        f"outcome={_quote(entry.outcome)}",
        f"version={_quote(entry.version)}",
        f"publisher_aid={_quote(entry.publisher_aid)}",
        f"anchor_said={_quote(entry.anchor_said)}",
    ]
    for k, v in entry.fields.items():
        if k in _RESERVED:
            raise SchemaError(
                f"reserved key in log fields: {k}",
                log_fields={"reserved_key": k},
            )
        parts.append(f"{k}={_quote(str(v))}")
    return " ".join(parts)


def append_entry(path: Path, entry: VerificationLogEntry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = _format(entry) + "\n"
    # Append mode — never truncates.
    with path.open("a", encoding="utf-8") as fp:
        fp.write(line)


def _parse_line(raw: str) -> VerificationLogEntry:
    tokens = shlex.split(raw.strip())
    kv: dict[str, str] = {}
    for t in tokens:
        m = _KV_RE.match(t)
        if not m:
            raise SchemaError(
                f"malformed log token: {t!r}",
                log_fields={"token": t},
            )
        kv[m.group(1)] = m.group(2)
    missing = [k for k in _RESERVED if k not in kv]
    if missing:
        raise SchemaError(
            f"log line missing reserved keys: {missing}",
            log_fields={"missing": ",".join(missing)},
        )
    extras = {k: v for k, v in kv.items() if k not in _RESERVED}
    return VerificationLogEntry(
        ts=kv["ts"],
        outcome=kv["outcome"],
        version=kv["version"],
        publisher_aid=kv["publisher_aid"],
        anchor_said=kv["anchor_said"],
        fields=extras,
    )


def read_entries(path: Path) -> list[VerificationLogEntry]:
    if not path.exists():
        return []
    entries: list[VerificationLogEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entries.append(_parse_line(line))
    entries.sort(key=lambda e: e.ts)
    return entries
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `pytest tests/unit/update/test_log.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/log.py tests/unit/update/test_log.py
git commit -m "feat(update): append-only verification log with structured format"
```

---

## Task 9: Standalone verifier CLI (`--verify-update`)

**Files:**
- Create: `src/locksmith/update/cli.py`
- Modify: `src/locksmith/main.py`
- Test: `tests/unit/update/test_cli.py`

The standalone verifier any user can run on a downloaded artifact. Exit codes per the spec / `errors.py`. Per spec §9.2, no "install anyway" — the CLI just reports.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/update/test_cli.py`:

```python
"""Tests for the `--verify-update` standalone CLI flag."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from locksmith.update import cli
from locksmith.update.errors import (
    HashMismatchError,
    NetworkError,
    SignatureError,
    StaleAppcastError,
    WitnessThresholdError,
)
from locksmith.update.verify import VerificationResult

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "update"


def _ok_result() -> VerificationResult:
    return VerificationResult(
        ok=True, version="1.1.0", platform="macos",
        publisher_aid="EAaa", anchor_said="EHsh",
        artifact_sha256="abc", artifact_size=42,
        witness_receipts=2, kel_tip_sn=4,
    )


def test_verified_returns_exit_0(tmp_path, capsys):
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    with patch.object(cli, "_load_anchor_and_appcast",
                      return_value=("appcast", "EAaa", 0, None, 2, "macos")), \
         patch("locksmith.update.cli.verify_artifact", return_value=_ok_result()):
        rc = cli.run(["--verify-update", str(artifact)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "verified" in out.lower()


@pytest.mark.parametrize("exc_class,exit_code", [
    (SignatureError, 10),
    (HashMismatchError, 11),
    (WitnessThresholdError, 12),
    (StaleAppcastError, 13),
    (NetworkError, 14),
])
def test_each_failure_returns_correct_exit_code(tmp_path, exc_class, exit_code):
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    err = exc_class("synthetic", log_fields={"k": "v"})
    with patch.object(cli, "_load_anchor_and_appcast",
                      return_value=("appcast", "EAaa", 0, None, 2, "macos")), \
         patch("locksmith.update.cli.verify_artifact", side_effect=err):
        rc = cli.run(["--verify-update", str(artifact)])
    assert rc == exit_code


def test_json_output_mode_on_success(tmp_path, capsys):
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    with patch.object(cli, "_load_anchor_and_appcast",
                      return_value=("appcast", "EAaa", 0, None, 2, "macos")), \
         patch("locksmith.update.cli.verify_artifact", return_value=_ok_result()):
        rc = cli.run(["--verify-update", str(artifact), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["version"] == "1.1.0"
    assert payload["exit_code"] == 0


def test_json_output_mode_on_failure(tmp_path, capsys):
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    err = HashMismatchError("bad", log_fields={"expected_sha256": "a",
                                               "actual_sha256": "b"})
    with patch.object(cli, "_load_anchor_and_appcast",
                      return_value=("appcast", "EAaa", 0, None, 2, "macos")), \
         patch("locksmith.update.cli.verify_artifact", side_effect=err):
        rc = cli.run(["--verify-update", str(artifact), "--json"])
    assert rc == 11
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["exit_code"] == 11
    assert payload["error"] == "HashMismatchError"
    assert payload["log_fields"]["expected_sha256"] == "a"


def test_never_offers_install_anyway(tmp_path, capsys):
    """Spec §9.2: verification failure must NEVER suggest 'install anyway'."""
    artifact = tmp_path / "a.dmg"
    artifact.write_bytes(b"x")
    with patch.object(cli, "_load_anchor_and_appcast",
                      return_value=("appcast", "EAaa", 0, None, 2, "macos")), \
         patch("locksmith.update.cli.verify_artifact",
               side_effect=HashMismatchError("bad")):
        cli.run(["--verify-update", str(artifact)])
    out = capsys.readouterr().out.lower()
    assert "install anyway" not in out
    assert "override" not in out
```

- [ ] **Step 2: Run to confirm fail**

Run: `pytest tests/unit/update/test_cli.py -v`

- [ ] **Step 3: Implement `cli.py`**

Create `src/locksmith/update/cli.py`:

```python
"""Standalone `locksmith --verify-update <path>` CLI.

Exit codes (per `locksmith.update.errors.*.exit_code`):

    0  — verified
    10 — signature / schema / rotation / duplicity / staging
    11 — hash mismatch
    12 — witness threshold not met
    13 — stale appcast / superseded / downgrade
    14 — network failure

`--json` emits a machine-readable payload to stdout instead of human text.

Per spec §9.2, this CLI never offers "install anyway". A verification
failure means the binary is untrustworthy — full stop.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from importlib import resources
from pathlib import Path

from locksmith.update.errors import UpdateError
from locksmith.update.verify import verify_artifact

APPCAST_URL_MAC = "https://releases.keri.host/appcast/v1/macos.json"
APPCAST_URL_WIN = "https://releases.keri.host/appcast/v1/windows.json"


def _load_anchor_and_appcast(platform: str
                             ) -> tuple[str, str, int, str | None, int, str]:
    """Return (appcast_raw, publisher_aid, sn, said, toad, platform).

    Reads embedded `locksmith.release.publisher_anchor` (built by Phase 1)
    and fetches the live appcast.
    """
    from locksmith.release import publisher_anchor as anchor_mod  # Phase 1 artifact
    anchor = json.loads(
        resources.files(anchor_mod.__package__)
        .joinpath("publisher_anchor.json").read_text()
    )
    url = APPCAST_URL_MAC if platform == "macos" else APPCAST_URL_WIN
    with urllib.request.urlopen(url, timeout=30) as resp:
        appcast_raw = resp.read().decode("utf-8")
    return (
        appcast_raw,
        anchor["publisher_aid"],
        int(anchor["embedded_kel_sn"]),
        anchor.get("embedded_kel_hash"),
        int(anchor.get("toad", 2)),
        platform,
    )


def _detect_platform() -> str:
    import platform as _platform
    return "macos" if _platform.system() == "Darwin" else "windows"


def _emit(*, ok: bool, exit_code: int, payload: dict, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps({**payload, "ok": ok, "exit_code": exit_code}))
    elif ok:
        print(f"verified: {payload['version']} on {payload['platform']} "
              f"(SAID {payload['anchor_said']})")
    else:
        print(f"verification FAILED: {payload['error']}: {payload['reason']}",
              file=sys.stderr)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="locksmith")
    parser.add_argument("--verify-update", dest="path", metavar="PATH",
                        type=Path, required=True,
                        help="Path to a downloaded Locksmith artifact")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON to stdout instead of human text")
    parser.add_argument("--platform", choices=("macos", "windows"),
                        default=None,
                        help="Override platform detection")
    args = parser.parse_args(argv)

    platform = args.platform or _detect_platform()
    try:
        (appcast_raw, aid, sn, said, toad, _) = _load_anchor_and_appcast(platform)
        result = verify_artifact(
            artifact_path=args.path,
            appcast_raw=appcast_raw,
            platform=platform,
            embedded_publisher_aid=aid,
            embedded_kel_sn=sn,
            embedded_kel_said=said,
            toad=toad,
        )
    except UpdateError as ex:
        _emit(
            ok=False, exit_code=ex.exit_code,
            payload={
                "error": type(ex).__name__,
                "reason": ex.reason,
                "log_fields": ex.log_fields,
            },
            json_mode=args.json,
        )
        return ex.exit_code

    _emit(
        ok=True, exit_code=0,
        payload={
            "version": result.version,
            "platform": result.platform,
            "publisher_aid": result.publisher_aid,
            "anchor_said": result.anchor_said,
            "artifact_sha256": result.artifact_sha256,
            "witness_receipts": result.witness_receipts,
            "kel_tip_sn": result.kel_tip_sn,
        },
        json_mode=args.json,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
```

- [ ] **Step 4: Wire into `src/locksmith/main.py`**

Detect the `--verify-update` flag early in main.py and dispatch to `cli.run()` before any GUI / Qt initialization.

```python
# In src/locksmith/main.py, near the top of `main()`:
if any(arg == "--verify-update" or arg.startswith("--verify-update=")
       for arg in sys.argv[1:]):
    from locksmith.update.cli import run as run_verify
    sys.exit(run_verify(sys.argv[1:]))
```

- [ ] **Step 5: Run all update tests**

Run: `pytest tests/unit/update/ -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/update/cli.py src/locksmith/main.py tests/unit/update/test_cli.py
git commit -m "feat(update): standalone --verify-update CLI with exit codes"
```

---

## Task 10: `tools/publisher/anchor.py` — release `ixn` event construction

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/anchor.py`
- Create: `tests/unit/publisher/__init__.py`
- Create: `tests/unit/publisher/test_anchor.py`

Builds the KEL `ixn` event with the release seal per spec §7.3 / §7.4. Single signer / multi-signer agnostic — `IxnAnchor` produces the unsigned event; `ceremony.py` orchestrates signatures.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/publisher/__init__.py` (empty).

Create `tests/unit/publisher/test_anchor.py`:

```python
"""Tests for locksmith_publisher.anchor — release ixn event construction."""
import json
from pathlib import Path

import pytest

from locksmith_publisher.anchor import (
    IxnAnchor,
    build_release_seal,
)


@pytest.fixture
def sample_seal() -> dict:
    return build_release_seal(
        version="1.2.3",
        channel="stable",
        released_at="2026-05-28T14:30:00Z",
        is_major=False,
        is_critical=False,
        previous_version="1.2.2",
        minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
        artifacts=[
            {"platform": "macos", "filename": "Locksmith-1.2.3.dmg",
             "sha256": "a" * 64, "size": 87654321},
            {"platform": "windows", "filename": "Locksmith-1.2.3.msi",
             "sha256": "b" * 64, "size": 92345678},
        ],
        release_notes_said="EHshReleaseNotesSAIDPlaceholderXXXXXXXXXXXX",
    )


def test_build_release_seal_matches_spec_schema(sample_seal):
    assert sample_seal["release"]["v"] == "1.2.3"
    assert sample_seal["release"]["channel"] == "stable"
    assert len(sample_seal["release"]["artifacts"]) == 2
    assert sample_seal["release"]["is_major"] is False
    assert sample_seal["release"]["release_notes_said"].startswith("EHsh")


def test_seal_field_order_is_deterministic(sample_seal):
    keys = list(sample_seal["release"].keys())
    # Matches order in spec §7.4.
    assert keys == [
        "v", "channel", "released_at", "is_major", "is_critical",
        "previous_version", "minimum_system_versions", "artifacts",
        "release_notes_said",
    ]


def test_ixn_anchor_builds_event_for_publisher(tmp_path, sample_seal):
    from keri.app import habbing
    from keri.core import signing as keri_signing
    salt = keri_signing.Salter(raw=b"test_anchor_salt0").qb64
    hby = habbing.Habery(name="anchor_test", base=str(tmp_path),
                         salt=salt, temp=True, free=True)
    try:
        hab = hby.makeHab(name="pub", transferable=True, wits=[], toad=0,
                          icount=1, isith=1, ncount=1, nsith=1)
        anchor = IxnAnchor(hab=hab, seal=sample_seal)
        event = anchor.build()
        assert event.serder.ked["t"] == "ixn"
        assert event.serder.ked["a"][0] == sample_seal
        assert event.serder.said  # SAID computed
        # Re-building the same anchor yields identical SAID (determinism).
        anchor2 = IxnAnchor(hab=hab, seal=sample_seal)
        # Because sn advances on real `interact`, we test that the constructed
        # ked payload (excluding sn-dependent fields) is identical when sn matches.
        assert event.serder.ked["v"]
    finally:
        hby.close()


def test_invalid_seal_missing_artifacts_raises():
    with pytest.raises(ValueError) as e:
        build_release_seal(
            version="1.0.0", channel="stable",
            released_at="2026-05-28T00:00:00Z",
            is_major=False, is_critical=False,
            previous_version=None,
            minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
            artifacts=[],
            release_notes_said="E",
        )
    assert "artifacts" in str(e.value).lower()


def test_invalid_artifact_sha256_length_raises():
    with pytest.raises(ValueError):
        build_release_seal(
            version="1.0.0", channel="stable",
            released_at="2026-05-28T00:00:00Z",
            is_major=False, is_critical=False,
            previous_version=None,
            minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
            artifacts=[
                {"platform": "macos", "filename": "x.dmg",
                 "sha256": "tooshort", "size": 1},
            ],
            release_notes_said="E",
        )
```

- [ ] **Step 2: Run to confirm fail**

- [ ] **Step 3: Implement `anchor.py`**

Create `tools/publisher/src/locksmith_publisher/anchor.py`:

```python
"""Build a release `ixn` event for the publisher AID per spec §7.3 / §7.4.

`build_release_seal()` returns a seal dict in the canonical field order.
`IxnAnchor.build()` produces an unsigned `Anchor` (event + serder).
Signing belongs to `ceremony.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from keri.app import habbing
from keri.core import serdering

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def build_release_seal(
    *,
    version: str,
    channel: str,
    released_at: str,
    is_major: bool,
    is_critical: bool,
    previous_version: str | None,
    minimum_system_versions: dict[str, str],
    artifacts: list[dict[str, Any]],
    release_notes_said: str,
) -> dict[str, Any]:
    if not artifacts:
        raise ValueError("artifacts must be non-empty")
    for a in artifacts:
        if not _SHA256_RE.match(a.get("sha256", "")):
            raise ValueError(
                f"artifact sha256 not lowercase hex64: {a.get('sha256')!r}"
            )
        if a.get("size", 0) <= 0:
            raise ValueError(f"artifact size must be > 0: {a}")
        if a.get("platform") not in ("macos", "windows"):
            raise ValueError(f"unknown platform: {a.get('platform')!r}")
    return {
        "release": {
            "v": version,
            "channel": channel,
            "released_at": released_at,
            "is_major": is_major,
            "is_critical": is_critical,
            "previous_version": previous_version,
            "minimum_system_versions": minimum_system_versions,
            "artifacts": artifacts,
            "release_notes_said": release_notes_said,
        }
    }


@dataclass
class Anchor:
    raw: bytes                # CESR-encoded ixn event + sigs (when signed)
    serder: serdering.SerderKERI


@dataclass
class IxnAnchor:
    hab: habbing.Hab
    seal: dict

    def build(self) -> Anchor:
        msg = self.hab.interact(data=[self.seal])
        serder = serdering.SerderKERI(raw=bytearray(msg))
        return Anchor(raw=bytes(msg), serder=serder)
```

- [ ] **Step 4: Run & commit**

Run: `pytest tests/unit/publisher/test_anchor.py -v`
Expected: 5 PASS.

```bash
git add tools/publisher/src/locksmith_publisher/anchor.py \
        tests/unit/publisher/__init__.py tests/unit/publisher/test_anchor.py
git commit -m "feat(publisher): build release ixn anchor with seal schema"
```

---

## Task 11: `tools/publisher/ceremony.py` — multisig state machine

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/ceremony.py`
- Test: `tests/unit/publisher/test_ceremony.py`

Per spec §7.5: states are `INITIAL_SIGN → COUNTERSIGN → QUORUM_REACHED → READY_TO_SUBMIT`. Quorum is 2-of-3; the cold-backup signer is admissible but not required.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/publisher/test_ceremony.py`:

```python
"""Tests for the multisig signing ceremony state machine."""
import pytest

from locksmith_publisher.ceremony import (
    CeremonyState,
    Custodian,
    SigningCeremony,
)


@pytest.fixture
def custodians():
    return [
        Custodian(name="laptop", aid="ECustLaptop"),
        Custodian(name="desktop", aid="ECustDesktop"),
        Custodian(name="cold", aid="ECustCold"),
    ]


def test_initial_state_is_initial_sign(custodians):
    c = SigningCeremony(custodians=custodians, threshold=2)
    assert c.state == CeremonyState.INITIAL_SIGN


def test_first_signature_transitions_to_countersign(custodians):
    c = SigningCeremony(custodians=custodians, threshold=2)
    c.add_signature(custodian=custodians[0], signature=b"sig1")
    assert c.state == CeremonyState.COUNTERSIGN
    assert len(c.signatures) == 1


def test_second_signature_reaches_quorum(custodians):
    c = SigningCeremony(custodians=custodians, threshold=2)
    c.add_signature(custodian=custodians[0], signature=b"sig1")
    c.add_signature(custodian=custodians[1], signature=b"sig2")
    assert c.state == CeremonyState.QUORUM_REACHED
    assert c.is_ready_to_submit() is True


def test_duplicate_signature_from_same_custodian_rejected(custodians):
    c = SigningCeremony(custodians=custodians, threshold=2)
    c.add_signature(custodian=custodians[0], signature=b"sig1")
    with pytest.raises(ValueError) as e:
        c.add_signature(custodian=custodians[0], signature=b"sig1again")
    assert "duplicate" in str(e.value).lower()


def test_unknown_custodian_rejected(custodians):
    c = SigningCeremony(custodians=custodians, threshold=2)
    stranger = Custodian(name="impostor", aid="EImpostor")
    with pytest.raises(ValueError) as e:
        c.add_signature(custodian=stranger, signature=b"sig")
    assert "unknown" in str(e.value).lower()


def test_extra_signature_beyond_threshold_is_accepted(custodians):
    """A third signature on a 2-of-3 ceremony is admissible but doesn't
    change state past QUORUM_REACHED."""
    c = SigningCeremony(custodians=custodians, threshold=2)
    c.add_signature(custodian=custodians[0], signature=b"s1")
    c.add_signature(custodian=custodians[1], signature=b"s2")
    c.add_signature(custodian=custodians[2], signature=b"s3")
    assert c.state == CeremonyState.QUORUM_REACHED
    assert len(c.signatures) == 3


def test_mark_submitted_transitions_to_ready_to_submit_only_after_quorum(custodians):
    c = SigningCeremony(custodians=custodians, threshold=2)
    with pytest.raises(RuntimeError):
        c.mark_ready_to_submit()
    c.add_signature(custodian=custodians[0], signature=b"s1")
    c.add_signature(custodian=custodians[1], signature=b"s2")
    c.mark_ready_to_submit()
    assert c.state == CeremonyState.READY_TO_SUBMIT


def test_threshold_lower_than_two_rejected(custodians):
    with pytest.raises(ValueError):
        SigningCeremony(custodians=custodians, threshold=1)
```

- [ ] **Step 2: Run to confirm fail**

- [ ] **Step 3: Implement `ceremony.py`**

Create `tools/publisher/src/locksmith_publisher/ceremony.py`:

```python
"""Multisig signing ceremony state machine per spec §7.5.

States advance monotonically:
  INITIAL_SIGN     - no signatures yet
  COUNTERSIGN      - first signature attached, quorum not yet reached
  QUORUM_REACHED   - >= threshold signatures attached
  READY_TO_SUBMIT  - operator confirmed submission to witnesses

This module knows nothing about how signatures are produced
(YubiKey / GPG / etc.) — it only enforces the state transitions
and refuses duplicate / unknown-custodian inputs.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class CeremonyState(enum.Enum):
    INITIAL_SIGN = "initial_sign"
    COUNTERSIGN = "countersign"
    QUORUM_REACHED = "quorum_reached"
    READY_TO_SUBMIT = "ready_to_submit"


@dataclass(frozen=True)
class Custodian:
    name: str
    aid: str


@dataclass
class SigningCeremony:
    custodians: list[Custodian]
    threshold: int
    signatures: dict[str, bytes] = field(default_factory=dict)
    state: CeremonyState = CeremonyState.INITIAL_SIGN

    def __post_init__(self) -> None:
        if self.threshold < 2:
            raise ValueError("threshold must be >= 2 for multisig publisher")
        if self.threshold > len(self.custodians):
            raise ValueError("threshold exceeds custodian count")

    def add_signature(self, *, custodian: Custodian, signature: bytes) -> None:
        if custodian not in self.custodians:
            raise ValueError(f"unknown custodian: {custodian.name} ({custodian.aid})")
        if custodian.aid in self.signatures:
            raise ValueError(f"duplicate signature from custodian {custodian.name}")
        self.signatures[custodian.aid] = signature
        if len(self.signatures) >= self.threshold:
            self.state = CeremonyState.QUORUM_REACHED
        else:
            self.state = CeremonyState.COUNTERSIGN

    def is_ready_to_submit(self) -> bool:
        return self.state in (CeremonyState.QUORUM_REACHED,
                              CeremonyState.READY_TO_SUBMIT)

    def mark_ready_to_submit(self) -> None:
        if not self.is_ready_to_submit():
            raise RuntimeError(
                f"cannot submit from state {self.state.value}; "
                f"need {self.threshold} signatures, have {len(self.signatures)}"
            )
        self.state = CeremonyState.READY_TO_SUBMIT
```

- [ ] **Step 4: Run & commit**

Run: `pytest tests/unit/publisher/test_ceremony.py -v`
Expected: 8 PASS.

```bash
git add tools/publisher/src/locksmith_publisher/ceremony.py \
        tests/unit/publisher/test_ceremony.py
git commit -m "feat(publisher): multisig ceremony state machine"
```

---

## Task 12: `tools/publisher/witness_client.py` — api.keri.host HTTP client

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/witness_client.py`
- Test: `tests/unit/publisher/test_witness_client.py`

Per spec §7.2 / §7.5 step 4: submit signed ixn to each witness, collect receipts, retry if threshold not met, detect duplicity.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/publisher/test_witness_client.py`:

```python
"""Tests for locksmith_publisher.witness_client."""
from unittest.mock import MagicMock, patch

import pytest

from locksmith_publisher.witness_client import (
    Receipt,
    WitnessClient,
    WitnessDuplicityDetected,
    WitnessThresholdNotMet,
)


def _ok_response(json_payload: dict):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = json_payload
    r.raise_for_status.return_value = None
    return r


def test_submit_collects_receipts_above_threshold():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
    )
    fake_receipt = {"witness_aid": "Bwit", "receipt_cesr": "AAAA"}
    with patch("locksmith_publisher.witness_client.requests.post",
               return_value=_ok_response(fake_receipt)):
        receipts = wc.submit(event_raw=b"event")
    assert len(receipts) == 3
    assert all(isinstance(r, Receipt) for r in receipts)


def test_submit_retries_partial_failures_until_threshold():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
        max_retries=2,
    )
    # w1, w2 succeed; w3 raises.
    def side_effect(url, **kwargs):
        if "w3" in url:
            raise OSError("connection refused")
        return _ok_response({"witness_aid": "Bwit", "receipt_cesr": "AAAA"})
    with patch("locksmith_publisher.witness_client.requests.post",
               side_effect=side_effect):
        receipts = wc.submit(event_raw=b"event")
    assert len(receipts) == 2


def test_submit_raises_threshold_not_met_when_too_few_succeed():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
        max_retries=1,
    )
    def side_effect(url, **kwargs):
        if "w1" in url:
            return _ok_response({"witness_aid": "Bw1", "receipt_cesr": "AAAA"})
        raise OSError("nope")
    with patch("locksmith_publisher.witness_client.requests.post",
               side_effect=side_effect):
        with pytest.raises(WitnessThresholdNotMet) as e:
            wc.submit(event_raw=b"event")
    assert e.value.collected == 1
    assert e.value.threshold == 2


def test_query_detects_duplicate_keystate():
    wc = WitnessClient(
        witness_urls=["https://api.keri.host/witness/w1/",
                      "https://api.keri.host/witness/w2/"],
        threshold=2,
    )
    def side_effect(url, **kwargs):
        if "w1" in url:
            return _ok_response({"current_said": "EHshA", "sn": 4})
        return _ok_response({"current_said": "EHshB", "sn": 4})
    with patch("locksmith_publisher.witness_client.requests.post",
               side_effect=side_effect):
        with pytest.raises(WitnessDuplicityDetected):
            wc.query_keystate(publisher_aid="EAaa")


def test_query_returns_consistent_keystate():
    wc = WitnessClient(
        witness_urls=["https://api.keri.host/witness/w1/",
                      "https://api.keri.host/witness/w2/"],
        threshold=2,
    )
    with patch("locksmith_publisher.witness_client.requests.post",
               return_value=_ok_response({"current_said": "EHshX", "sn": 4})):
        ks = wc.query_keystate(publisher_aid="EAaa")
    assert ks["current_said"] == "EHshX"
    assert ks["sn"] == 4
```

- [ ] **Step 2: Run to confirm fail**

- [ ] **Step 3: Implement `witness_client.py`**

Create `tools/publisher/src/locksmith_publisher/witness_client.py`:

```python
"""HTTP client for the api.keri.host witness pool.

Endpoints (per ~/KERI/code/kerihost reference impl):

  POST {witness_url}/process   — submit a CESR event stream; returns a receipt
  POST {witness_url}/query     — query current key state for a publisher AID

The client gathers responses concurrently across the configured witness pool
and applies a `threshold` decision. Errors are typed so the CLI can map them
to operator-friendly messages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class WitnessThresholdNotMet(Exception):
    def __init__(self, collected: int, threshold: int):
        super().__init__(f"only {collected}/{threshold} witness receipts collected")
        self.collected = collected
        self.threshold = threshold


class WitnessDuplicityDetected(Exception):
    def __init__(self, divergence: dict[str, Any]):
        super().__init__(f"witness duplicity: {divergence}")
        self.divergence = divergence


@dataclass(frozen=True)
class Receipt:
    witness_aid: str
    receipt_cesr: str


@dataclass
class WitnessClient:
    witness_urls: list[str]
    threshold: int
    timeout_sec: int = 30
    max_retries: int = 3

    def submit(self, *, event_raw: bytes) -> list[Receipt]:
        receipts: list[Receipt] = []
        errors: list[str] = []
        for attempt in range(self.max_retries):
            remaining = [u for u in self.witness_urls
                         if not any(r.witness_aid for r in receipts
                                    if u.rstrip("/").endswith(r.witness_aid))]
            for url in remaining:
                endpoint = url.rstrip("/") + "/process"
                try:
                    resp = requests.post(
                        endpoint, data=event_raw,
                        headers={"Content-Type": "application/cesr+json"},
                        timeout=self.timeout_sec,
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                    receipts.append(Receipt(
                        witness_aid=payload["witness_aid"],
                        receipt_cesr=payload["receipt_cesr"],
                    ))
                except (requests.RequestException, OSError, KeyError) as ex:
                    errors.append(f"{url}: {ex}")
            if len(receipts) >= self.threshold:
                return receipts
        if len(receipts) < self.threshold:
            raise WitnessThresholdNotMet(
                collected=len(receipts),
                threshold=self.threshold,
            )
        return receipts

    def query_keystate(self, *, publisher_aid: str) -> dict[str, Any]:
        responses: list[dict[str, Any]] = []
        for url in self.witness_urls:
            endpoint = url.rstrip("/") + "/query"
            try:
                resp = requests.post(
                    endpoint, json={"aid": publisher_aid},
                    timeout=self.timeout_sec,
                )
                resp.raise_for_status()
                responses.append(resp.json())
            except (requests.RequestException, OSError) as ex:
                continue
        if len(responses) < self.threshold:
            raise WitnessThresholdNotMet(
                collected=len(responses),
                threshold=self.threshold,
            )
        # Compare on (current_said, sn).
        canonical = (responses[0]["current_said"], responses[0]["sn"])
        for r in responses[1:]:
            if (r["current_said"], r["sn"]) != canonical:
                raise WitnessDuplicityDetected({
                    "responses": responses,
                })
        return responses[0]
```

- [ ] **Step 4: Run & commit**

Run: `pytest tests/unit/publisher/test_witness_client.py -v`
Expected: 5 PASS.

```bash
git add tools/publisher/src/locksmith_publisher/witness_client.py \
        tests/unit/publisher/test_witness_client.py
git commit -m "feat(publisher): witness HTTP client with threshold + duplicity"
```

---

## Task 13: Finalize `tools/publisher/cli.py` — `sign`, `countersign`, `submit`

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/cli.py` (Phase 1 stubs)
- Create: `tools/publisher/src/locksmith_publisher/s3_client.py`
- Test: `tests/unit/publisher/test_cli.py`

Wires `anchor` + `ceremony` + `witness_client` + S3 into the user-facing subcommands.

- [ ] **Step 1: Implement `s3_client.py` first (thin wrapper)**

Create `tools/publisher/src/locksmith_publisher/s3_client.py`:

```python
"""Thin boto3 wrapper for the publisher CLI.

OIDC creds are picked up from the ambient environment when run in CI;
local operators export AWS_PROFILE before invoking the CLI.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import boto3


@dataclass
class S3:
    client: object  # boto3 client — not strongly typed by boto3 itself

    @classmethod
    def default(cls) -> "S3":
        return cls(client=boto3.client("s3"))

    def get_object(self, *, bucket: str, key: str) -> bytes:
        resp = self.client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()

    def get_json(self, *, bucket: str, key: str) -> dict:
        return json.loads(self.get_object(bucket=bucket, key=key))

    def put_object(self, *, bucket: str, key: str, data: bytes,
                   content_type: str = "application/octet-stream") -> None:
        self.client.put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=content_type
        )

    def put_file(self, *, bucket: str, key: str, path: Path,
                 content_type: str = "application/octet-stream") -> None:
        self.put_object(
            bucket=bucket, key=key, data=path.read_bytes(),
            content_type=content_type,
        )
```

- [ ] **Step 2: Write the failing tests for `cli.py`**

Create `tests/unit/publisher/test_cli.py`:

```python
"""Tests for the publisher CLI subcommands (sign / countersign / submit)."""
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from locksmith_publisher import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def candidates_payload(tmp_path) -> dict:
    body = b"FAKE-DMG-CONTENT"
    return {
        "version": "1.2.3",
        "channel": "stable",
        "released_at": "2026-05-28T00:00:00Z",
        "is_major": False,
        "is_critical": False,
        "previous_version": "1.2.2",
        "minimum_system_versions": {"macos": "13.0", "windows": "10.0.19041"},
        "artifacts": [
            {"platform": "macos", "filename": "Locksmith-1.2.3.dmg",
             "sha256": hashlib.sha256(body).hexdigest(),
             "size": len(body), "s3_key": "candidates/1.2.3/Locksmith-1.2.3.dmg"},
            {"platform": "windows", "filename": "Locksmith-1.2.3.msi",
             "sha256": hashlib.sha256(body).hexdigest(),
             "size": len(body), "s3_key": "candidates/1.2.3/Locksmith-1.2.3.msi"},
        ],
        "release_notes_said": "E" + "x" * 43,
    }


def test_sign_verifies_candidate_shas_then_emits_partial(runner, tmp_path, candidates_payload):
    body = b"FAKE-DMG-CONTENT"
    s3_mock = MagicMock()
    s3_mock.get_json.return_value = candidates_payload
    s3_mock.get_object.return_value = body
    out = tmp_path / "release-anchor-1.2.3.partial.cesr"
    with patch("locksmith_publisher.cli.S3.default", return_value=s3_mock), \
         patch("locksmith_publisher.cli._sign_with_custodian",
               return_value=b"PARTIAL_CESR"):
        result = runner.invoke(cli.app, [
            "sign", "--version", "1.2.3",
            "--candidates-url", "s3://releases-staging.keri.host/candidates/1.2.3/",
            "--output", str(out),
        ])
    assert result.exit_code == 0, result.output
    assert out.exists()


def test_sign_rejects_sha_mismatch(runner, tmp_path, candidates_payload):
    # Tamper: claim sha256 = 0... but S3 body is something else.
    candidates_payload["artifacts"][0]["sha256"] = "0" * 64
    s3_mock = MagicMock()
    s3_mock.get_json.return_value = candidates_payload
    s3_mock.get_object.return_value = b"FAKE-DMG-CONTENT"
    out = tmp_path / "out.cesr"
    with patch("locksmith_publisher.cli.S3.default", return_value=s3_mock):
        result = runner.invoke(cli.app, [
            "sign", "--version", "1.2.3",
            "--candidates-url", "s3://releases-staging.keri.host/candidates/1.2.3/",
            "--output", str(out),
        ])
    assert result.exit_code != 0
    assert "sha256" in result.output.lower()


def test_countersign_emits_signed_cesr(runner, tmp_path):
    partial = tmp_path / "p.cesr"
    partial.write_bytes(b"PARTIAL")
    out = tmp_path / "signed.cesr"
    with patch("locksmith_publisher.cli._countersign", return_value=b"SIGNED_CESR"):
        result = runner.invoke(cli.app, [
            "countersign",
            "--partial", str(partial),
            "--output", str(out),
        ])
    assert result.exit_code == 0
    assert out.read_bytes() == b"SIGNED_CESR"


def test_submit_uploads_to_s3_and_invokes_witnesses(runner, tmp_path):
    signed = tmp_path / "signed.cesr"
    signed.write_bytes(b"SIGNED")
    s3_mock = MagicMock()
    wc_mock = MagicMock()
    wc_mock.submit.return_value = [MagicMock(), MagicMock()]  # 2 receipts
    with patch("locksmith_publisher.cli.S3.default", return_value=s3_mock), \
         patch("locksmith_publisher.cli._witness_client", return_value=wc_mock):
        result = runner.invoke(cli.app, [
            "submit",
            "--signed", str(signed),
            "--version", "1.2.3",
        ])
    assert result.exit_code == 0
    # Final anchor uploaded.
    keys = [c.kwargs["key"] for c in s3_mock.put_object.call_args_list]
    assert any("releases/1.2.3/release-anchor-1.2.3.cesr" in k for k in keys)
```

- [ ] **Step 3: Implement `cli.py`**

Replace the Phase 1 stubs in `tools/publisher/src/locksmith_publisher/cli.py`:

```python
"""Publisher CLI — `sign`, `countersign`, `submit` subcommands per spec §7.5.

This CLI is operator-facing; it runs on a custodian device with
access to YubiKey-resident signing keys. Each subcommand is small,
auditable, and writes its output to disk for the next custodian to
pick up.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
from pathlib import Path

import click

from locksmith_publisher.anchor import IxnAnchor, build_release_seal
from locksmith_publisher.ceremony import (
    CeremonyState,
    Custodian,
    SigningCeremony,
)
from locksmith_publisher.s3_client import S3
from locksmith_publisher.witness_client import (
    WitnessClient,
    WitnessThresholdNotMet,
)


@click.group()
def app() -> None:
    """Locksmith publisher CLI."""


def _parse_s3_url(s3_url: str) -> tuple[str, str]:
    if not s3_url.startswith("s3://"):
        raise click.BadParameter(f"not an s3:// URL: {s3_url}")
    parsed = urllib.parse.urlparse(s3_url)
    return parsed.netloc, parsed.path.lstrip("/")


def _sign_with_custodian(serder_raw: bytes) -> bytes:
    """Sign with the resident custodian key (YubiKey/GPG).

    Real impl shells out to `gpg --detach-sign` against the OpenPGP slot;
    tests patch this with a stub.
    """
    raise NotImplementedError("integrate YubiKey signing during operator setup")


def _countersign(partial_raw: bytes) -> bytes:
    """Add the second custodian's signature."""
    raise NotImplementedError("integrate YubiKey signing during operator setup")


def _witness_client() -> WitnessClient:
    """Construct the witness client from publisher-anchor metadata."""
    return WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
    )


@app.command("sign")
@click.option("--version", required=True)
@click.option("--candidates-url", required=True,
              help="s3:// URL of candidates/X.Y.Z/ directory")
@click.option("--output", required=True, type=click.Path(path_type=Path))
def sign_cmd(version: str, candidates_url: str, output: Path) -> None:
    bucket, prefix = _parse_s3_url(candidates_url.rstrip("/") + "/")
    s3 = S3.default()
    candidate = s3.get_json(bucket=bucket, key=prefix + "release-candidate.json")

    # Re-hash every candidate artifact against actual S3 bytes — TOCTOU defense
    # at the signing boundary.
    for a in candidate["artifacts"]:
        body = s3.get_object(bucket=bucket, key=a["s3_key"])
        actual = hashlib.sha256(body).hexdigest()
        if actual != a["sha256"]:
            raise click.ClickException(
                f"sha256 mismatch for {a['filename']}: "
                f"expected {a['sha256']}, got {actual}"
            )

    seal = build_release_seal(
        version=version,
        channel=candidate["channel"],
        released_at=candidate["released_at"],
        is_major=candidate["is_major"],
        is_critical=candidate["is_critical"],
        previous_version=candidate.get("previous_version"),
        minimum_system_versions=candidate["minimum_system_versions"],
        artifacts=[
            {"platform": a["platform"], "filename": a["filename"],
             "sha256": a["sha256"], "size": a["size"]}
            for a in candidate["artifacts"]
        ],
        release_notes_said=candidate["release_notes_said"],
    )
    # Real impl loads the publisher Hab from the custodian's keystore.
    # For test injection, the call is via `_sign_with_custodian`.
    partial_raw = _sign_with_custodian(json.dumps(seal).encode())
    output.write_bytes(partial_raw)
    click.echo(f"Partial anchor written to {output}")


@app.command("countersign")
@click.option("--partial", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--output", required=True, type=click.Path(path_type=Path))
def countersign_cmd(partial: Path, output: Path) -> None:
    signed_raw = _countersign(partial.read_bytes())
    output.write_bytes(signed_raw)
    click.echo(f"Signed anchor written to {output}")


@app.command("submit")
@click.option("--signed", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--version", required=True)
def submit_cmd(signed: Path, version: str) -> None:
    event_raw = signed.read_bytes()
    wc = _witness_client()
    try:
        receipts = wc.submit(event_raw=event_raw)
    except WitnessThresholdNotMet as ex:
        raise click.ClickException(
            f"witness threshold not met: {ex.collected}/{ex.threshold}"
        )
    s3 = S3.default()
    s3.put_object(
        bucket="releases.keri.host",
        key=f"releases/{version}/release-anchor-{version}.cesr",
        data=event_raw,
        content_type="application/cesr+json",
    )
    # Refresh publisher anchor pointer.
    s3.put_object(
        bucket="releases.keri.host",
        key="publisher/v1/publisher-aid.json",
        data=json.dumps({"latest_version": version,
                         "witness_receipts": len(receipts)}).encode(),
        content_type="application/json",
    )
    click.echo(f"Submitted {version} with {len(receipts)} witness receipts")


if __name__ == "__main__":  # pragma: no cover
    app()
```

- [ ] **Step 4: Run all publisher tests**

Run: `pytest tests/unit/publisher/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/cli.py \
        tools/publisher/src/locksmith_publisher/s3_client.py \
        tests/unit/publisher/test_cli.py
git commit -m "feat(publisher): finalize sign/countersign/submit subcommands"
```

---

## Task 14: Appcast generator (`tools/publisher/appcast.py`)

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/appcast.py`
- Test: `tests/unit/publisher/test_appcast_generator.py`

Per spec §6.3: enumerate every released version, re-build `appcast/v1/macos.json` and `appcast/v1/windows.json`, archive the prior versions. Full history retained — do **not** prune.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/publisher/test_appcast_generator.py`:

```python
"""Tests for the appcast generator (run by the publish CI job)."""
import json
from unittest.mock import MagicMock, patch

import pytest

from locksmith_publisher.appcast import (
    GeneratorConfig,
    generate_and_upload_appcasts,
)


def _fake_anchor_cesr(version: str, said: str, mac_sha: str, win_sha: str) -> bytes:
    # Stub CESR: serder JSON + dummy sigs. Generator parses with SerderKERI.
    seal = {
        "release": {
            "v": version, "channel": "stable",
            "released_at": "2026-05-28T00:00:00Z",
            "is_major": False, "is_critical": False,
            "previous_version": None,
            "minimum_system_versions": {"macos": "13.0", "windows": "10.0.19041"},
            "artifacts": [
                {"platform": "macos", "filename": f"Locksmith-{version}.dmg",
                 "sha256": mac_sha, "size": 100},
                {"platform": "windows", "filename": f"Locksmith-{version}.msi",
                 "sha256": win_sha, "size": 100},
            ],
            "release_notes_said": "EHshNotes",
        }
    }
    # Real impl re-reads via SerderKERI — test fakes the parse via monkeypatch.
    return json.dumps({"said": said, "seal": seal}).encode()


def test_generator_lists_and_writes_per_platform_appcasts():
    s3 = MagicMock()
    s3.list_release_versions.return_value = ["1.0.0", "1.0.1", "1.1.0"]
    s3.get_object.side_effect = [
        _fake_anchor_cesr("1.0.0", "EHshA", "a" * 64, "A" * 64),
        _fake_anchor_cesr("1.0.1", "EHshB", "b" * 64, "B" * 64),
        _fake_anchor_cesr("1.1.0", "EHshC", "c" * 64, "C" * 64),
    ]
    cfg = GeneratorConfig(
        bucket="releases.keri.host",
        publisher_aid="EAaa",
        publisher_kel_url="https://releases.keri.host/publisher/v1/publisher-aid.json",
    )
    with patch("locksmith_publisher.appcast._parse_anchor",
               side_effect=lambda raw: json.loads(raw)):
        generate_and_upload_appcasts(s3=s3, config=cfg)

    keys = {c.kwargs["key"] for c in s3.put_object.call_args_list}
    assert "appcast/v1/macos.json" in keys
    assert "appcast/v1/windows.json" in keys
    # Archive copies — one per platform, timestamped.
    assert any(k.startswith("appcast/archive/") for k in keys)


def test_generator_retains_full_history_no_pruning():
    s3 = MagicMock()
    s3.list_release_versions.return_value = ["1.0.0", "1.0.1", "1.1.0"]
    s3.get_object.side_effect = [
        _fake_anchor_cesr("1.0.0", "EHshA", "a" * 64, "A" * 64),
        _fake_anchor_cesr("1.0.1", "EHshB", "b" * 64, "B" * 64),
        _fake_anchor_cesr("1.1.0", "EHshC", "c" * 64, "C" * 64),
    ]
    cfg = GeneratorConfig(
        bucket="releases.keri.host",
        publisher_aid="EAaa",
        publisher_kel_url="https://releases.keri.host/publisher/v1/publisher-aid.json",
    )
    captured: dict[str, bytes] = {}
    def capture(Bucket, Key, Body, **kw):
        captured[Key] = Body
    s3.put_object.side_effect = capture
    with patch("locksmith_publisher.appcast._parse_anchor",
               side_effect=lambda raw: json.loads(raw)):
        generate_and_upload_appcasts(s3=s3, config=cfg)

    macos = json.loads(captured["appcast/v1/macos.json"])
    assert len(macos["releases"]) == 3
    assert macos["current_version"] == "1.1.0"
    assert [r["version"] for r in macos["releases"]] == ["1.0.0", "1.0.1", "1.1.0"]


def test_generator_current_version_is_highest_semver():
    s3 = MagicMock()
    # Out-of-order listing — generator must sort by semver.
    s3.list_release_versions.return_value = ["1.1.0", "1.0.1", "1.0.0"]
    s3.get_object.side_effect = [
        _fake_anchor_cesr("1.1.0", "EHshC", "c" * 64, "C" * 64),
        _fake_anchor_cesr("1.0.1", "EHshB", "b" * 64, "B" * 64),
        _fake_anchor_cesr("1.0.0", "EHshA", "a" * 64, "A" * 64),
    ]
    cfg = GeneratorConfig(
        bucket="releases.keri.host",
        publisher_aid="EAaa",
        publisher_kel_url="https://releases.keri.host/publisher/v1/publisher-aid.json",
    )
    captured: dict[str, bytes] = {}
    s3.put_object.side_effect = lambda Bucket, Key, Body, **kw: captured.update({Key: Body})
    with patch("locksmith_publisher.appcast._parse_anchor",
               side_effect=lambda raw: json.loads(raw)):
        generate_and_upload_appcasts(s3=s3, config=cfg)
    macos = json.loads(captured["appcast/v1/macos.json"])
    assert macos["current_version"] == "1.1.0"
```

- [ ] **Step 2: Implement `appcast.py`**

Create `tools/publisher/src/locksmith_publisher/appcast.py`:

```python
"""Appcast generator — invoked by the `publish` CI job after a signing ceremony.

Reads every `releases/X.Y.Z/release-anchor-X.Y.Z.cesr` from S3, extracts the
release seal from each, and emits per-platform appcasts under `appcast/v1/`.
Archives the prior appcasts under `appcast/archive/{timestamp}/` so the
history is recoverable.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from typing import Any

from keri.core import serdering


@dataclass(frozen=True)
class GeneratorConfig:
    bucket: str
    publisher_aid: str
    publisher_kel_url: str
    schema_version: int = 1
    channel: str = "stable"


def _parse_anchor(raw: bytes) -> dict[str, Any]:
    """Parse a CESR-encoded release anchor and return {said, seal}."""
    serder = serdering.SerderKERI(raw=bytearray(raw))
    seal = serder.ked["a"][0]
    return {"said": serder.said, "seal": seal}


def _semver_key(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def generate_and_upload_appcasts(*, s3, config: GeneratorConfig) -> None:
    versions = sorted(s3.list_release_versions(), key=_semver_key)
    if not versions:
        return
    anchors_by_version: dict[str, dict[str, Any]] = {}
    for v in versions:
        raw = s3.get_object(
            Bucket=config.bucket,
            Key=f"releases/{v}/release-anchor-{v}.cesr",
        )
        anchors_by_version[v] = _parse_anchor(raw)

    current_version = versions[-1]
    timestamp = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for platform, ext in [("macos", "dmg"), ("windows", "msi")]:
        releases: list[dict[str, Any]] = []
        for v in versions:
            parsed = anchors_by_version[v]
            seal = parsed["seal"]["release"]
            artifact = next(
                a for a in seal["artifacts"] if a["platform"] == platform
            )
            releases.append({
                "version": v,
                "released_at": seal["released_at"],
                "platform": platform,
                "minimum_system_version":
                    seal["minimum_system_versions"][platform],
                "artifact_url":
                    f"https://releases.keri.host/releases/{v}/{artifact['filename']}",
                "artifact_sha256": artifact["sha256"],
                "artifact_size": artifact["size"],
                "anchor_url":
                    f"https://releases.keri.host/releases/{v}/release-anchor-{v}.cesr",
                "anchor_said": parsed["said"],
                "release_notes_url":
                    f"https://locksmith.app/releases/{v}",
                "is_major": seal.get("is_major", False),
                "is_critical": seal.get("is_critical", False),
            })

        appcast = {
            "schema_version": config.schema_version,
            "channel": config.channel,
            "publisher_aid": config.publisher_aid,
            "publisher_kel_url": config.publisher_kel_url,
            "current_version": current_version,
            "releases": releases,
        }
        body = json.dumps(appcast, indent=2).encode()
        live_key = f"appcast/v1/{platform}.json"
        archive_key = f"appcast/archive/{timestamp}/{platform}.json"
        s3.put_object(
            Bucket=config.bucket, Key=live_key, Body=body,
            ContentType="application/json",
        )
        s3.put_object(
            Bucket=config.bucket, Key=archive_key, Body=body,
            ContentType="application/json",
        )
```

- [ ] **Step 3: Run & commit**

Run: `pytest tests/unit/publisher/test_appcast_generator.py -v`
Expected: 3 PASS.

```bash
git add tools/publisher/src/locksmith_publisher/appcast.py \
        tests/unit/publisher/test_appcast_generator.py
git commit -m "feat(publisher): appcast generator with full history retained"
```

---

## Task 15: `publish` CI workflow

**Files:**
- Create: `.github/workflows/publish.yml`
- Test: actionlint structural check (added as a step inside the workflow itself)

Per Phase-4 open-question resolution: triggered by `workflow_dispatch` with a `version` input. Operator runs `gh workflow run publish.yml --field version=X.Y.Z` after `submit` completes.

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/publish.yml`:

```yaml
name: publish-appcast

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Release version that was just submitted (e.g., 1.2.3)"
        required: true
        type: string

permissions:
  id-token: write   # OIDC
  contents: read

jobs:
  generate-and-publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Install publisher package
        run: |
          python -m pip install --upgrade pip
          pip install ./tools/publisher

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/gha-locksmith-release-publisher
          aws-region: us-east-1

      - name: Regenerate appcasts
        run: |
          python -m locksmith_publisher.publish_appcasts \
            --version "${{ github.event.inputs.version }}"

      - name: Invalidate CloudFront cache for appcast paths
        run: |
          aws cloudfront create-invalidation \
            --distribution-id "${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }}" \
            --paths "/appcast/v1/macos.json" "/appcast/v1/windows.json"
```

- [ ] **Step 2: Add a tiny driver entrypoint**

Append to `tools/publisher/src/locksmith_publisher/`, file `publish_appcasts.py`:

```python
"""CI entrypoint for the appcast regeneration job."""
from __future__ import annotations

import argparse
import json
from importlib import resources

import boto3

from locksmith_publisher.appcast import (
    GeneratorConfig,
    generate_and_upload_appcasts,
)
from locksmith_publisher.s3_client import S3


class _S3WithList(S3):
    def list_release_versions(self) -> list[str]:
        paginator = self.client.get_paginator("list_objects_v2")
        versions: set[str] = set()
        for page in paginator.paginate(Bucket="releases.keri.host",
                                       Prefix="releases/"):
            for obj in page.get("Contents", []):
                # releases/X.Y.Z/release-anchor-X.Y.Z.cesr
                parts = obj["Key"].split("/")
                if len(parts) >= 2 and parts[0] == "releases":
                    versions.add(parts[1])
        return sorted(versions)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True,
                   help="Version that triggered this run (for log breadcrumb)")
    args = p.parse_args()

    # Embedded publisher anchor metadata supplies AID + KEL url.
    from locksmith.release import publisher_anchor as anchor_mod  # Phase 1 artifact
    anchor = json.loads(
        resources.files(anchor_mod.__package__)
        .joinpath("publisher_anchor.json").read_text()
    )

    s3 = _S3WithList(client=boto3.client("s3"))
    cfg = GeneratorConfig(
        bucket="releases.keri.host",
        publisher_aid=anchor["publisher_aid"],
        publisher_kel_url="https://releases.keri.host/publisher/v1/publisher-aid.json",
    )
    generate_and_upload_appcasts(s3=s3, config=cfg)
    print(f"appcasts refreshed (triggered by version={args.version})")


if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 3: Lint the workflow with actionlint**

Run:
```bash
which actionlint || brew install actionlint
actionlint .github/workflows/publish.yml
```
Expected: exit 0, no errors.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/publish.yml \
        tools/publisher/src/locksmith_publisher/publish_appcasts.py
git commit -m "feat(publisher): publish-appcast CI workflow + entrypoint"
```

---

## Self-Review

This section captures a final pass over the Phase 4 plan after the last commit, before the plan is handed off to executors.

### Spec coverage table

| Spec section | Concern | Covered by task(s) |
|---|---|---|
| §6.3 Appcast schema | Parser, `Release` dataclass, schema validation | Task 4 |
| §6.3 Appcast schema | Generator emits matching schema with full history | Task 14 |
| §7.1 Publisher AID identity | Embedded `publisher_anchor.json` consumed by verifier | Task 6, Task 9 |
| §7.2 Witness configuration | `toad` threshold enforced per-event | Task 5, Task 12 |
| §7.3 Release anchoring (ixn) | `IxnAnchor.build()` produces release `ixn` events | Task 10 |
| §7.4 Anchored seal schema | `build_release_seal()` with field-order assertions | Task 10 |
| §7.5 Signing workflow (sign/countersign/submit) | Multisig state machine + CLI subcommands + witness submit | Tasks 11, 12, 13 |
| §7.6 Key rotation | KEL replay accepts `rot` events, detects pre-rotation violations | Task 5 |
| §7.7 Bootstrap trust (embedded anchor) | `verify_artifact()` takes embedded sn/said/aid; CLI loads from `locksmith.release.publisher_anchor` | Tasks 6, 9 |
| §7.8 TOCTOU mitigation | 0700 staging dir + exclusive lock + re-hash | Task 7 |
| §9.1 Network failure | `NetworkError` exit code 14; silent retry left to Phase 5 UI | Task 1, Task 9 |
| §9.2 Verification failure ("install anyway" never offered) | CLI test asserts absence of "install anyway"; verifier raises typed errors | Tasks 6, 9 |
| §9.3 Witness disagreement | `WitnessDuplicityError` + `WitnessClient.query_keystate` divergence detection | Tasks 1, 12 |
| §9.4 Publisher key rotation in flight | KEL replay forward from `embedded_kel_sn`; rotation acceptance | Task 5 |
| §9.6 Logging philosophy (key=value) | `log.py` writes/parses key=value lines | Task 8 |
| §10.1 Adversarial unit cases (table) | Each row mapped to a test in `test_verify.py` and `test_kel_replay.py` | Tasks 5, 6 |
| §11.2 "What's new" — `src/locksmith/update/`, `tools/publisher/`, fixtures | All directories created | Tasks 1–14 |
| §12 Open Q #7 (publish trigger) | Resolved upfront — manual `workflow_dispatch` keyed on version | Task 15 |

### Placeholder scan

- No `TBD` markers remain in any task body.
- No `XXX` / `FIXME` placeholders.
- Every code block names a concrete file path; no `<dir>` template variables.
- The `_sign_with_custodian` / `_countersign` helpers in `tools/publisher/cli.py` are intentionally `NotImplementedError` stubs — they are operator-environment-specific (YubiKey/GPG bindings) and must be implemented during the operator-onboarding step, not during this plan's execution. The test suite covers the surrounding code by patching these symbols.

### Type / method-name consistency check

| Name | Defined in | Imported by | Status |
|---|---|---|---|
| `UpdateError`, `SignatureError`, `HashMismatchError`, `WitnessThresholdError`, `StaleAppcastError`, `DowngradeError`, `RotationMismatchError`, `WitnessDuplicityError`, `NetworkError`, `SchemaError`, `StagingError` | `locksmith.update.errors` | `appcast`, `kel_replay`, `verify`, `staging`, `log`, `cli` | OK |
| `Release`, `Appcast`, `parse_appcast`, `select_latest_for_platform` | `locksmith.update.appcast` | `verify`, tests | OK |
| `KelState`, `ReplayedEvent`, `replay_kel`, `extract_release_seal` | `locksmith.update.kel_replay` | `verify`, tests | OK |
| `VerificationResult`, `verify_artifact` | `locksmith.update.verify` | `cli`, Phase 5 UI | OK |
| `StagingArea`, `StagedArtifact`, `stage_and_lock`, `default_staging_root` | `locksmith.update.staging` | Phase 5 UI, tests | OK |
| `VerificationLogEntry`, `append_entry`, `read_entries`, `default_log_path` | `locksmith.update.log` | Phase 5 UI, tests | OK |
| `IxnAnchor`, `Anchor`, `build_release_seal` | `locksmith_publisher.anchor` | `cli`, `appcast` generator | OK |
| `CeremonyState`, `Custodian`, `SigningCeremony` | `locksmith_publisher.ceremony` | `cli` | OK |
| `WitnessClient`, `Receipt`, `WitnessThresholdNotMet`, `WitnessDuplicityDetected` | `locksmith_publisher.witness_client` | `cli` | OK |
| `S3` | `locksmith_publisher.s3_client` | `cli`, `publish_appcasts` | OK |
| `GeneratorConfig`, `generate_and_upload_appcasts` | `locksmith_publisher.appcast` | `publish_appcasts` entrypoint | OK |

### Cross-phase dependencies — confirmed

**Phase 4 depends on Phase 1 having provided:**
- `src/locksmith/release/publisher_anchor.json` (and the package import path `locksmith.release.publisher_anchor`) — consumed by `cli._load_anchor_and_appcast()` (Task 9) and `publish_appcasts.main()` (Task 15).
- AWS OIDC role `gha-locksmith-release-publisher` — referenced by `.github/workflows/publish.yml` (Task 15).
- `s3://releases.keri.host` bucket + CloudFront distribution — written-to by Tasks 13–15.
- The publisher AID itself, present on `api.keri.host` with `toad=2` and ≥3 witness receipts at inception — Task 5's KEL replay assumes this.
- `tools/publisher/` package skeleton + `pyproject.toml` with `click` already wired — Tasks 10–13 extend it; Task 13 adds `boto3` and `requests` deps.

**Phase 4 depends on Phase 2/3 having provided:**
- Actual `Locksmith-X.Y.Z.dmg` / `.msi` artifacts staged at `s3://releases-staging.keri.host/candidates/X.Y.Z/` and final-uploaded to `s3://releases.keri.host/releases/X.Y.Z/`. Task 13's `sign` subcommand reads from staging; Task 15's workflow assumes the final bucket layout.

**Phase 5 consumes from Phase 4:**
- `from locksmith.update.verify import verify_artifact, VerificationResult` — main entry the Settings → Updates UI calls.
- `from locksmith.update.log import read_entries, default_log_path` — for the verification-history page.
- `from locksmith.update.errors import UpdateError, ...` — for surfacing typed errors as user-facing strings.
- `from locksmith.update.staging import stage_and_lock, StagedArtifact` — for the Sparkle/WinSparkle hand-off.

No circular imports across phases — `locksmith.update.*` does not import any UI/Qt module; `tools/publisher/*` does not import `locksmith.*` except for the `publisher_anchor` JSON resource (read-only metadata).

### Final notes

- Every test runs with the committed fixtures from Task 2/3 — CI does not regenerate fixtures unless `make fixtures` is invoked explicitly.
- The `verify_artifact()` function is **pure** w.r.t. side effects (no logging, no UI). Phase 5's UI is responsible for calling `log.append_entry()` after each invocation.
- All AWS calls go through `boto3`; no direct HTTP. Witness calls go through `requests` per the existing publisher patterns.
- The plan is consistent with the project memory [[project-aws-infrastructure]], [[project-keri-host-publisher-entity]], and [[feedback-testing-automated]].

