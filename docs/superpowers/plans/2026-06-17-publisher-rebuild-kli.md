# Greenfield Publisher Rebuild (kli-based) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Locksmith release publisher as a thin orchestration of stock `kli` commands (`incept`/`interact`/`export`, always `--receipt-endpoint`) + a release-seal builder + S3/appcast glue, so witness receipts and KEL export come from keripy correctly (no wig bug), and the trust anchor ships via a build-injected (uncommitted) file.

**Architecture:** A `publish` module shells out to `kli` for all KERI work and produces three artifacts — the full KEL (`kel.cesr`), each anchor event, and the appcast — matching the existing (correct, unchanged) verifier in `src/locksmith/update/`. The publisher AID is incepted once on a controlled machine; per-release anchoring runs in CI with the keystore+bran as secrets; pre-rotation is the safety net. Real inception/e2e is deferred behind the SAM→CDK federation cutover.

**Tech Stack:** Python, keripy `kli` (subprocess), `boto3`, pytest. Spec: `docs/superpowers/specs/2026-06-17-publisher-rebuild-kli-design.md`.

**Verified contract (do not re-derive):**
- Release seal anchored in the ixn `a` field: `{"release": {"v": "<ver>", "artifacts": [{"platform": "<p>", "sha256": "<hex>"}, ...]}}` (`update/kel_replay.py extract_release_seal` scans `a` for a dict with a `"release"` key; `update/verify.py:199-242` reads `seal["release"]["v"]` and `seal["release"]["artifacts"][n]["sha256"]` per platform).
- Verifier fetches the full KEL from `appcast.publisher_kel_url` (`replay_kel` → Kevery + `db.wigs` toad check) AND each anchor event from `Release.anchor_url` (`verify.py:179`), confirming `SerderKERI(anchor_raw).said == Release.anchor_said`.
- `kli incept`/`kli interact` collect receipts correctly over HTTP ONLY with `--receipt-endpoint` (`src/keri/cli/commands/{incept,interact}.py` → `Receiptor`); the default uses `WitnessReceiptor` and hangs over HTTP.
- `kli export --alias <a> --files` writes `<aid>-kel.cesr` via `db.clonePreIter` (wigs inline) (`src/keri/cli/commands/export.py:88`).

**Worktree:** already created at `~/code/locksmith/.worktrees/publisher-rebuild` (branch `feat/publisher-rebuild`, carries the spec). Run pytest with the main venv + `--import-mode=importlib` (locksmith's top-level `packaging/` dir otherwise shadows the real `packaging`): `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest … --import-mode=importlib`.

---

## File Structure

- `tools/publisher/src/locksmith_publisher/seal.py` — **new**: pure `build_release_seal()` (the publisher↔verifier contract).
- `tools/publisher/src/locksmith_publisher/kli.py` — **new**: subprocess wrappers `kli_incept()`, `kli_interact()`, `kli_export()` (all force `--receipt-endpoint`).
- `tools/publisher/src/locksmith_publisher/publish.py` — **new**: orchestration (build seal → anchor → export → publish artifacts + appcast).
- `tools/publisher/src/locksmith_publisher/appcast.py`, `s3_client.py` — **keep/adapt** (non-key glue).
- `tools/publisher/src/locksmith_publisher/{release_anchor,witness_client,signing_context}.py` — **retire** the KERI-event/receipt parts (Task 7).
- `src/locksmith/release/publisher_anchor.json` — **de-commit**; add `publisher_anchor.example.json`; build-inject the real one (Task 6).
- `tests/integration/test_publisher_roundtrip.py` — **new**: in-process-witness incept→interact→export→`verify_artifact` (the keystone, Task 5).
- Retire masking tests: `tests/unit/publisher/test_round_trip_verify.py`, `tests/fixtures/update/generate.py` `attach_wigs` (Task 7).

---

### Task 0: Worktree venv + baseline

**Files:** none (environment).

- [ ] **Step 1: Confirm kli + deps available** (reuse the main locksmith venv — no fresh install):
```bash
VENV=/Users/seriouscoderone/code/locksmith/.venv
$VENV/bin/kli version            # kli present (from the keri install)
$VENV/bin/python -c "import boto3, keri; from keri.app import indirecting; print('ok')"
```
Expected: a version string + `ok`. If `kli` is missing, `$VENV/bin/pip install -e /Users/seriouscoderone/code/keripy -q` (the fork provides kli).

- [ ] **Step 2: Baseline the verifier tests** (they must already pass — we keep the verifier):
Run: `cd ~/code/locksmith/.worktrees/publisher-rebuild && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/unit/update -q --import-mode=importlib`
Expected: PASS. Note the count.

---

### Task 1: Release-seal builder (the contract)

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/seal.py`
- Test: `tools/publisher/tests/test_seal.py`

- [ ] **Step 1: Write the failing test**
```python
import hashlib
from pathlib import Path
from locksmith_publisher.seal import build_release_seal


def test_build_release_seal_shape(tmp_path):
    mac = tmp_path / "Locksmith-macos.dmg"; mac.write_bytes(b"mac-bytes")
    win = tmp_path / "Locksmith-win.msi"; win.write_bytes(b"win-bytes")
    seal = build_release_seal(version="0.2.0",
                              artifacts=[("macos", mac), ("windows", win)])
    assert seal == {"release": {"v": "0.2.0", "artifacts": [
        {"platform": "macos", "sha256": hashlib.sha256(b"mac-bytes").hexdigest()},
        {"platform": "windows", "sha256": hashlib.sha256(b"win-bytes").hexdigest()},
    ]}}
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`/`build_release_seal` undefined)
Run: `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tools/publisher/tests/test_seal.py -q --import-mode=importlib`

- [ ] **Step 3: Implement** `tools/publisher/src/locksmith_publisher/seal.py`:
```python
"""Release seal — the publisher↔verifier contract anchored in the ixn `a` field.

Verifier (locksmith/update/verify.py + kel_replay.extract_release_seal) expects:
    {"release": {"v": <version>, "artifacts": [{"platform": <p>, "sha256": <hex>}, ...]}}
"""
import hashlib
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_release_seal(*, version: str, artifacts: list[tuple[str, Path]]) -> dict:
    """artifacts = [(platform, path), ...] in publish order."""
    return {"release": {"v": version, "artifacts": [
        {"platform": plat, "sha256": _sha256(path)} for plat, path in artifacts
    ]}}
```

- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit**
```bash
git add tools/publisher/src/locksmith_publisher/seal.py tools/publisher/tests/test_seal.py
git commit -m "feat(publisher): release-seal builder (publisher↔verifier contract)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: kli subprocess wrappers (always --receipt-endpoint)

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/kli.py`
- Test: `tools/publisher/tests/test_kli_argv.py`

- [ ] **Step 1: Write the failing test** (assert argv composition — no real kli run here):
```python
from pathlib import Path
from locksmith_publisher import kli


def test_interact_argv_forces_receipt_endpoint(monkeypatch):
    captured = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **kw: captured.setdefault("argv", argv) or "")
    kli.kli_interact(name="publisher", alias="publisher", bran="x" * 21,
                     base="/tmp/pub", data='{"release":{}}')
    argv = captured["argv"]
    assert argv[:2] == ["kli", "interact"]
    assert "--receipt-endpoint" in argv
    assert "--data" in argv and '{"release":{}}' in argv
    assert "--alias" in argv and "publisher" in argv


def test_incept_argv_has_wits_toad_and_receipt_endpoint(monkeypatch):
    captured = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **kw: captured.setdefault("argv", argv) or "")
    kli.kli_incept(name="publisher", alias="publisher", bran="x" * 21, base="/tmp/pub",
                   wits=["BWit1", "BWit2", "BWit3"], toad=3)
    argv = captured["argv"]
    assert "--receipt-endpoint" in argv
    assert argv.count("--wits") == 3 and "BWit2" in argv
    assert "--toad" in argv and "3" in argv
```

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** `tools/publisher/src/locksmith_publisher/kli.py`:
```python
"""Thin subprocess wrappers over keripy `kli`. ALL receipt-collecting commands
force --receipt-endpoint (routes to Receiptor → /receipts; the default
WitnessReceiptor path hangs over HTTP)."""
import subprocess
from pathlib import Path

KLI = "kli"  # resolved on PATH; in tests/CI use the venv's bin/kli


def _run(argv: list[str], *, check: bool = True) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(argv)} failed ({proc.returncode}):\n{proc.stderr}")
    return proc.stdout


def kli_incept(*, name, alias, bran, base, wits: list[str], toad: int,
               transferable=True, icount=1, isith="1", ncount=1, nsith="1") -> str:
    argv = [KLI, "incept", "--name", name, "--alias", alias, "--base", base,
            "--passcode", bran, "--receipt-endpoint",
            "--transferable" if transferable else "--non-transferable",
            "--icount", str(icount), "--isith", str(isith),
            "--ncount", str(ncount), "--nsith", str(nsith), "--toad", str(toad)]
    for w in wits:
        argv += ["--wits", w]
    return _run(argv)


def kli_interact(*, name, alias, bran, base, data: str) -> str:
    argv = [KLI, "interact", "--name", name, "--alias", alias, "--base", base,
            "--passcode", bran, "--receipt-endpoint", "--data", data]
    return _run(argv)
```
(`KLI` defaults to the PATH `kli`; tests/CI set `kli.KLI = "<venv>/bin/kli"`. KEL export is done in `publish.py` via the keri library, not a kli wrapper — see Task 4.)

- [ ] **Step 4: Run — expect PASS.**
- [ ] **Step 5: Commit**
```bash
git add tools/publisher/src/locksmith_publisher/kli.py tools/publisher/tests/test_kli_argv.py
git commit -m "feat(publisher): kli subprocess wrappers (force --receipt-endpoint)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Publish glue — appcast + S3 (adapt existing modules)

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/appcast.py` (build/update), `s3_client.py` (upload)
- Test: `tools/publisher/tests/test_appcast_build.py`

- [ ] **Step 1: Read the existing interfaces first.** Open `appcast.py` (the `Appcast`/`Release` it parses on the verify side — fields used by `verify.py`: appcast `publisher_aid`, `publisher_kel_url`, `current_version`; release `version`, `anchor_said`, `anchor_url`, `artifact_sha256`) and `s3_client.py` (its upload signature). The build side must emit exactly those fields.

- [ ] **Step 2: Write the failing test** — `tools/publisher/tests/test_appcast_build.py`:
```python
from locksmith_publisher.appcast import build_appcast
from locksmith.update.appcast import parse_appcast, select_latest_for_platform


def test_build_appcast_roundtrips_through_verifier_parser():
    raw = build_appcast(
        publisher_aid="EPub",
        publisher_kel_url="https://releases.example.com/publisher/v1/kel.cesr",
        releases=[dict(version="0.2.0", anchor_said="EAnch", platform="macos",
                       anchor_url="https://releases.example.com/publisher/v1/anchors/EAnch.cesr",
                       artifact_sha256="ab" * 32,
                       artifact_url="https://releases.example.com/0.2.0/Locksmith-macos.dmg")],
    )
    ac = parse_appcast(raw)
    assert ac.publisher_aid == "EPub"
    assert ac.publisher_kel_url.endswith("/publisher/v1/kel.cesr")
    rel = select_latest_for_platform(ac, "macos")
    assert rel.version == "0.2.0" and rel.anchor_said == "EAnch"
    assert rel.artifact_sha256 == "ab" * 32
```

- [ ] **Step 3: Implement `build_appcast(...)`** in `appcast.py` to emit the structure `parse_appcast`/`select_latest_for_platform` consume (mirror the parsed schema exactly — read `parse_appcast` to match keys). Add an `upload_release(...)` helper in `s3_client.py` that puts `kel.cesr` at `<bucket>/publisher/v1/kel.cesr`, each anchor event at `<bucket>/publisher/v1/anchors/<said>.cesr`, and the appcast at its path (use the existing boto3 client/signature).

- [ ] **Step 4: Run — expect PASS.** Run: `… -m pytest tools/publisher/tests/test_appcast_build.py -q --import-mode=importlib`

- [ ] **Step 5: Commit**
```bash
git add tools/publisher/src/locksmith_publisher/appcast.py tools/publisher/src/locksmith_publisher/s3_client.py tools/publisher/tests/test_appcast_build.py
git commit -m "feat(publisher): appcast build + S3 upload glue for the kli pipeline

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Orchestration (`publish.py`)

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/publish.py`
- (Tested end-to-end by Task 5; Task 4 wires the pieces.)

- [ ] **Step 1: Implement** `publish.py` — `anchor_release(...)` composes the pieces. kli does the key ops (interact = sign + witness); the keri library reads the KEL back (no keys for reading) via `db.clonePreIter`, which yields **each event together with its attachments (wigs inline)** — giving both the full `kel.cesr` and the per-event bytes/SAID in one pass, no byte-walking:
```python
"""Greenfield publisher orchestration: build seal → kli interact (sign+witness) →
read the KEL back via clonePreIter (export + anchor lookup). No re-implemented
KERI logic — kli for keys, keri lib read-only for the KEL stream."""
import json
from pathlib import Path
from keri.app import habbing
from keri.core import serdering
from .seal import build_release_seal
from . import kli


def anchor_release(*, name, alias, bran, base, version,
                   artifacts: list[tuple[str, Path]], out_dir: str) -> dict:
    """Anchor one release. Returns {anchor_said, anchor_sn, kel_path, anchor_event_path}."""
    seal = build_release_seal(version=version, artifacts=artifacts)
    kli.kli_interact(name=name, alias=alias, bran=bran, base=base, data=json.dumps(seal))

    # Read the KEL back (no keys needed to read). clonePreIter yields one msg per
    # event = event bytes + its inline attachments (sigs/wigs); SerderKERI parses
    # the leading event. The anchor is the event whose `a` carries our release seal.
    hby = habbing.Habery(name=name, base=base, bran=bran)
    try:
        hab = hby.habByName(alias)
        kel = bytearray()
        anchor = None
        for msg in hby.db.clonePreIter(pre=hab.pre):
            kel.extend(msg)
            serder = serdering.SerderKERI(raw=bytes(msg))
            for s in serder.ked.get("a", []):
                if isinstance(s, dict) and s.get("release", {}).get("v") == version:
                    anchor = dict(said=serder.said, sn=serder.sn, bytes=bytes(msg))
        if anchor is None:
            raise RuntimeError(f"no anchor event for version {version} in publisher KEL")
        pre = hab.pre
    finally:
        hby.close()

    kel_path = Path(out_dir) / f"{pre}-kel.cesr"
    kel_path.write_bytes(bytes(kel))
    anchor_event_path = Path(out_dir) / f"{anchor['said']}.cesr"
    anchor_event_path.write_bytes(anchor["bytes"])
    return dict(anchor_said=anchor["said"], anchor_sn=anchor["sn"],
                kel_path=str(kel_path), anchor_event_path=str(anchor_event_path))
```
(`clonePreIter` is exactly what `kli export` uses internally — `export.py:88` — so the emitted `kel.cesr` is byte-identical to a `kli export`, and the per-event `msg` bytes are what the verifier fetches from `anchor_url`. One pass, no separate split helper.)

- [ ] **Step 2: Commit** (no standalone unit test — Task 5 is its test):
```bash
git add tools/publisher/src/locksmith_publisher/publish.py
git commit -m "feat(publisher): kli anchor→export orchestration

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Keystone round-trip test (in-process witness → verify_artifact)

**Files:**
- Create: `tests/integration/test_publisher_roundtrip.py`

- [ ] **Step 1: Write the test.** Stand up a real keripy witness (HTTP, in-process) like the ConfirmDoer integration test; point `kli.KLI` at `<venv>/bin/kli`; run incept(`--receipt-endpoint`, wits=[the in-process witness], toad=1) → `anchor_release(...)` for a fake artifact → assert `verify_artifact` validates the exported KEL.
```python
import pytest
from pathlib import Path
from locksmith_publisher import kli, publish
from locksmith.update.verify import verify_artifact
from locksmith.update.appcast import ... # build a minimal appcast in-test

VENV_KLI = "/Users/seriouscoderone/code/locksmith/.venv/bin/kli"


@pytest.mark.integration
def test_publisher_roundtrip_verifies(tmp_path, monkeypatch):
    monkeypatch.setattr(kli, "KLI", VENV_KLI)
    # 1. in-process witness over HTTP (mirror tests/integration/test_confirmdoer_receipts_over_http.py:
    #    indirecting.setupWitness(tcpPort=None, httpPort=<free>), run in a Doist; get witHab.pre).
    # 2. kli init/incept --receipt-endpoint --wits <witHab.pre> --toad 1 (base=tmp_path keystore).
    #    NOTE: kli must resolve the witness OOBI/loc — seed it the same way the ConfirmDoer test's
    #    _seed_wit_ends does, OR pass the witness OOBI to `kli oobi resolve` before incept.
    # 3. artifact = tmp_path/"app.bin"; artifact.write_bytes(b"...")
    #    info = publish.anchor_release(version="0.2.0", artifacts=[("macos", artifact)], out_dir=tmp_path, ...)
    # 4. assert verify_artifact(artifact_path=artifact, appcast_raw=<built appcast pointing kel_url at a
    #    file:// of info['kel_path'] via monkeypatched _fetch_url>, platform="macos",
    #    embedded_publisher_aid=<pub.pre>, embedded_kel_sn=info['anchor_sn'],
    #    embedded_kel_said=info['anchor_said'], toad=1).ok
```
Monkeypatch `locksmith.update.verify._fetch_url` to return the local `kel.cesr` / anchor-event bytes (no network). The test asserts the full chain: kli+Receiptor put wigs in the KEL, `clonePreIter` emits them, `replay_kel` meets toad, and the seal binds the artifact digest. This is the round trip the old `attach_wigs` tests faked.

- [ ] **Step 2: Run — iterate to GREEN** (this is integration; budget a debug pass on the witness OOBI seeding + the per-event split helper from Task 4 Step 1).
Run: `… -m pytest tests/integration/test_publisher_roundtrip.py -q --import-mode=importlib -m integration`
Expected: `1 passed`. If `verify_artifact` raises `WitnessThresholdError`, the wigs didn't land → confirm `--receipt-endpoint` is passed and the witness has the publisher's icp (OOBI/seed). If `SchemaError` on the seal → the per-event split in Task 4 picked the wrong event; fix the helper.

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_publisher_roundtrip.py tools/publisher/src/locksmith_publisher/publish.py
git commit -m "test(publisher): in-process-witness incept→interact→export→verify round trip

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Trust-anchor template + build-injection; de-commit the real one

**Files:**
- Delete (from git): `src/locksmith/release/publisher_anchor.json`
- Create: `src/locksmith/release/publisher_anchor.example.json`
- Modify: the loader that reads the anchor (find it: `grep -rn publisher_anchor src/locksmith`) + `.gitignore`
- Test: `tests/unit/release/test_publisher_anchor_loader.py`

- [ ] **Step 1: Find the loader + write the failing test.** `grep -rn "publisher_anchor" src/locksmith` to find how the anchor is loaded. Write a test asserting: (a) the loader reads from a build-injected path/env (`LOCKSMITH_PUBLISHER_ANCHOR` or `src/locksmith/release/publisher_anchor.json` when present), (b) the committed `publisher_anchor.example.json` parses and has `example.com` placeholders + the required keys (`publisher_aid`, `witness_oobis`, `embedded_kel_sn`, `embedded_kel_said`, `toad`).
- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** — add `publisher_anchor.example.json` (placeholders), make the loader prefer `$LOCKSMITH_PUBLISHER_ANCHOR` then a gitignored `publisher_anchor.json`, add `src/locksmith/release/publisher_anchor.json` to `.gitignore`, and `git rm --cached src/locksmith/release/publisher_anchor.json` (de-commit the stale old AID; the file stays locally/ignored).
- [ ] **Step 4: Run — expect PASS.** Confirm `git status` shows the real anchor now ignored.
- [ ] **Step 5: Commit**
```bash
git add src/locksmith/release/publisher_anchor.example.json .gitignore <loader-file> tests/unit/release/test_publisher_anchor_loader.py
git rm --cached src/locksmith/release/publisher_anchor.json
git commit -m "refactor(release): build-inject publisher trust anchor; de-commit real one (privacy)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Retire the old publisher KERI code + the masking tests

**Files:**
- Modify/Delete: `tools/publisher/src/locksmith_publisher/{release_anchor,witness_client,signing_context}.py` (remove KERI-event/receipt parts; keep nothing that builds/collects KEL events outside `kli`)
- Delete: `tests/unit/publisher/test_round_trip_verify.py` (its `_attach_wigs` fakes the bug), `attach_wigs` in `tests/fixtures/update/generate.py`

- [ ] **Step 1:** `grep -rn "witness_client\|release_anchor\|signing_context\|attach_wigs\|WitnessReceiptor" tools/publisher tests` to enumerate references. Remove the now-dead modules/functions and any imports of them. The kli pipeline (Tasks 1-5) replaces them; the Apple/Azure code-signing path (if in `signing_context.py`) stays — only the KERI-event building goes.
- [ ] **Step 2: Run the full publisher + update suites — expect green** (the round-trip from Task 5 is now the real coverage):
Run: `… -m pytest tools/publisher/tests tests/unit/update tests/integration/test_publisher_roundtrip.py -q --import-mode=importlib -m "integration or not integration"`
- [ ] **Step 3: Commit**
```bash
git add -A tools/publisher tests
git commit -m "chore(publisher): retire bespoke KERI-event/receipt code + wig-masking tests

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Wire the updater verify gate (kept dark)

**Files:**
- Modify: `src/locksmith/core/apping.py` (`_init_native_updater`, the `verifier=lambda staged, info: True` stub ~`:126-135`)
- Test: `tests/unit/update/test_updater_gate.py`

- [ ] **Step 1: Write the failing test** — the gate calls `verify_artifact` when a publisher anchor is configured, and is inert (returns True / updater disabled) when no real anchor/kel is present (so it stays dark until the cutover + first real publish):
```python
def test_gate_calls_verify_when_anchor_present(monkeypatch):
    # configure a present anchor; assert the verifier closure invokes verify_artifact
    ...
def test_gate_dark_without_anchor(monkeypatch):
    # no injected anchor → closure does not hard-fail updates (dark)
    ...
```
- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** — replace the `lambda: True` with a closure that, when the trust anchor (Task 6 loader) resolves a real publisher AID, calls `verify_artifact(artifact_path=staged, appcast_raw=info.appcast, platform=<current>, embedded_*=<from anchor>, toad=<anchor.toad>)` and returns its `.ok`; when the anchor is the example/placeholder (or absent), it stays dark (no enforcement) so nothing breaks pre-cutover.
- [ ] **Step 4: Run — expect PASS.** Full suite: `… -m pytest tests/unit -q --import-mode=importlib`
- [ ] **Step 5: Commit**
```bash
git add src/locksmith/core/apping.py tests/unit/update/test_updater_gate.py
git commit -m "feat(update): wire verify_artifact gate (dark until a real publisher anchor exists)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Real publisher inception + e2e + activation — DEFERRED (gated on the SAM→CDK cutover)

**Do not start until the fresh 5-witness CDK federation is live.** No code changes — operational.

- [ ] Incept the real publisher once on a controlled machine: `kli init` + `kli incept --receipt-endpoint --wits <5 fresh witness AIDs> --toad 3` (pre-rotation). Store keystore+bran as CI secrets.
- [ ] Anchor the first real release (`publish.anchor_release`), upload `kel.cesr` + anchor event + appcast to `releases.keri.host` (S3).
- [ ] Generate the real `publisher_anchor.json` (publisher AID + the 5 witness OOBIs + embedded sn/said + toad=3); inject at the next release build.
- [ ] Download a built artifact and confirm `locksmith --verify-update` / the in-app gate validates it end-to-end; then the gate (Task 8) activates automatically (real anchor present).
- [ ] Confirm the live SAM federation is gone and only the CDK federation serves.

---

## Completion

Full local suite green (incl. the round-trip + verifier tests), then **superpowers:finishing-a-development-branch** to merge `feat/publisher-rebuild` → `development` (Tasks 0-8; Task 9 stays open behind the cutover). Update memory `project_publisher_wig_attachment_bug` → resolved-by-rebuild once Task 9 lands.
