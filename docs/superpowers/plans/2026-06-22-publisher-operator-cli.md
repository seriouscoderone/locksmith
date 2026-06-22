# Publisher Operator CLI + Trust-Root Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deferred publisher operator CLI (thin glue over the already-tested kli pipeline) + generate the `publisher_anchor.json` trust root, then execute the two-phase rollout: mint the production publisher AID, and ship Locksmith 0.1.7 built with the new anchor so the in-app KERI update gate goes live.

**Architecture:** A `locksmith-publisher` Click group (`tools/publisher/src/locksmith_publisher/cli.py`) gains four working commands — `incept`, `gen-anchor`, `anchor`, `publish` — each sequencing existing, tested library functions (`seal`/`kli`/`publish.anchor_release`/`appcast`/`s3_client`/`witnesses`). Two new thin `kli` subprocess wrappers (`kli_init`, `kli_resolve_oobi`) and one pure builder (`build_publisher_anchor`) are the only new logic. The orphaned `yubikey.py`/`software_key.py` custody modules are retired. Then the operator runs the commands to mint the trust root and bootstrap-release 0.1.7.

**Tech Stack:** Python 3.14, Click, keripy `kli` (subprocess), boto3, pytest. Spec: `docs/superpowers/specs/2026-06-22-publisher-operator-cli-design.md`.

## Global Constraints

- **Repo:** locksmith (`~/code/locksmith`); publisher at `tools/publisher/`. Venv: `/Users/seriouscoderone/code/locksmith/.venv`.
- **Two test locations / commands (do not mix):**
  - Publisher unit tests live in `tools/publisher/tests/` (pyproject `pythonpath=["src","."]`). Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/ -q` (NO `--import-mode`).
  - The integration keystone lives in locksmith's main tree `tests/integration/test_publisher_roundtrip.py`. Run: `cd /Users/seriouscoderone/code/locksmith && .venv/bin/python -m pytest tests/integration/test_publisher_roundtrip.py -q --import-mode=importlib` (the top-level `packaging/` dir shadows the real `packaging` without it).
- **Custody:** `kli` keystore + bran. The bran is read from an **env var** (default `LOCKSMITH_PUBLISHER_BRAN`), never a literal CLI arg, never echoed. Single Ed25519 key (`icount=1`/`ncount=1`), pre-rotation by construction, `toad=3`.
- **Trust model (do not break):** KERI is the sole update trust; installed apps verify only against their build-injected `publisher_anchor.json`; the verifier (`src/locksmith/update/`) and the tested pipeline library functions are correct and MUST NOT change.
- **`publisher_anchor.json` schema (exact):** `{"publisher_aid": str, "embedded_kel_sn": 0, "embedded_kel_hash": str, "toad": 3, "witness_oobis": [str×5]}`. For sn=0, `embedded_kel_hash == publisher_aid` (an inception event's SAID is its prefix). Loader: `$LOCKSMITH_PUBLISHER_ANCHOR` → gitignored `src/locksmith/release/publisher_anchor.json` → raise (no example fallback). It is gitignored; the committed `publisher_anchor.example.json` keeps `example.com`/placeholders.
- **S3 layout (from `s3_client.upload_release`):** `<bucket>/publisher/v1/kel.cesr`, `<bucket>/publisher/v1/anchors/<said>.cesr`, appcasts at `<bucket>/appcast/v1/{macos,windows}.json`.
- **First anchored release = 0.1.7** (new build with the anchor injected), NOT a re-anchor of 0.1.6. Artifacts hashed are the **served** `releases/0.1.7/` dmg+msi.
- **Commit footer:** end each commit message with
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **AWS:** `AWS_PROFILE=personal`, region `us-east-1`, account `117870855864`.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `tools/publisher/src/locksmith_publisher/kli.py` | thin kli subprocess wrappers | **Add** `kli_init`, `kli_resolve_oobi` |
| `tools/publisher/src/locksmith_publisher/anchor_doc.py` (new) | pure `publisher_anchor.json` builder | **Create** `build_publisher_anchor(...)` |
| `tools/publisher/src/locksmith_publisher/cli.py` | operator CLI | **Replace** the `incept`/`anchor`/`sign`/`submit`/`verify-ceremony` retired stubs with working `incept`/`gen-anchor`/`anchor`/`publish` (drop `sign`/`submit`/`verify-ceremony`); keep `appcast` |
| `tools/publisher/src/locksmith_publisher/yubikey.py`, `software_key.py` | orphaned custody (unused) | **Delete** |
| `tools/publisher/tests/test_kli.py` | kli wrapper unit tests | **Add/extend** |
| `tools/publisher/tests/test_anchor_doc.py` (new) | builder unit test | **Create** |
| `tools/publisher/tests/test_cli.py` (new) | CLI command unit tests (Click `CliRunner`) | **Create** |
| `tools/publisher/tests/{test_yubikey.py,test_software_key.py}`, `tools/publisher/tests/conftest.py` | orphaned tests/fixtures | **Delete** test files; **clean** conftest |
| `tests/integration/test_publisher_roundtrip.py` | keystone — extend to drive the CLI | **Modify** |
| `pyproject.toml` (root) version + `.github/workflows/release.ci.yml` | 0.1.7 bump + anchor injection | **Modify** (Task 7) |

---

## Task 1: kli ceremony wrappers (`kli_init`, `kli_resolve_oobi`)

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/kli.py`
- Test: `tools/publisher/tests/test_kli.py`

**Interfaces:**
- Produces: `kli_init(*, name: str, base: str, bran: str) -> str`; `kli_resolve_oobi(*, name: str, base: str, bran: str, oobi: str) -> str`.
- Consumes: existing module-level `KLI` and `_run(argv, *, check=True) -> str` (raises `RuntimeError` on non-zero).

- [ ] **Step 1: Write the failing tests**

Create/extend `tools/publisher/tests/test_kli.py`:
```python
from locksmith_publisher import kli


def test_kli_init_argv(monkeypatch):
    seen = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **k: seen.setdefault("argv", argv) or "")
    kli.kli_init(name="pub", base="/ks", bran="BRANBRANBRANBRANBRAN0")
    assert seen["argv"] == [
        kli.KLI, "init", "--name", "pub", "--base", "/ks",
        "--passcode", "BRANBRANBRANBRANBRAN0",
    ]


def test_kli_resolve_oobi_argv(monkeypatch):
    seen = {}
    monkeypatch.setattr(kli, "_run", lambda argv, **k: seen.setdefault("argv", argv) or "")
    kli.kli_resolve_oobi(name="pub", base="/ks", bran="BRAN",
                         oobi="https://witness.example.com/oobi/BAID/witness")
    assert seen["argv"] == [
        kli.KLI, "oobi", "resolve", "--name", "pub", "--base", "/ks",
        "--passcode", "BRAN",
        "--oobi", "https://witness.example.com/oobi/BAID/witness",
    ]
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: module ... has no attribute 'kli_init'`)

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_kli.py -q`

- [ ] **Step 3: Implement** — append to `tools/publisher/src/locksmith_publisher/kli.py`:
```python
def kli_init(*, name, base, bran) -> str:
    """Create the keystore. `bran` is the passcode/seed; never logged."""
    return _run([KLI, "init", "--name", name, "--base", base, "--passcode", bran])


def kli_resolve_oobi(*, name, base, bran, oobi: str) -> str:
    """Resolve a witness OOBI into the keystore so incept can reach it."""
    return _run([KLI, "oobi", "resolve", "--name", name, "--base", base,
                 "--passcode", bran, "--oobi", oobi])
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_kli.py -q`

- [ ] **Step 5: Commit**
```bash
git add tools/publisher/src/locksmith_publisher/kli.py tools/publisher/tests/test_kli.py
git commit -m "feat(publisher): kli_init + kli_resolve_oobi ceremony wrappers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `publisher_anchor.json` builder (`build_publisher_anchor`)

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/anchor_doc.py`
- Test: `tools/publisher/tests/test_anchor_doc.py`

**Interfaces:**
- Produces: `build_publisher_anchor(*, publisher_aid: str, witness_oobis: list[str], toad: int = 3) -> dict`. `embedded_kel_sn` is always `0`; `embedded_kel_hash` equals `publisher_aid` (inception SAID == prefix).

- [ ] **Step 1: Write the failing test**

Create `tools/publisher/tests/test_anchor_doc.py`:
```python
from locksmith_publisher.anchor_doc import build_publisher_anchor


def test_build_publisher_anchor_shape():
    doc = build_publisher_anchor(
        publisher_aid="EpubAID000000000000000000000000000000000000",
        witness_oobis=[f"https://w{i}.example.com/oobi/Bw{i}/witness" for i in range(5)],
        toad=3,
    )
    assert doc == {
        "publisher_aid": "EpubAID000000000000000000000000000000000000",
        "embedded_kel_sn": 0,
        "embedded_kel_hash": "EpubAID000000000000000000000000000000000000",
        "toad": 3,
        "witness_oobis": [f"https://w{i}.example.com/oobi/Bw{i}/witness" for i in range(5)],
    }
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`)

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_anchor_doc.py -q`

- [ ] **Step 3: Implement** `tools/publisher/src/locksmith_publisher/anchor_doc.py`:
```python
"""Pure builder for the publisher trust anchor (publisher_anchor.json).

Schema consumed by locksmith/update/cli.py:_load_publisher_anchor + verify.
For sn=0 the inception event's SAID is the AID prefix, so embedded_kel_hash
equals publisher_aid.
"""
from __future__ import annotations


def build_publisher_anchor(*, publisher_aid: str, witness_oobis: list[str],
                           toad: int = 3) -> dict:
    return {
        "publisher_aid": publisher_aid,
        "embedded_kel_sn": 0,
        "embedded_kel_hash": publisher_aid,
        "toad": toad,
        "witness_oobis": list(witness_oobis),
    }
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_anchor_doc.py -q`

- [ ] **Step 5: Commit**
```bash
git add tools/publisher/src/locksmith_publisher/anchor_doc.py tools/publisher/tests/test_anchor_doc.py
git commit -m "feat(publisher): pure publisher_anchor.json builder

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `incept` + `gen-anchor` CLI commands (one-time ceremony)

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/cli.py` (replace the `incept` stub; add `gen-anchor`; delete `sign`/`submit`/`verify-ceremony` stubs and the `anchor` stub — `anchor` is re-added live in Task 4)
- Test: `tools/publisher/tests/test_cli.py`

**Interfaces:**
- Consumes: `kli.kli_init`/`kli_resolve_oobi`/`kli_incept`/`KLI` (Task 1), `anchor_doc.build_publisher_anchor` (Task 2), `witnesses.default_witness_pool()` → `[WitnessInfo(aid, oobi)]`, `keri.app.habbing.Habery`.
- Produces (behavior): `incept` mints the AID (init → resolve N OOBIs → `kli_incept(wits, toad)`), prints the AID. `gen-anchor` writes `src/locksmith/release/publisher_anchor.json` from the keystore's `hab.pre` + the witness OOBIs + toad; refuses to overwrite without `--force`.

- [ ] **Step 1: Write the failing tests**

Create `tools/publisher/tests/test_cli.py`:
```python
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from locksmith_publisher import cli as cli_mod
from locksmith_publisher.witnesses import WitnessInfo


@pytest.fixture
def fake_pool(monkeypatch):
    pool = [WitnessInfo(aid=f"Bwit{i}", oobi=f"https://w{i}.example.com/oobi/Bwit{i}/witness")
            for i in range(5)]
    monkeypatch.setattr(cli_mod, "default_witness_pool", lambda: pool)
    return pool


def test_incept_sequences_kli(monkeypatch, fake_pool):
    calls = []
    monkeypatch.setattr(cli_mod.kli, "kli_init", lambda **k: calls.append(("init", k)) or "")
    monkeypatch.setattr(cli_mod.kli, "kli_resolve_oobi", lambda **k: calls.append(("oobi", k["oobi"])) or "")
    monkeypatch.setattr(cli_mod.kli, "kli_incept",
                        lambda **k: calls.append(("incept", k)) or "Prefix  EpubAID\n")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    r = CliRunner().invoke(cli_mod.cli, ["incept", "--name", "pub", "--base", "/ks"])
    assert r.exit_code == 0, r.output
    assert calls[0][0] == "init"
    assert [c[1] for c in calls if c[0] == "oobi"] == [w.oobi for w in fake_pool]
    incept_call = next(c for c in calls if c[0] == "incept")
    assert incept_call[1]["wits"] == [w.aid for w in fake_pool]
    assert incept_call[1]["toad"] == 3


def test_incept_requires_bran_env(monkeypatch, fake_pool):
    monkeypatch.delenv("LOCKSMITH_PUBLISHER_BRAN", raising=False)
    r = CliRunner().invoke(cli_mod.cli, ["incept", "--name", "pub", "--base", "/ks"])
    assert r.exit_code != 0
    assert "LOCKSMITH_PUBLISHER_BRAN" in r.output


def test_gen_anchor_writes_doc(monkeypatch, tmp_path, fake_pool):
    out = tmp_path / "publisher_anchor.json"
    monkeypatch.setattr(cli_mod, "_publisher_anchor_path", lambda: out)
    monkeypatch.setattr(cli_mod, "_read_publisher_aid",
                        lambda **k: "EpubAID000000000000000000000000000000000000")
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    r = CliRunner().invoke(cli_mod.cli, ["gen-anchor", "--name", "pub", "--base", "/ks"])
    assert r.exit_code == 0, r.output
    doc = json.loads(out.read_text())
    assert doc["publisher_aid"] == "EpubAID000000000000000000000000000000000000"
    assert doc["embedded_kel_hash"] == doc["publisher_aid"]
    assert doc["embedded_kel_sn"] == 0 and doc["toad"] == 3
    assert doc["witness_oobis"] == [w.oobi for w in fake_pool]
    # refuses overwrite without --force
    r2 = CliRunner().invoke(cli_mod.cli, ["gen-anchor", "--name", "pub", "--base", "/ks"])
    assert r2.exit_code != 0 and "exists" in r2.output.lower()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_cli.py -q`
Expected: FAIL (commands not implemented / `incept` still the retired stub).

- [ ] **Step 3: Implement** — in `cli.py`, add imports at top and replace the stubs. Add near the existing imports:
```python
import json
import os
from pathlib import Path

from . import kli
from .anchor_doc import build_publisher_anchor
from .witnesses import default_witness_pool
from keri.app import habbing
```
Add helpers (module level):
```python
def _publisher_anchor_path() -> Path:
    bundled = _bundled_publisher_anchor_path()
    if bundled is not None:
        return bundled
    # Not yet present — resolve the canonical gitignored location from this file.
    for parent in Path(__file__).resolve().parents:
        cand = parent / "src" / "locksmith" / "release"
        if cand.is_dir():
            return cand / "publisher_anchor.json"
    raise click.UsageError("could not locate src/locksmith/release/ — run from the repo")


def _read_publisher_aid(*, name: str, base: str, bran: str) -> str:
    """Open the keystore read-only and return the publisher hab prefix (the AID)."""
    hby = habbing.Habery(name=name, base=base, bran=bran)
    try:
        hab = hby.habByName("publisher")
        if hab is None:
            raise click.ClickException(f"no 'publisher' alias in keystore {name}")
        return hab.pre
    finally:
        hby.close()


def _bran(bran_env: str) -> str:
    try:
        return os.environ[bran_env]
    except KeyError:
        raise click.UsageError(f"bran env var {bran_env} is not set")
```
Replace the `@cli.command("incept")` stub with:
```python
@cli.command("incept")
@click.option("--name", required=True, help="keystore name")
@click.option("--base", required=True, help="keystore base dir")
@click.option("--alias", default="publisher", show_default=True)
@click.option("--bran-env", default="LOCKSMITH_PUBLISHER_BRAN", show_default=True,
              help="env var holding the keystore bran (never pass the bran as an arg)")
@click.option("--toad", default=3, show_default=True, type=int)
def incept_cmd(name, base, alias, bran_env, toad):
    """Mint the publisher AID: init keystore, resolve witness OOBIs, incept (pre-rotation)."""
    bran = _bran(bran_env)
    pool = default_witness_pool()
    kli.kli_init(name=name, base=base, bran=bran)
    for w in pool:
        kli.kli_resolve_oobi(name=name, base=base, bran=bran, oobi=w.oobi)
    out = kli.kli_incept(name=name, alias=alias, bran=bran, base=base,
                         wits=[w.aid for w in pool], toad=toad)
    click.echo(out)
```
Add the `gen-anchor` command (and delete the `sign`/`submit`/`verify-ceremony`/`anchor` stub defs):
```python
@cli.command("gen-anchor")
@click.option("--name", required=True)
@click.option("--base", required=True)
@click.option("--bran-env", default="LOCKSMITH_PUBLISHER_BRAN", show_default=True)
@click.option("--toad", default=3, show_default=True, type=int)
@click.option("--force", is_flag=True, help="overwrite an existing publisher_anchor.json")
def gen_anchor_cmd(name, base, bran_env, toad, force):
    """Write src/locksmith/release/publisher_anchor.json from the minted keystore."""
    path = _publisher_anchor_path()
    if path.exists() and not force:
        raise click.ClickException(f"{path} already exists; pass --force to overwrite")
    aid = _read_publisher_aid(name=name, base=base, bran=_bran(bran_env))
    doc = build_publisher_anchor(
        publisher_aid=aid,
        witness_oobis=[w.oobi for w in default_witness_pool()],
        toad=toad,
    )
    path.write_text(json.dumps(doc, indent=2) + "\n")
    click.echo(f"wrote {path} (publisher_aid={aid})")
```
Delete the now-unneeded `_retired`/`_RETIRED_MSG` helpers and the `sign`/`submit`/`verify-ceremony`/`anchor` stub functions.

- [ ] **Step 4: Run — expect PASS**

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_cli.py -q`

- [ ] **Step 5: Commit**
```bash
git add tools/publisher/src/locksmith_publisher/cli.py tools/publisher/tests/test_cli.py
git commit -m "feat(publisher): incept + gen-anchor operator commands

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `anchor` + `publish` CLI commands (per-release)

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/cli.py`
- Test: `tools/publisher/tests/test_cli.py`

**Interfaces:**
- Consumes: `publish.anchor_release(...) -> {anchor_said, anchor_sn, kel_path, anchor_event_path}`, `appcast.build_appcast(*, publisher_aid, publisher_kel_url, releases, channel, schema_version, current_version) -> str`, `s3_client.S3.default()` + `upload_release(*, bucket, kel, anchors, appcast, appcast_key)` + `put_object(*, bucket, key, data, content_type)`, `locksmith.release.deploy.load_deploy_config()`, `seal.build_release_seal` (for sha256s). The appcast `releases` dict keys: `version, platform, anchor_said, anchor_url, artifact_sha256, artifact_url`.
- Produces (behavior): `anchor` signs+witnesses the release seal and writes `kel.cesr` + anchor event to `--out-dir`. `publish` uploads the KEL + anchor + a per-platform appcast (macos + windows) to S3 from `deploy_config`-derived bucket/URLs.

> **Why `build_appcast` not `generate_and_upload_appcasts`:** the S3-re-reading generator expects a richer seal (`released_at`, `minimum_system_versions`, artifact `filename`/`size`) than `build_release_seal` produces. `publish` builds appcasts directly from known release data via the forgiving `build_appcast`. The existing `appcast` regeneration command is left as-is (out of scope; its richer-seal expectation is a separate follow-up).

- [ ] **Step 1: Write the failing tests** (append to `tools/publisher/tests/test_cli.py`)
```python
def test_anchor_invokes_anchor_release(monkeypatch, tmp_path):
    mac = tmp_path / "Locksmith-0.1.7.dmg"; mac.write_bytes(b"dmg")
    win = tmp_path / "Locksmith-0.1.7.msi"; win.write_bytes(b"msi")
    seen = {}
    monkeypatch.setattr(cli_mod.publish, "anchor_release",
                        lambda **k: seen.update(k) or {
                            "anchor_said": "Eanchor", "anchor_sn": 1,
                            "kel_path": str(tmp_path / "kel.cesr"),
                            "anchor_event_path": str(tmp_path / "Eanchor.cesr")})
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    r = CliRunner().invoke(cli_mod.cli, [
        "anchor", "--name", "pub", "--base", "/ks", "--version", "0.1.7",
        "--macos", str(mac), "--windows", str(win), "--out-dir", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert seen["version"] == "0.1.7"
    assert [p for p, _ in seen["artifacts"]] == ["macos", "windows"]


def test_publish_uploads_kel_anchor_and_two_appcasts(monkeypatch, tmp_path):
    (tmp_path / "kel.cesr").write_bytes(b"KEL")
    (tmp_path / "Eanchor.cesr").write_bytes(b"ANCHOR")
    monkeypatch.setattr(cli_mod, "load_deploy_config", lambda: {
        "s3_bucket": "releases.example.com",
        "releases_cdn_base": "https://releases.example.com",
        "publisher_kel_url": "https://releases.example.com/publisher/v1/kel.cesr",
    })
    monkeypatch.setattr(cli_mod, "_read_publisher_aid", lambda **k: "EpubAID")
    uploads = {"release": None, "puts": []}
    class FakeS3:
        def upload_release(self, **k): uploads["release"] = k
        def put_object(self, **k): uploads["puts"].append(k)
    monkeypatch.setattr(cli_mod.S3, "default", classmethod(lambda cls: FakeS3()))
    monkeypatch.setenv("LOCKSMITH_PUBLISHER_BRAN", "BRAN0000000000000000")
    r = CliRunner().invoke(cli_mod.cli, [
        "publish", "--name", "pub", "--base", "/ks", "--version", "0.1.7",
        "--anchor-said", "Eanchor",
        "--macos-sha256", "a"*64, "--windows-sha256", "b"*64,
        "--out-dir", str(tmp_path)])
    assert r.exit_code == 0, r.output
    rel = uploads["release"]
    assert rel["bucket"] == "releases.example.com"
    assert rel["kel"] == b"KEL"
    assert rel["anchors"] == {"Eanchor": b"ANCHOR"}
    assert rel["appcast_key"] == "appcast/v1/macos.json"
    # windows appcast uploaded separately
    assert any(p["key"] == "appcast/v1/windows.json" for p in uploads["puts"])
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_cli.py -q`

- [ ] **Step 3: Implement** — add to `cli.py` imports:
```python
from . import publish
from .appcast import build_appcast
from .s3_client import S3
from locksmith.release.deploy import load_deploy_config
```
(`from .s3_client import S3` may already exist — keep one.) Add the commands:
```python
@cli.command("anchor")
@click.option("--name", required=True)
@click.option("--base", required=True)
@click.option("--alias", default="publisher", show_default=True)
@click.option("--bran-env", default="LOCKSMITH_PUBLISHER_BRAN", show_default=True)
@click.option("--version", required=True)
@click.option("--macos", "macos_path", required=True,
              type=click.Path(exists=True, path_type=Path))
@click.option("--windows", "windows_path", required=True,
              type=click.Path(exists=True, path_type=Path))
@click.option("--out-dir", default="out", show_default=True)
def anchor_cmd(name, base, alias, bran_env, version, macos_path, windows_path, out_dir):
    """Sign + witness the release seal over the (served) artifacts; export the KEL."""
    info = publish.anchor_release(
        name=name, alias=alias, bran=_bran(bran_env), base=base, version=version,
        artifacts=[("macos", macos_path), ("windows", windows_path)], out_dir=out_dir)
    click.echo(json.dumps(info, indent=2))


@cli.command("publish")
@click.option("--name", required=True)
@click.option("--base", required=True)
@click.option("--bran-env", default="LOCKSMITH_PUBLISHER_BRAN", show_default=True)
@click.option("--version", required=True)
@click.option("--anchor-said", required=True)
@click.option("--macos-sha256", required=True)
@click.option("--windows-sha256", required=True)
@click.option("--out-dir", default="out", show_default=True)
def publish_cmd(name, base, bran_env, version, anchor_said,
                macos_sha256, windows_sha256, out_dir):
    """Upload KEL + anchor + per-platform appcasts to S3 from deploy_config."""
    cfg = load_deploy_config()
    bucket = cfg["s3_bucket"]
    cdn = cfg["releases_cdn_base"].rstrip("/")
    kel_url = cfg["publisher_kel_url"]
    aid = _read_publisher_aid(name=name, base=base, bran=_bran(bran_env))

    out = Path(out_dir)
    kel = (out / f"{aid}-kel.cesr").read_bytes()
    anchor_bytes = (out / f"{anchor_said}.cesr").read_bytes()
    anchor_url = f"{cdn}/publisher/v1/anchors/{anchor_said}.cesr"

    def _appcast(platform, sha, ext):
        rel = {"version": version, "platform": platform, "anchor_said": anchor_said,
               "anchor_url": anchor_url, "artifact_sha256": sha,
               "artifact_url": f"{cdn}/releases/{version}/Locksmith-{version}.{ext}"}
        return build_appcast(publisher_aid=aid, publisher_kel_url=kel_url,
                             releases=[rel], current_version=version).encode()

    s3 = S3.default()
    s3.upload_release(bucket=bucket, kel=kel, anchors={anchor_said: anchor_bytes},
                      appcast=_appcast("macos", macos_sha256, "dmg"),
                      appcast_key="appcast/v1/macos.json")
    s3.put_object(bucket=bucket, key="appcast/v1/windows.json",
                  data=_appcast("windows", windows_sha256, "msi"),
                  content_type="application/json")
    click.echo(f"published v{version}: publisher/v1/kel.cesr + anchors/{anchor_said}.cesr "
               f"+ appcast/v1/{{macos,windows}}.json")
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_cli.py -q`

- [ ] **Step 5: Commit**
```bash
git add tools/publisher/src/locksmith_publisher/cli.py tools/publisher/tests/test_cli.py
git commit -m "feat(publisher): anchor + publish per-release commands

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Retire the orphaned custody modules

**Files:**
- Delete: `tools/publisher/src/locksmith_publisher/yubikey.py`, `tools/publisher/src/locksmith_publisher/software_key.py`, `tools/publisher/tests/test_yubikey.py`, `tools/publisher/tests/test_software_key.py`
- Modify: `tools/publisher/tests/conftest.py` (remove the `FakeYubiKeyDevice` import + its fixtures)

- [ ] **Step 1: Confirm no live (non-test) importers remain**

Run: `cd /Users/seriouscoderone/code/locksmith && grep -rn "yubikey\|software_key\|YubiKeyDevice\|SoftwareKeyDevice\|open_software_devices\|open_real_device" tools/publisher/src/ src/`
Expected: hits ONLY inside `yubikey.py`/`software_key.py` themselves (no pipeline module imports them). If any pipeline module (`cli.py`/`publish.py`/etc.) imports them, STOP and report.

- [ ] **Step 2: Check which conftest fixtures are used elsewhere**

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && grep -rn "yubikey\|software_key\|FakeYubiKeyDevice\|<fixture-names-from-conftest>" tests/`
Identify whether any *surviving* test uses the conftest YubiKey fixtures. (Expected: only `test_yubikey.py`/`test_software_key.py`, which are being deleted.)

- [ ] **Step 3: Delete + clean**
```bash
cd /Users/seriouscoderone/code/locksmith
git rm tools/publisher/src/locksmith_publisher/yubikey.py \
       tools/publisher/src/locksmith_publisher/software_key.py \
       tools/publisher/tests/test_yubikey.py \
       tools/publisher/tests/test_software_key.py
```
Edit `tools/publisher/tests/conftest.py`: remove the `from locksmith_publisher.yubikey import FakeYubiKeyDevice` line and any fixtures that construct `FakeYubiKeyDevice` (per Step 2, confirmed unused by surviving tests). If that empties `conftest.py`, `git rm` it too.

- [ ] **Step 4: Run the full publisher unit suite — expect PASS (no import errors)**

Run: `cd /Users/seriouscoderone/code/locksmith/tools/publisher && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/ -q`
Expected: PASS; the yubikey/software_key tests are gone; nothing references the deleted modules.

- [ ] **Step 5: Commit**
```bash
git add -A tools/publisher/
git commit -m "chore(publisher): retire unused yubikey/software_key custody modules

Orphaned from the old bespoke design; the kli pipeline owns custody via the
kli keystore + bran. No pipeline module imported them.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Extend the keystone integration test to drive the CLI

**Files:**
- Modify: `tests/integration/test_publisher_roundtrip.py`

**Interfaces:**
- Consumes: the existing in-process witness harness (`indirecting.setupWitness`, the background doist thread, `kli.KLI` override, the `verify._fetch_url` monkeypatch) + the new CLI commands via Click `CliRunner`.
- Produces (behavior): an end-to-end test that runs `incept` → `anchor` → `publish` (S3 calls faked) → `verify_artifact`, asserting `result.ok` and `result.witness_receipts >= 1`.

- [ ] **Step 1: Add the CLI-driven test** alongside the existing round-trip test, reusing its witness fixture/harness. Add a test that:
  1. Stands up the in-process witness (reuse the existing setup; refactor the witness bring-up into a fixture if not already), with the witness AID wired into a fake `default_witness_pool()` (monkeypatch `cli.default_witness_pool` to return one `WitnessInfo(aid=witHab.pre, oobi=<wit_url>/oobi/<aid>/witness)`, `toad=1`).
  2. Sets `LOCKSMITH_PUBLISHER_BRAN`, runs `CliRunner().invoke(cli, ["incept", "--name", ..., "--base", ..., "--toad", "1"])`; asserts exit 0.
  3. Builds a fake artifact, runs `anchor --version 0.2.0 --macos <f> --windows <f> --out-dir <tmp>`; captures `anchor_said` from output JSON.
  4. Runs `publish` with `S3.default` monkeypatched to a fake capturing uploads; captures the uploaded `kel` + appcast bytes.
  5. Monkeypatches `verify._fetch_url` to serve the captured KEL + anchor bytes (as the existing test does) and calls `verify.verify_artifact(...)` with the `publisher_anchor.json` fields produced by `gen-anchor`.
  6. Asserts `result.ok` and `result.witness_receipts >= 1`.

> Reuse the exact witness setup, `kli.KLI` override (`/Users/seriouscoderone/code/locksmith/.venv/bin/kli`), and `_fetch_url` monkeypatch already in the file. Keep the assertions verbatim: `assert result.ok` and `assert result.witness_receipts >= 1`. The S3 layer is faked (no real AWS in CI); the KERI/witness/kli path is real.

- [ ] **Step 2: Register the `integration` marker** (the file uses `@pytest.mark.integration`, currently undeclared). Add to the **root** `pyproject.toml` `[tool.pytest.ini_options]`:
```toml
markers = ["integration: real-witness / subprocess end-to-end tests"]
```
(If a `[tool.pytest.ini_options]` block exists, add the `markers` line; else add the block.)

- [ ] **Step 3: Run the integration test — expect PASS**

Run: `cd /Users/seriouscoderone/code/locksmith && .venv/bin/python -m pytest tests/integration/test_publisher_roundtrip.py -q --import-mode=importlib`
Expected: PASS (both the original round-trip and the new CLI-driven test), no marker warning.

- [ ] **Step 4: Commit**
```bash
git add tests/integration/test_publisher_roundtrip.py pyproject.toml
git commit -m "test(publisher): drive the operator CLI end-to-end through the real witness

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Version bump to 0.1.7 + CI anchor injection + dark-build guard

**Files:**
- Modify: root `pyproject.toml` (`version = "0.1.7"`)
- Modify: `.github/workflows/release.ci.yml` (inject `$LOCKSMITH_PUBLISHER_ANCHOR` into the build env on tagged releases)
- Create: `scripts/check-anchor-present.py` (guard: a tagged release build must have a non-placeholder anchor)

**Interfaces:**
- Produces (behavior): a tagged 0.1.7 release build injects the real `publisher_anchor.json` (via the `$LOCKSMITH_PUBLISHER_ANCHOR` secret) and FAILS the build if the anchor is missing/placeholder — so 0.1.7 can never silently ship gate-dark.

- [ ] **Step 1: Write the failing guard test**

Create `tests/unit/release/test_check_anchor_present.py` (locksmith main tree):
```python
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = "scripts/check-anchor-present.py"


def _run(path):
    return subprocess.run([sys.executable, SCRIPT, "--anchor", str(path)],
                          capture_output=True, text=True)


def test_rejects_placeholder(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"publisher_aid": "ELocksmithPublisherAidPlaceholderExample00000"}))
    assert _run(p).returncode != 0


def test_accepts_real(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"publisher_aid": "ErealAID000000000000000000000000000000000000",
                             "embedded_kel_sn": 0, "toad": 3,
                             "witness_oobis": ["https://w/oobi/B/witness"]}))
    assert _run(p).returncode == 0


def test_rejects_missing(tmp_path):
    assert _run(tmp_path / "nope.json").returncode != 0
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd /Users/seriouscoderone/code/locksmith && .venv/bin/python -m pytest tests/unit/release/test_check_anchor_present.py -q --import-mode=importlib`

- [ ] **Step 3: Implement** `scripts/check-anchor-present.py`:
```python
#!/usr/bin/env python3
"""Fail if the publisher anchor is missing or still a placeholder (CI guard:
a tagged release must ship with a real KERI trust anchor, never gate-dark)."""
import argparse
import json
import sys

_PLACEHOLDER = "Placeholder"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", required=True)
    args = ap.parse_args()
    try:
        doc = json.loads(open(args.anchor).read())
    except FileNotFoundError:
        print(f"ERROR: publisher anchor not found at {args.anchor}", file=sys.stderr)
        return 1
    aid = doc.get("publisher_aid", "")
    if not aid or _PLACEHOLDER in aid:
        print(f"ERROR: placeholder/empty publisher_aid ({aid!r})", file=sys.stderr)
        return 1
    if not doc.get("witness_oobis"):
        print("ERROR: no witness_oobis in anchor", file=sys.stderr)
        return 1
    print(f"anchor OK: publisher_aid={aid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd /Users/seriouscoderone/code/locksmith && .venv/bin/python -m pytest tests/unit/release/test_check_anchor_present.py -q --import-mode=importlib`

- [ ] **Step 5: Bump version + wire CI**

Set root `pyproject.toml` `version = "0.1.7"`. In `.github/workflows/release.ci.yml`, in BOTH the macOS and Windows build jobs, BEFORE the build step, add:
```yaml
      - name: Inject publisher trust anchor (real, from secret)
        run: |
          mkdir -p src/locksmith/release
          printf '%s' "${{ secrets.LOCKSMITH_PUBLISHER_ANCHOR }}" > src/locksmith/release/publisher_anchor.json
          python scripts/check-anchor-present.py --anchor src/locksmith/release/publisher_anchor.json
```
(The build's anchor loader then finds the gitignored file. The guard fails the release if the secret is unset/placeholder.) Add a `LOCKSMITH_PUBLISHER_ANCHOR` GitHub Actions secret containing the real `publisher_anchor.json` contents — done as an operator step in Task 8 after `gen-anchor`.

- [ ] **Step 6: Commit**
```bash
git add pyproject.toml .github/workflows/release.ci.yml scripts/check-anchor-present.py tests/unit/release/test_check_anchor_present.py
git commit -m "build(release): 0.1.7 + inject publisher anchor in CI with a dark-build guard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Operator execution runbook (Phase 1 mint + Phase 2 bootstrap) — OPERATOR-DRIVEN, IRREVERSIBLE

> **Not a code task.** This is the operational ceremony, run by the operator after Tasks 1-7 are merged. It mints the permanent production trust root and ships the bootstrap release. Each step has a verification. The bran NEVER enters an automated/agent session.

**Phase 1 — mint + trust root:**

- [ ] **P1.1 Mint** (controlled machine; you hold the bran):
```bash
export LOCKSMITH_PUBLISHER_BRAN='<your-strong-bran>'      # not echoed into logs
export AWS_PROFILE=personal
cd /Users/seriouscoderone/code/locksmith/tools/publisher
/Users/seriouscoderone/code/locksmith/.venv/bin/locksmith-publisher incept \
    --name publisher --base ~/.locksmith-publisher-ks --toad 3
```
Verify: the command prints a publisher AID; the witnesses now serve it. Check 3-of-5 receipts via the public side, e.g. `kli status --name publisher --base ~/.locksmith-publisher-ks --alias publisher --verbose` → `Receipts: >=3`. **Back up the keystore dir + bran to your vault now.**

- [ ] **P1.2 Generate the trust anchor:**
```bash
locksmith-publisher gen-anchor --name publisher --base ~/.locksmith-publisher-ks --toad 3
```
Verify: `src/locksmith/release/publisher_anchor.json` exists with the real AID + 5 witness OOBIs + `toad:3` + `embedded_kel_sn:0` and `embedded_kel_hash == publisher_aid`. (Gitignored — confirm `git status` does NOT show it.)

- [ ] **P1.3 Publish the inception KEL** (so the verifier can replay the trust root). Export + upload the inception KEL to `publisher/v1/kel.cesr`:
```bash
kli export --name publisher --base ~/.locksmith-publisher-ks --alias publisher --files  # writes <aid>-kel.cesr
AWS_PROFILE=personal aws s3 cp <aid>-kel.cesr s3://releases.keri.host/publisher/v1/kel.cesr --content-type application/cesr
```
Verify: `curl -sf https://releases.keri.host/publisher/v1/kel.cesr | head -c 32` returns CESR bytes (replaces the stale 2026-06-02 content).

- [ ] **P1.4 Register the CI secret:** add a GitHub Actions secret `LOCKSMITH_PUBLISHER_ANCHOR` whose value is the exact contents of `src/locksmith/release/publisher_anchor.json` (so Task 7's CI step injects it).

**Phase 2 — bootstrap release 0.1.7:**

- [ ] **P2.1 Tag + release 0.1.7** (Tasks 1-7 merged; version already `0.1.7`). Create the signed release tag `v0.1.7` per the existing release process. CI builds + signs + notarizes the dmg/msi, injects the anchor (Task 7), runs the dark-build guard, and uploads to `s3://releases.keri.host/releases/0.1.7/`.
Verify: `aws s3 ls s3://releases.keri.host/releases/0.1.7/` shows `Locksmith-0.1.7.dmg` + `.msi`; the CI "Inject publisher trust anchor" + guard step passed.

- [ ] **P2.2 Anchor the SERVED artifacts** (download them so the seal hashes exactly what users get):
```bash
cd /tmp && mkdir anchor-0.1.7 && cd anchor-0.1.7
AWS_PROFILE=personal aws s3 cp s3://releases.keri.host/releases/0.1.7/Locksmith-0.1.7.dmg .
AWS_PROFILE=personal aws s3 cp s3://releases.keri.host/releases/0.1.7/Locksmith-0.1.7.msi .
locksmith-publisher anchor --name publisher --base ~/.locksmith-publisher-ks --version 0.1.7 \
    --macos Locksmith-0.1.7.dmg --windows Locksmith-0.1.7.msi --out-dir .   # prints {anchor_said, ...}
MAC_SHA=$(shasum -a 256 Locksmith-0.1.7.dmg | cut -d' ' -f1)
WIN_SHA=$(shasum -a 256 Locksmith-0.1.7.msi | cut -d' ' -f1)
```
Verify: `anchor` prints an `anchor_said`; `<aid>-kel.cesr` + `<anchor_said>.cesr` are in the dir.

- [ ] **P2.3 Publish:**
```bash
locksmith-publisher publish --name publisher --base ~/.locksmith-publisher-ks --version 0.1.7 \
    --anchor-said <anchor_said> --macos-sha256 "$MAC_SHA" --windows-sha256 "$WIN_SHA" --out-dir .
```
Verify: `publisher/v1/kel.cesr` (now at sn≥1), `publisher/v1/anchors/<said>.cesr`, and `appcast/v1/{macos,windows}.json` are live in S3.

- [ ] **P2.4 Verify end-to-end** with the real verifier (the gate's exact path):
```bash
cd /Users/seriouscoderone/code/locksmith
LOCKSMITH_PUBLISHER_ANCHOR=src/locksmith/release/publisher_anchor.json \
  .venv/bin/python -m locksmith.update.cli --verify-update \
    --artifact /tmp/anchor-0.1.7/Locksmith-0.1.7.dmg --platform macos
```
(Use the actual `update.cli` verify entrypoint/flags.) Verify: result `ok=True`, `witness_receipts >= 3`, version `0.1.7`. This is the gate's path; a real installed 0.1.7 will now enforce it for every future update.

- [ ] **P2.5 Record the outcome** in `project_publisher_wig_attachment_bug` memory (resolved) + a short note in the PR/commit: publisher AID, that the gate is live for 0.1.7+, and the bootstrap-TOFU/OS-signing property.

---

## Self-Review

**1. Spec coverage:** operator CLI commands → Tasks 3-4; `kli_resolve_oobi` → Task 1; `publisher_anchor.json` generator → Tasks 2-3 (`gen-anchor`); retire orphaned modules → Task 5; testing through the real-witness harness → Task 6; custody (kli keystore + bran, env var) → Tasks 3-4 + Global Constraints; bootstrap 0.1.7 + anchor injection + dark-build guard → Task 7; two-phase execution → Task 8; trust model / no verifier change → Global Constraints. ✓
**2. Placeholder scan:** every code step has real code; the one "fill from the file" pointer is Task 6 Step 1 (extend an existing test, reusing its named harness) + Task 5 conftest cleanup (depends on a grep result) — both are concrete with the exact reuse named. No TODO/TBD. ✓
**3. Type consistency:** `_bran(bran_env)`, `_read_publisher_aid(*, name, base, bran)`, `_publisher_anchor_path()`, `build_publisher_anchor(*, publisher_aid, witness_oobis, toad)`, `default_witness_pool()→[WitnessInfo(aid,oobi)]`, `anchor_release(...)→{anchor_said,...}`, `S3.default()`/`upload_release(*, bucket, kel, anchors, appcast, appcast_key)`/`put_object(*, bucket, key, data, content_type)`, `build_appcast(*, publisher_aid, publisher_kel_url, releases, current_version)` — consistent across Tasks 1-4 and match the verified library signatures.

## Notable refinements vs spec (flag for reviewer)

- `publish` builds appcasts via `build_appcast` (forgiving) rather than the existing `generate_and_upload_appcasts` (which expects a richer seal than `build_release_seal` produces). The existing `appcast` regeneration command is left untouched; its richer-seal expectation is a pre-existing gap, noted as a follow-up, not fixed here.
- `embedded_kel_hash == publisher_aid` for sn=0 (inception SAID is the prefix), so `gen-anchor` needs only the AID (no separate KEL parse). Confirmed against `publisher_anchor.example.json` (both fields identical).
