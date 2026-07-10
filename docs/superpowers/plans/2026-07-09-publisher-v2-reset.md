# Publisher v2 Reset + SAID-Native Release Seal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-incept the release publisher as a clean KERI-v2 AID and move the release seal to a SAID-native digest seal, unblocking the v0.2.20 publish on the v2 base.

**Architecture:** The publisher anchors a digest seal `{"d": <said>, "brand": <b>, "ver": <v>}` in its ixn `a`; `d` is the SAID of a release SAD `{"d", "brand", "ver", "artifacts":[{"platform","sha256"}]}` published in the JSON appcast. The verifier reads `brand`/`ver` from the tamper-proof KEL seal (omission-resistant freeze-defense), resolves the SAD from the appcast, checks `saidify(SAD)==d`, and binds the per-platform sha256. A v2 publisher hab makes all this serialize cleanly (the failure was a v1 hab getting a v2 ixn).

**Tech Stack:** Python 3.14, keri 2.0.0-dev6 (fork `6ab5019e`), `kli` CLI, click, pytest.

## Global Constraints

- **Branch:** `feat/publisher-v2-reset` (already created off `development`; spec commit `46aca58` is its first commit). Do **not** push.
- **The seal/SAD contract (exact shapes — every task uses these verbatim):**
  - Release SAD (dict, keys in THIS order): `{"d": "", "brand": <brand>, "ver": <version>, "artifacts": [{"platform": <p>, "sha256": <hex>}, ...]}`, then `keri.core.coring.Saider.saidify(sad=sad)` fills `d`. Use `ver`, **never** the KERI-reserved `v`.
  - KEL digest seal (the `a`-field entry): `{"d": <said>, "brand": <brand>, "ver": <version>}` where `<said>` == the SAD's `d`.
  - SAID recipe (both build + verify): `_, sad = Saider.saidify(sad=<dict>)`; the SAID string is `sad["d"]`. Verify by re-saidifying the resolved SAD and comparing `sad["d"]` to the KEL anchor's `d`.
- **Two packages, one checkout (this is a normal branch, not a worktree):**
  - Publisher: `tools/publisher/` (own `pyproject.toml`, `pythonpath=["src","."]`). Run its tests **from `tools/publisher/`**: `cd tools/publisher && ../../.venv/bin/python -m pytest -q`. Publisher tests may `import locksmith.update.*` (resolves this checkout's `src`).
  - Verifier: `src/locksmith/update/`. Run its tests from the repo root: `.venv/bin/python -m pytest <path> -q --import-mode=importlib`.
- **Main-session-only tasks (Tasks 1, 8, 9):** real-wallet / real-infra / real-publisher-key work — NOT subagents. Touch the live federation + the real publisher bran → each needs explicit user go-ahead; nothing is pushed or published without it.
- **`v` is reserved:** never put a business `v` field in any dict handed to `Saider.saidify` or serialized as a SAD/seal — it collides with the KERI version-string label (`deversify` raises).
- **Commit trailers** (every commit):
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn
  ```

---

### Task 1: Validate-early federation gate (MAIN SESSION — do first)

Confirm the live federation **receipts a v2 publisher's ixn** before investing in the rework. This is the exact path that failed. If it fails, **STOP** and escalate — scope grows to a federation-v2 decision (out of this plan).

**Files:** none (a live probe on a throwaway keystore).

- [ ] **Step 1: Incept a throwaway v2 AID against the real federation**

Pick a witness set from the deploy config (the same `--wit`/`--toad` the publisher uses). Run (user provides any needed bran; touches live witnesses):

```bash
cd /tmp && rm -rf ~/.keri/db/v2gate ~/.keri/ks/v2gate ~/.keri/cf/v2gate
kli init --name v2gate --base v2gate --nopasscode
kli incept --name v2gate --base v2gate --alias g --version 2.0 --transferable \
  --wit <WAN_AID> --toad 1 --receipt-endpoint
```
Expected: inception completes and reports ≥1 witness receipt (no serialization error).

- [ ] **Step 2: Interact with a v2 digest-seal anchor + collect receipts**

```bash
kli interact --name v2gate --base v2gate --alias g --receipt-endpoint \
  --data '{"d":"EAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","brand":"locksmith","ver":"0.0.0"}'
```
Expected: **"New Sequence No. 1"** and receipt collection completes with **no** `Invalid value while serializing`. (This is the v2-consistent analogue of the failing publisher call.)

- [ ] **Step 3: Record the outcome + clean up**

```bash
rm -rf ~/.keri/db/v2gate ~/.keri/ks/v2gate ~/.keri/cf/v2gate ~/.keri/reg/v2gate
```
PASS → proceed to Task 2. FAIL (serialization or receipt error) → STOP, report the exact error, do not start the rework. No commit (probe only).

---

### Task 2: Release SAD + digest-seal builders (`seal.py`)

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/seal.py`
- Test: `tools/publisher/tests/test_seal.py`

**Interfaces:**
- Produces: `build_release_sad(*, version, artifacts, brand) -> dict` (the saidified SAD) and `build_release_seal(*, version, artifacts, brand) -> dict` (the digest seal `{"d","brand","ver"}`). `artifacts = [(platform, Path), ...]`.

- [ ] **Step 1: Write the failing test**

Replace the body of `tools/publisher/tests/test_seal.py` (keep the existing `_sha256` fixture usage if any; this is the new contract):

```python
from pathlib import Path
from keri.core.coring import Saider
from locksmith_publisher.seal import build_release_sad, build_release_seal


def _tmpfile(tmp_path, name, content):
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_build_release_sad_is_saidified_with_ver_and_artifacts(tmp_path):
    a = _tmpfile(tmp_path, "app.dmg", b"macos-bytes")
    sad = build_release_sad(version="0.2.20", brand="locksmith",
                            artifacts=[("macos", a)])
    # self-addressing: re-saidify reproduces d, and there is NO reserved 'v'
    assert "v" not in sad
    assert sad["brand"] == "locksmith" and sad["ver"] == "0.2.20"
    assert sad["artifacts"][0]["platform"] == "macos"
    assert len(sad["artifacts"][0]["sha256"]) == 64
    _, recomputed = Saider.saidify(sad=dict(sad))
    assert recomputed["d"] == sad["d"]


def test_build_release_seal_is_digest_seal_with_brand_ver(tmp_path):
    a = _tmpfile(tmp_path, "app.dmg", b"macos-bytes")
    seal = build_release_seal(version="0.2.20", brand="locksmith",
                              artifacts=[("macos", a)])
    sad = build_release_sad(version="0.2.20", brand="locksmith",
                            artifacts=[("macos", a)])
    assert seal == {"d": sad["d"], "brand": "locksmith", "ver": "0.2.20"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_seal.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_release_sad'`.

- [ ] **Step 3: Implement**

Rewrite `tools/publisher/src/locksmith_publisher/seal.py`:

```python
"""Release seal — the publisher↔verifier contract anchored in the ixn ``a`` field.

SAID-native: the ixn anchors a digest seal ``{"d": <said>, "brand": <b>, "ver": <v>}``.
``d`` is the SAID of the release SAD ``{"d","brand","ver","artifacts":[{platform,sha256}]}``,
which the publisher also publishes in the JSON appcast. Verifier (locksmith/update)
reads brand/ver from the KEL seal (freeze-defense) and resolves+verifies the SAD.
Never use the reserved ``v`` field — it collides with the KERI version string.
"""
import hashlib
from pathlib import Path

from keri.core.coring import Saider


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_release_sad(*, version: str, artifacts: list[tuple[str, Path]], brand: str) -> dict:
    """The saidified release SAD. artifacts = [(platform, path), ...] in publish order."""
    sad = {
        "d": "",
        "brand": brand,
        "ver": version,
        "artifacts": [{"platform": plat, "sha256": _sha256(path)} for plat, path in artifacts],
    }
    _, sad = Saider.saidify(sad=sad)
    return sad


def build_release_seal(*, version: str, artifacts: list[tuple[str, Path]], brand: str) -> dict:
    """The KEL digest seal anchored in the ixn ``a`` field."""
    sad = build_release_sad(version=version, artifacts=artifacts, brand=brand)
    return {"d": sad["d"], "brand": brand, "ver": version}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_seal.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/seal.py tools/publisher/tests/test_seal.py
git commit -m "feat(publisher): SAID-native release SAD + digest seal builders

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 3: Anchor the digest seal + carry the SAD (`publish.py`)

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/publish.py` (`anchor_release`)
- Test: `tools/publisher/tests/test_publish_anchor.py` (new)

**Interfaces:**
- Consumes: `build_release_seal`, `build_release_sad` (Task 2).
- Produces: `anchor_release(...)` returns the existing dict **plus** `"release_sad"` (the SAD dict) so the appcast step (Task 4) can embed it. The `kli.kli_interact` call now anchors `json.dumps(build_release_seal(...))`.

- [ ] **Step 1: Write the failing test**

Create `tools/publisher/tests/test_publish_anchor.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch
from locksmith_publisher import publish


def test_anchor_release_anchors_digest_seal_and_returns_sad(tmp_path, monkeypatch):
    a = tmp_path / "app.dmg"; a.write_bytes(b"m")
    w = tmp_path / "app.msi"; w.write_bytes(b"w")
    captured = {}

    def fake_interact(*, name, alias, bran, base, data):
        captured["data"] = json.loads(data)
    monkeypatch.setattr(publish.kli, "kli_interact", fake_interact)

    # Stop after the interact by making the KEL read-back raise; we only assert
    # the anchored seal + the returned SAD contract here.
    class _Stop(Exception): ...
    monkeypatch.setattr(publish.habbing, "Habery",
                        lambda *x, **k: (_ for _ in ()).throw(_Stop()))
    try:
        publish.anchor_release(name="p", alias="p", bran="b", base="p",
                               version="0.2.20", brand="locksmith",
                               artifacts=[("macos", a), ("windows", w)], out_dir=str(tmp_path))
    except _Stop:
        pass

    seal = captured["data"]
    assert set(seal) == {"d", "brand", "ver"}
    assert seal["brand"] == "locksmith" and seal["ver"] == "0.2.20"
    assert len(seal["d"]) == 44  # qb64 SAID
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_publish_anchor.py -q`
Expected: FAIL — the current `anchor_release` anchors `{"release": {...}}`, so `set(seal)` is `{"release"}`, not `{"d","brand","ver"}`.

- [ ] **Step 3: Implement**

In `tools/publisher/src/locksmith_publisher/publish.py`, change the top of `anchor_release` (the `seal = build_release_seal(...)` + interact lines) to anchor the digest seal and keep the SAD, and add `"release_sad"` to the returned dict:

```python
    from .seal import build_release_seal, build_release_sad  # if not already module-level
    seal = build_release_seal(version=version, artifacts=artifacts, brand=brand)
    sad = build_release_sad(version=version, artifacts=artifacts, brand=brand)
    kli.kli_interact(name=name, alias=alias, bran=bran, base=base, data=json.dumps(seal))
```

At the `return {...}` of `anchor_release`, add `"release_sad": sad` to the returned dict (alongside `anchor_said`, `anchor_sn`, `kel_path`, `anchor_event_path`).

(Update the module import at the top of `publish.py` from `from .seal import build_release_seal` to `from .seal import build_release_seal, build_release_sad`.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_publish_anchor.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/publish.py tools/publisher/tests/test_publish_anchor.py
git commit -m "feat(publisher): anchor the digest seal + return the release SAD

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 4: Embed the SAD in the JSON appcast (`appcast` build + `Release`/`Appcast` aggregate + `cli.py`)

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/appcast.py` (`build_appcast` — add a `release_sad` per release entry)
- Modify: `tools/publisher/src/locksmith_publisher/cli.py` (`publish_cmd` — pass `release_sad` through to `build_appcast`)
- Modify: `src/locksmith/update/appcast.py` (`Release` gains `release_sad: dict`; `REQUIRED_REL` + `parse_appcast`)
- Test: `tools/publisher/tests/test_appcast.py` (append) and `tests/unit/test_appcast_parse_sad.py` (new, verifier side)

**Interfaces:**
- Consumes: `anchor_release(...)["release_sad"]` (Task 3).
- Produces: JSON appcast whose each release object carries `"release_sad": {d,brand,ver,artifacts}`. Verifier `Release.release_sad: dict`.

- [ ] **Step 1: Write the failing tests**

Publisher side — append to `tools/publisher/tests/test_appcast.py`:

```python
def test_build_appcast_embeds_release_sad():
    from locksmith_publisher.appcast import build_appcast
    sad = {"d": "E" + "A"*43, "brand": "locksmith", "ver": "0.2.20",
           "artifacts": [{"platform": "macos", "sha256": "a"*64}]}
    ac = build_appcast(
        publisher_aid="Epub", publisher_kel_url="https://x/kel.cesr",
        releases=[{"version": "0.2.20", "platform": "macos",
                   "artifact_url": "u", "artifact_sha256": "a"*64, "artifact_size": 1,
                   "anchor_said": sad["d"], "anchor_url": "au",
                   "released_at": "2026-07-09T00:00:00+00:00",
                   "minimum_system_version": "12.0", "release_notes_url": "rn",
                   "is_major": False, "is_critical": False,
                   "release_sad": sad}])
    import json
    doc = json.loads(ac)
    assert doc["releases"][0]["release_sad"] == sad
```

Verifier side — create `tests/unit/test_appcast_parse_sad.py`:

```python
import json
from locksmith.update.appcast import parse_appcast


def _appcast_with_sad(sad):
    return json.dumps({
        "schema_version": 1, "channel": "stable",
        "publisher_aid": "Epub", "publisher_kel_url": "https://x/kel.cesr",
        "current_version": "0.2.20",
        "releases": [{
            "version": "0.2.20", "released_at": "2026-07-09T00:00:00+00:00",
            "platform": "macos", "minimum_system_version": "12.0",
            "artifact_url": "u", "artifact_sha256": "a"*64, "artifact_size": 1,
            "anchor_url": "au", "anchor_said": sad["d"],
            "release_notes_url": "rn", "is_major": False, "is_critical": False,
            "release_sad": sad}]})


def test_parse_appcast_carries_release_sad():
    sad = {"d": "E"+"A"*43, "brand": "locksmith", "ver": "0.2.20",
           "artifacts": [{"platform": "macos", "sha256": "a"*64}]}
    ac = parse_appcast(_appcast_with_sad(sad))
    assert ac.releases[0].release_sad == sad
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_appcast.py::test_build_appcast_embeds_release_sad -q`
Run: `.venv/bin/python -m pytest tests/unit/test_appcast_parse_sad.py -q --import-mode=importlib`
Expected: publisher test FAIL (release entry lacks `release_sad`); verifier test FAIL (`Release` has no `release_sad`, and `parse_appcast` drops it).

- [ ] **Step 3: Implement (publisher build)**

In `tools/publisher/src/locksmith_publisher/appcast.py` `build_appcast`, in the per-release dict it builds (the block that sets `"anchor_said"`, `"artifact_sha256"`, ...), add:

```python
            "release_sad": r["release_sad"],
```

- [ ] **Step 4: Implement (verifier aggregate + parse)**

In `src/locksmith/update/appcast.py`: add `"release_sad"` to `REQUIRED_REL`; add `release_sad: dict` to the `Release` dataclass; and in `parse_appcast` where it constructs each `Release(...)`, pass `release_sad=r["release_sad"]`.

- [ ] **Step 5: Wire `cli.py`**

In `tools/publisher/src/locksmith_publisher/cli.py` `publish_cmd`, where it assembles the per-platform `rel = {"version": ..., "anchor_said": anchor_said, ...}` dict passed into `build_appcast`, add `"release_sad": info["release_sad"]` (from `anchor_release`'s return; `info` is the anchor result). If `publish_cmd` reads the SAD from an on-disk anchor artifact instead of `info`, read it from the same `out_dir` the anchor wrote — keep the single source: the `anchor_release` return value.

- [ ] **Step 6: Run to verify they pass**

Run both test commands from Step 2. Expected: PASS. Then the existing appcast suites: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_appcast.py tests/test_appcast_xml.py -q` and `.venv/bin/python -m pytest tests/unit/branding/test_render_packaging.py -q --import-mode=importlib` — green.

- [ ] **Step 7: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/appcast.py tools/publisher/src/locksmith_publisher/cli.py \
        tools/publisher/tests/test_appcast.py src/locksmith/update/appcast.py tests/unit/test_appcast_parse_sad.py
git commit -m "feat(appcast): embed the release SAD per release (publisher + verifier aggregate)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 5: Read the digest seal from the KEL (`kel_replay.py`)

**Files:**
- Modify: `src/locksmith/update/kel_replay.py` (`extract_release_seal`, `highest_version_for_brand`)
- Test: `tests/unit/test_kel_replay_digest_seal.py` (new) — plus update any existing kel_replay tests that assert the old `release` seal shape.

**Interfaces:**
- Produces: `extract_release_seal(state, *, anchor_said) -> dict` returns the digest seal `{"d","brand","ver"}` (the `a`-entry with a `d`). `highest_version_for_brand(state, brand) -> str | None` reads `ver` from digest seals; a seal with no `brand` counts as `"locksmith"`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_kel_replay_digest_seal.py`:

```python
from types import SimpleNamespace
from locksmith.update.kel_replay import extract_release_seal, highest_version_for_brand


def _state(events):
    return SimpleNamespace(events=events)


def _ev(said, sn, seals):
    return SimpleNamespace(said=said, sn=sn, seals=seals)


def test_extract_returns_digest_seal():
    st = _state([_ev("Eanchor", 1, [{"d": "Esad", "brand": "locksmith", "ver": "0.2.20"}])])
    seal = extract_release_seal(st, anchor_said="Eanchor")
    assert seal == {"d": "Esad", "brand": "locksmith", "ver": "0.2.20"}


def test_highest_version_reads_ver_from_digest_seals():
    st = _state([
        _ev("E1", 1, [{"d": "Ea", "brand": "locksmith", "ver": "0.2.19"}]),
        _ev("E2", 2, [{"d": "Eb", "brand": "locksmith", "ver": "0.2.20"}]),
        _ev("E3", 3, [{"d": "Ec", "brand": "usurance", "ver": "0.3.0"}]),
    ])
    assert highest_version_for_brand(st, "locksmith") == "0.2.20"
    assert highest_version_for_brand(st, "usurance") == "0.3.0"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_kel_replay_digest_seal.py -q --import-mode=importlib`
Expected: FAIL — `extract_release_seal` looks for `"release" in s`, so it finds no seal (raises `SchemaError`); `highest_version_for_brand` reads `s["release"]["v"]`.

- [ ] **Step 3: Implement**

In `src/locksmith/update/kel_replay.py`:
- `extract_release_seal`: change the inner match from `if isinstance(s, dict) and "release" in s:` to `if isinstance(s, dict) and "d" in s and "ver" in s:` and `return s`. Update the error message to "has no release digest seal".
- `highest_version_for_brand`: iterate the digest seals; for each `s` with `"d"` and `"ver"`, `brand = s.get("brand", "locksmith")`; collect `s["ver"]` where `brand == <arg>`; return the highest by `_semver_key` (keep the existing comparison helper).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_kel_replay_digest_seal.py -q --import-mode=importlib`
Expected: PASS. Then run the existing replay tests and fix any that assert the old `release`-seal shape: `.venv/bin/python -m pytest tests/ -k "kel_replay or replay" -q --import-mode=importlib`.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/kel_replay.py tests/unit/test_kel_replay_digest_seal.py
git commit -m "feat(verify): read the SAID-native digest seal from the KEL

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 6: Resolve + verify the SAD in the verifier (`verify.py`)

**Files:**
- Modify: `src/locksmith/update/verify.py` (`_assert_current_for_brand`, `verify_artifact` — resolve the SAD, verify its SAID against the KEL anchor, read the per-platform sha256 from the SAD)
- Test: `tests/unit/test_verify_sad.py` (new) — plus update existing verify tests that build the old `release` seal.

**Interfaces:**
- Consumes: `extract_release_seal` → `{"d","brand","ver"}` (Task 5); `Release.release_sad` (Task 4); `Saider.saidify` (Global Constraints recipe).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_verify_sad.py`:

```python
import pytest
from keri.core.coring import Saider
from locksmith.update.verify import _verify_sad_against_anchor  # new helper (Task 6)
from locksmith.update.errors import SignatureError


def _sad():
    _, sad = Saider.saidify(sad={"d": "", "brand": "locksmith", "ver": "0.2.20",
                                 "artifacts": [{"platform": "macos", "sha256": "a"*64}]})
    return sad


def test_verify_sad_matches_anchor_returns_artifact_sha():
    sad = _sad()
    sha = _verify_sad_against_anchor(sad, anchor_d=sad["d"], platform="macos")
    assert sha == "a"*64


def test_verify_sad_rejects_tampered_sad():
    sad = _sad()
    tampered = dict(sad)
    tampered["artifacts"] = [{"platform": "macos", "sha256": "b"*64}]  # d no longer matches
    with pytest.raises(SignatureError):
        _verify_sad_against_anchor(tampered, anchor_d=sad["d"], platform="macos")


def test_verify_sad_rejects_anchor_mismatch():
    sad = _sad()
    with pytest.raises(SignatureError):
        _verify_sad_against_anchor(sad, anchor_d="E" + "Z"*43, platform="macos")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_verify_sad.py -q --import-mode=importlib`
Expected: FAIL — `ImportError: cannot import name '_verify_sad_against_anchor'`.

- [ ] **Step 3: Implement the helper + wire it in**

In `src/locksmith/update/verify.py`, add the helper:

```python
from keri.core.coring import Saider

def _verify_sad_against_anchor(sad: dict, *, anchor_d: str, platform: str) -> str:
    """Verify the release SAD self-addresses to ``anchor_d`` and return the
    per-platform sha256. Raises SignatureError on a SAID mismatch or a missing
    platform entry."""
    _, recomputed = Saider.saidify(sad=dict(sad))
    if recomputed["d"] != sad["d"] or sad["d"] != anchor_d:
        raise SignatureError(
            "release SAD does not self-address to the KEL anchor",
            log_fields={"sad_d": sad.get("d"), "anchor_d": anchor_d})
    for art in sad.get("artifacts", []):
        if art.get("platform") == platform:
            return art["sha256"]
    raise SignatureError(f"release SAD has no artifact for platform {platform!r}",
                         log_fields={"platform": platform})
```

Then in `verify_artifact`, after `_assert_current_for_brand(...)` (which now reads brand/ver from the digest seal via Task 5), resolve + verify the SAD and use its sha256 for the artifact cross-check:

```python
    seal = extract_release_seal(state, anchor_said=embedded_kel_said or rel.anchor_said)
    seal_sha = _verify_sad_against_anchor(rel.release_sad, anchor_d=seal["d"], platform=platform)
```

Replace the existing `seal["release"]["artifacts"]` sha256 lookup in the downgrade cross-check with `seal_sha` (bind: downloaded-file sha256 == `seal_sha` == `rel.artifact_sha256`).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_verify_sad.py -q --import-mode=importlib`
Expected: PASS. Then the full verify suite, fixing tests that build the old seal shape: `.venv/bin/python -m pytest tests/ -k verify -q --import-mode=importlib`.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/verify.py tests/unit/test_verify_sad.py
git commit -m "feat(verify): resolve + SAID-verify the release SAD, bind per-platform sha256

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 7: End-to-end round-trip on the v2 base (integration test)

**Files:**
- Test: `tools/publisher/tests/test_v2_roundtrip.py` (new) — lives in the publisher suite (it may import both `locksmith_publisher.seal` and `locksmith.update.*`).

**Interfaces:** Consumes Tasks 2–6.

- [ ] **Step 1: Write the test**

Create `tools/publisher/tests/test_v2_roundtrip.py`:

```python
"""Publisher builds the SAD + digest seal, anchors it on a REAL v2 hab, and the
verifier extracts the seal, resolves the SAD from a built appcast, verifies the SAID,
and reads the per-platform sha256 — all on the v2 base (no version pins)."""
import json
from pathlib import Path
from keri.app import habbing
from keri.core import signing

from locksmith_publisher.seal import build_release_seal, build_release_sad
from locksmith.update.kel_replay import extract_release_seal
from locksmith.update.verify import _verify_sad_against_anchor


def test_v2_roundtrip(tmp_path):
    a = tmp_path / "app.dmg"; a.write_bytes(b"macos-bytes")
    seal = build_release_seal(version="0.2.20", brand="locksmith", artifacts=[("macos", a)])
    sad = build_release_sad(version="0.2.20", brand="locksmith", artifacts=[("macos", a)])

    # anchor the digest seal on a real v2 hab (default v2 — NO version pin)
    hby = habbing.Habery(name="rt", bran="A"*21,
                         salt=signing.Salter(raw=b"0123456789abcdef").qb64, temp=True)
    try:
        hab = hby.makeHab(name="pub", isith="1", icount=1, transferable=True)  # v2
        hab.interact(data=[seal], framed=True)                                  # v2 ixn, no error
        anchor = hab.kever.serder
        anchor_seals = anchor.ked["a"]
        assert anchor_seals == [seal]
    finally:
        hby.close()

    # verifier side: SAD resolves + self-addresses to the seal's d, sha256 binds
    sha = _verify_sad_against_anchor(sad, anchor_d=seal["d"], platform="macos")
    import hashlib
    assert sha == hashlib.sha256(b"macos-bytes").hexdigest()
```

- [ ] **Step 2: Run**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_v2_roundtrip.py -q`
Expected: PASS (proves the whole contract serializes + verifies on the v2 base with no version pins).

- [ ] **Step 3: Commit**

```bash
git add tools/publisher/tests/test_v2_roundtrip.py
git commit -m "test(publisher): v2 end-to-end round-trip (SAD anchor -> verify)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 8: Re-incept the v2 publisher + re-issue the trust anchor (MAIN SESSION)

Real infra (federation witnesses) + the real publisher key. User-gated at each step; nothing published.

**Files:** `src/locksmith/release/publisher_anchor.json` (regenerated, gitignored) via `tools/publisher/src/locksmith_publisher/anchor_doc.py`.

- [ ] **Step 1: Replace the v1 publisher keystore with a clean v2 AID**

Back up then destroy the v1 `publisher` keystore and re-incept at v2 (witnessed, `--receipt-endpoint`), using the same witness set/toad from the deploy config and the publisher bran:

```bash
mv ~/.keri/db/publisher ~/.keri/db/publisher.v1.bak; mv ~/.keri/ks/publisher ~/.keri/ks/publisher.v1.bak
kli init --name publisher --base publisher --passcode "$LOCKSMITH_PUBLISHER_BRAN"
kli incept --name publisher --base publisher --alias publisher --version 2.0 \
  --transferable --wit <WITS…> --toad <N> --receipt-endpoint
```
Expected: v2 icp (`KERICAACAA…`) with receipts. Record the new publisher AID (pre).

- [ ] **Step 2: Regenerate `publisher_anchor.json` for the new v2 AID**

Run `anchor_doc.py` (the publisher-anchor builder) against the new keystore to write `src/locksmith/release/publisher_anchor.json` binding the new v2 publisher AID (pre + KEL sn/said + toad). Confirm it is gitignored (per CLAUDE.md) and matches the new AID.

- [ ] **Step 3: Verify the new AID interacts + receipts with a digest seal**

Do one throwaway `anchor_release`-shaped interact on the new v2 publisher (a dummy version to a temp out-dir) and confirm no serialization error + receipts land. Do NOT publish. (This is the real-key analogue of Task 1's gate.)

- [ ] **Step 4: Record**

Write the new publisher AID + the fact that the v1 keystore is backed up (`*.v1.bak`) into the task report / commit message. No source commit here unless `anchor_doc.py` needed a change to emit v2 fields (if so, commit that with a test).

---

### Task 9: Housekeeping + re-publish v0.2.20 (MAIN SESSION — acceptance)

- [ ] **Step 1: Correct the backlog + registry**

- Edit `backlog/2026-07-09-release-seal-not-v2-cesr-serializable.md`: real cause = v1-hab/v2-interact mismatch; resolution = publisher v2 reset (this spec/plan).
- Edit `docs/keri-v2-hold-registry.md`: move the release-seal row from 🟢 ACTIONABLE to ✅ ON-V2 (publisher reset to v2 + SAID-native seal).
- Commit both docs.

- [ ] **Step 2: Re-run the real publish**

With the new v2 publisher, run the real `locksmith-publisher anchor` then `publish` for 0.2.20 (artifacts in `/tmp/promote-0.2.20/`). Expected: anchor succeeds (v2 digest seal, no serialization error), appcast carries the release SAD, KEL uploaded.

- [ ] **Step 3: Verify a real download**

Run the in-app / CLI verify path (`locksmith.update.cli`) against the live appcast for one platform; confirm it resolves the SAD, matches the SAID to the KEL anchor, and binds the artifact sha256. This is the acceptance gate.

---

## Final verification

- Publisher suite: `cd tools/publisher && ../../.venv/bin/python -m pytest -q` → green.
- Verifier suite: `.venv/bin/python -m pytest tests/unit/test_kel_replay_digest_seal.py tests/unit/test_verify_sad.py tests/unit/test_appcast_parse_sad.py tests/ -k "verify or appcast or replay" -q --import-mode=importlib` → green.
- v2 round-trip (Task 7) green.
- Live acceptance (Task 9 Step 3): a real 0.2.20 artifact verifies against the v2 publisher KEL + SAD.

## Gated follow-up (NOT in this plan)
- Push `feat/publisher-v2-reset` + merge to `development`, and push the v1-hold registry commit — on explicit user OK (finishing-a-development-branch).
- Federation v2 posture beyond Task 1's probe.
