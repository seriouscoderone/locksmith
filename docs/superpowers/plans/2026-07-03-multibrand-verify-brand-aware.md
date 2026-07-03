# Brand-Aware Update Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every white-label brand's release pass the in-app KERI update verifier while all brands share one publisher KEL, by tagging each release anchor with its brand and changing the verifier's stale-defense from "must be the KEL tip" to "no higher version exists for this brand."

**Architecture:** The release seal (anchored in the ixn `a` field) gains a `brand` field. The verifier scans the replayed KEL for the highest release version belonging to the app's own brand; a release is current if no higher version for that brand exists. Trust/integrity stay fully KERI (KEL replay + witness `toad`); brand+version are anchored seal data, and the "highest version for brand" comparison is a projection over already-verified data.

**Tech Stack:** Python 3.14, pytest, keripy (read-only KEL replay), click (publisher CLI).

**Spec:** `docs/superpowers/specs/2026-07-02-multibrand-verify-brand-aware.md`

## Global Constraints

- Run main-tree tests from the repo root with `.venv/bin/python -m pytest <path> -q --import-mode=importlib` (the top-level `packaging/` dir otherwise shadows the `packaging` library).
- Run **publisher** tests from `tools/publisher/` via `../../.venv/bin/python -m pytest tests/ -q`.
- **Locksmith stays byte-identical:** `embedded_brand` and `Brand.id` both default to `"locksmith"`; a seal with no `brand` field counts as `"locksmith"`.
- **No re-anchoring** of the shipped v0.2.18 — the fix is version-based, so both brands (already at 0.2.18) pass once the new verifier ships.
- Version comparison uses the existing `locksmith.update.appcast._semver_key` (numeric `major.minor.patch`).
- End every commit message with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Do not touch the other agent's uncommitted mailbox docs or untracked artifacts in the tree; stage only files named in each task.

---

## File Structure

- `src/locksmith/core/branding.py` — add `id` to the `Brand` dataclass so the running app can name its own brand (Task 1).
- `packaging/brandlib.py` — write `id` into the generated runtime `brand.json` (Task 1).
- `tools/publisher/src/locksmith_publisher/seal.py` — release seal gains `brand` (Task 2).
- `tools/publisher/src/locksmith_publisher/brand.py` — `brand_id()` resolver (Task 2).
- `tools/publisher/src/locksmith_publisher/publish.py`, `cli.py` — thread `brand` into the anchor (Task 2).
- `src/locksmith/update/kel_replay.py` — `highest_version_for_brand()` scan helper (Task 3).
- `src/locksmith/update/verify.py` — brand-aware, version-based stale defense (Task 4).
- `src/locksmith/core/apping.py` — pass `embedded_brand`; treat a half-filled anchor as off (Task 5).

Task order: 1 → 2 → 3 → 4 → 5. Task 4 consumes Task 3; Task 5 consumes Tasks 1 and 4. Task 2 is independent (publisher side) and may be done any time.

---

### Task 1: Runtime brand id (`Brand.id` + `brand.json`)

**Files:**
- Modify: `packaging/brandlib.py` (`runtime_brand_json`)
- Modify: `src/locksmith/core/branding.py` (`Brand`, `_from_dict`, `_DEFAULT`)
- Test: `tests/unit/branding/test_runtime_brand_json.py`, `tests/unit/branding/test_branding_loader.py`

**Interfaces:**
- Produces: `branding.brand().id` → `str` (the active brand id, e.g. `"locksmith"`, `"usurance"`; default `"locksmith"`). Generated `brand.json` now carries an `"id"` key.

- [ ] **Step 1: Write the failing test (runtime json carries id)**

Add to `tests/unit/branding/test_runtime_brand_json.py`:

```python
def test_runtime_json_carries_brand_id():
    assert brandlib.runtime_brand_json(brandlib.load_brand_manifest("locksmith"))["id"] == "locksmith"
    assert brandlib.runtime_brand_json(brandlib.load_brand_manifest("usurance"))["id"] == "usurance"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_runtime_brand_json.py::test_runtime_json_carries_brand_id -q --import-mode=importlib`
Expected: FAIL with `KeyError: 'id'`.

- [ ] **Step 3: Add `id` to `runtime_brand_json`**

In `packaging/brandlib.py`, `runtime_brand_json`, add `id` as the first key:

```python
def runtime_brand_json(manifest: dict) -> dict:
    """The brand.json runtime subset consumed by locksmith.core.branding."""
    return {
        "id": manifest["brand"]["id"],
        "display_name": manifest["brand"]["display_name"],
        "tagline": manifest["brand"]["tagline"],
        "org_name": _org_name(manifest),
        "org_domain": manifest["identity"]["org_domain"],
        "website": manifest["urls"]["website"],
        "support": manifest["urls"]["support"],
        "appcast_macos_xml": manifest["urls"]["appcast_macos_xml"],
        "appcast_windows_xml": manifest["urls"]["appcast_windows_xml"],
        "theme": dict(manifest.get("theme", {})),
    }
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_runtime_brand_json.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 5: Write the failing test (Brand carries id, defaults to locksmith)**

Add to `tests/unit/branding/test_branding_loader.py`:

```python
def test_default_brand_id_is_locksmith():
    assert branding.load_brand().id == "locksmith"


def test_brand_id_from_injected_json(tmp_path, monkeypatch):
    cfg = tmp_path / "brand.json"
    cfg.write_text(json.dumps({
        "id": "usurance", "display_name": "Usurance", "tagline": "t",
        "org_name": "usurance.com", "org_domain": "usurance.com",
        "website": "https://usurance.com", "support": "https://usurance.com/help",
        "theme": {},
    }))
    monkeypatch.setenv("LOCKSMITH_BRAND_CONFIG", str(cfg))
    branding._reset_cache_for_tests()
    assert branding.brand().id == "usurance"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_branding_loader.py::test_default_brand_id_is_locksmith tests/unit/branding/test_branding_loader.py::test_brand_id_from_injected_json -q --import-mode=importlib`
Expected: FAIL — `AttributeError: 'Brand' object has no attribute 'id'`.

- [ ] **Step 7: Add `id` to `Brand`, `_from_dict`, `_DEFAULT`**

In `src/locksmith/core/branding.py`:

Add the field to the dataclass (after `support`, before the appcast fields — it has a default, and all fields before it are non-default):

```python
@dataclass(frozen=True)
class Brand:
    display_name: str
    tagline: str
    org_name: str
    org_domain: str
    website: str
    support: str
    id: str = "locksmith"
    appcast_macos_xml: str = ""
    appcast_windows_xml: str = ""
    theme: dict = field(default_factory=dict)
```

Add `id="locksmith",` to the `_DEFAULT = Brand(...)` literal (e.g. right after `support=...`).

Add to `_from_dict` (right after `display_name=...`):

```python
        id=doc.get("id", _DEFAULT.id),
```

- [ ] **Step 8: Run it to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/branding -q --import-mode=importlib`
Expected: PASS (all branding tests, including the two new ones).

- [ ] **Step 9: Commit**

```bash
git add packaging/brandlib.py src/locksmith/core/branding.py \
        tests/unit/branding/test_runtime_brand_json.py tests/unit/branding/test_branding_loader.py
git commit -m "feat(branding): expose brand id at runtime (Brand.id + brand.json)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Release seal carries `brand`

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/seal.py` (`build_release_seal`)
- Modify: `tools/publisher/src/locksmith_publisher/brand.py` (add `brand_id()`)
- Modify: `tools/publisher/src/locksmith_publisher/publish.py` (`anchor_release`)
- Modify: `tools/publisher/src/locksmith_publisher/cli.py` (`anchor_cmd`)
- Test: `tools/publisher/tests/test_seal.py`, `tools/publisher/tests/test_brand.py`, `tools/publisher/tests/test_cli.py`

**Interfaces:**
- Produces: seal shape `{"release": {"brand": <id>, "v": <ver>, "artifacts": [...]}}`; `brand.brand_id() -> str`; `anchor_release(..., brand=<id>, ...)`.

All publisher steps run from `tools/publisher/`.

- [ ] **Step 1: Update the seal test to require `brand`**

Replace the body of `test_build_release_seal_shape` in `tools/publisher/tests/test_seal.py`:

```python
def test_build_release_seal_shape(tmp_path):
    mac = tmp_path / "Locksmith-macos.dmg"; mac.write_bytes(b"mac-bytes")
    win = tmp_path / "Locksmith-win.msi"; win.write_bytes(b"win-bytes")
    seal = build_release_seal(version="0.2.0", brand="usurance",
                              artifacts=[("macos", mac), ("windows", win)])
    assert seal == {"release": {"brand": "usurance", "v": "0.2.0", "artifacts": [
        {"platform": "macos", "sha256": hashlib.sha256(b"mac-bytes").hexdigest()},
        {"platform": "windows", "sha256": hashlib.sha256(b"win-bytes").hexdigest()},
    ]}}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_seal.py -q`
Expected: FAIL — `build_release_seal() got an unexpected keyword argument 'brand'`.

- [ ] **Step 3: Add `brand` to `build_release_seal`**

In `tools/publisher/src/locksmith_publisher/seal.py`:

```python
def build_release_seal(*, version: str, artifacts: list[tuple[str, Path]], brand: str) -> dict:
    """artifacts = [(platform, path), ...] in publish order."""
    return {"release": {"brand": brand, "v": version, "artifacts": [
        {"platform": plat, "sha256": _sha256(path)} for plat, path in artifacts
    ]}}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_seal.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing test for `brand_id()`**

Add to `tools/publisher/tests/test_brand.py`:

```python
def test_brand_id_from_brandlib(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(0, "usurance\n"))
    assert brand.brand_id() == "usurance"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_brand.py::test_brand_id_from_brandlib -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'brand_id'`.

- [ ] **Step 7: Add `brand_id()` to publisher `brand.py`**

In `tools/publisher/src/locksmith_publisher/brand.py`, after `release_prefix()`:

```python
def brand_id() -> str:
    return _brandlib_id("id")
```

- [ ] **Step 8: Run it to verify it passes**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_brand.py -q`
Expected: PASS.

- [ ] **Step 9: Thread `brand` through `anchor_release`**

In `tools/publisher/src/locksmith_publisher/publish.py`, change the `anchor_release` signature and the `build_release_seal` call:

```python
def anchor_release(*, name, alias, bran, base, version, brand,
                   artifacts: list[tuple[str, Path]], out_dir: str) -> dict:
    """Anchor one release. Returns {anchor_said, anchor_sn, kel_path, anchor_event_path}."""
    seal = build_release_seal(version=version, artifacts=artifacts, brand=brand)
    kli.kli_interact(name=name, alias=alias, bran=bran, base=base, data=json.dumps(seal))
    # ... rest unchanged ...
```

- [ ] **Step 10: Resolve + pass `brand` in `anchor_cmd`**

In `tools/publisher/src/locksmith_publisher/cli.py`, `anchor_cmd`:

```python
def anchor_cmd(name, base, alias, bran_env, version, macos_path, windows_path, out_dir):
    """Sign + witness the release seal over the (served) artifacts; export the KEL."""
    from . import brand
    info = publish.anchor_release(
        name=name, alias=alias, bran=_bran(bran_env), base=base, version=version,
        brand=brand.brand_id(),
        artifacts=[("macos", macos_path), ("windows", windows_path)], out_dir=out_dir)
    click.echo(json.dumps(info, indent=2))
```

- [ ] **Step 11: Update the CLI anchor test to assert brand is threaded**

In `tools/publisher/tests/test_cli.py`, in the anchor test (the one that mocks `cli_mod.publish.anchor_release` into `seen`), add near the other monkeypatches:

```python
    monkeypatch.setattr(brand_mod, "brand_id", lambda: "locksmith")
```

and after the existing assertions:

```python
    assert seen["brand"] == "locksmith"
```

- [ ] **Step 12: Run the full publisher suite**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/ -q`
Expected: PASS (all publisher tests).

- [ ] **Step 13: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/seal.py \
        tools/publisher/src/locksmith_publisher/brand.py \
        tools/publisher/src/locksmith_publisher/publish.py \
        tools/publisher/src/locksmith_publisher/cli.py \
        tools/publisher/tests/test_seal.py tools/publisher/tests/test_brand.py \
        tools/publisher/tests/test_cli.py
git commit -m "feat(publisher): tag the release seal with the active brand

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `highest_version_for_brand` KEL scan helper

**Files:**
- Modify: `src/locksmith/update/kel_replay.py` (import `_semver_key`; add helper)
- Test: `tests/unit/update/test_kel_replay.py`

**Interfaces:**
- Consumes: `KelState`, `ReplayedEvent` (dataclasses: `ReplayedEvent(sn, said, ilk, seals, receipts)`), `locksmith.update.appcast._semver_key`.
- Produces: `highest_version_for_brand(state: KelState, brand: str) -> str | None` — highest semver among release seals whose brand equals `brand` (a seal with no `brand` key counts as `"locksmith"`); `None` if none.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/update/test_kel_replay.py`:

```python
def _ev(sn, brand, ver):
    seal = {"release": {"v": ver, "artifacts": []}}
    if brand is not None:
        seal["release"]["brand"] = brand
    return ReplayedEvent(sn=sn, said=f"E{sn}", ilk="ixn", seals=[seal], receipts=3)


def _state(events):
    return KelState(publisher_aid="Epub", current_sn=events[-1].sn,
                    current_said=events[-1].said, current_keys=("K",),
                    next_digest="N", toad=3, events=events)


def test_highest_version_for_brand_scopes_by_brand():
    from locksmith.update.kel_replay import highest_version_for_brand
    st = _state([_ev(10, "locksmith", "0.2.17"), _ev(12, "locksmith", "0.2.18"),
                 _ev(13, "usurance", "0.2.18"), _ev(14, "usurance", "0.2.20")])
    assert highest_version_for_brand(st, "locksmith") == "0.2.18"
    assert highest_version_for_brand(st, "usurance") == "0.2.20"


def test_highest_version_brandless_counts_as_locksmith():
    from locksmith.update.kel_replay import highest_version_for_brand
    st = _state([_ev(1, None, "0.1.0"), _ev(2, None, "0.2.18")])
    assert highest_version_for_brand(st, "locksmith") == "0.2.18"
    assert highest_version_for_brand(st, "usurance") is None
```

Ensure `ReplayedEvent` is imported at the top of the test file (add to the existing `from locksmith.update.kel_replay import (...)` block if absent).

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/update/test_kel_replay.py::test_highest_version_for_brand_scopes_by_brand -q --import-mode=importlib`
Expected: FAIL — `ImportError: cannot import name 'highest_version_for_brand'`.

- [ ] **Step 3: Implement the helper**

In `src/locksmith/update/kel_replay.py`, add the import near the top (after the existing `from locksmith.update.errors import (...)`):

```python
from locksmith.update.appcast import _semver_key
```

and add at the end of the file:

```python
def highest_version_for_brand(state: KelState, brand: str) -> str | None:
    """Highest semver among release seals in the KEL whose brand == ``brand``.

    A seal with no ``brand`` field counts as brand ``"locksmith"`` (every
    pre-multibrand release was Locksmith). Returns ``None`` if no release seal
    for ``brand`` exists.
    """
    versions = []
    for ev in state.events:
        for s in ev.seals:
            if isinstance(s, dict) and "release" in s:
                rel = s["release"]
                if rel.get("brand", "locksmith") == brand and "v" in rel:
                    versions.append(rel["v"])
    return max(versions, key=_semver_key) if versions else None
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/update/test_kel_replay.py -q --import-mode=importlib`
Expected: PASS (all kel_replay tests).

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/update/kel_replay.py tests/unit/update/test_kel_replay.py
git commit -m "feat(update): highest_version_for_brand KEL scan helper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Brand-aware, version-based stale defense in `verify_artifact`

**Files:**
- Modify: `src/locksmith/update/verify.py` (imports; new `_assert_current_for_brand`; `verify_artifact` signature + replace the sn-based block)
- Test: `tests/unit/update/test_verify.py`

**Interfaces:**
- Consumes: `highest_version_for_brand` (Task 3), `_semver_key`, `extract_release_seal`, `SignatureError`, `StaleAppcastError`.
- Produces: `verify_artifact(..., embedded_brand: str = "locksmith")`; module-level `_assert_current_for_brand(state, *, version, embedded_brand, anchor_said)`.

- [ ] **Step 1: Write the failing tests (unit-test the new check helper)**

Add to `tests/unit/update/test_verify.py`:

```python
from locksmith.update.kel_replay import KelState, ReplayedEvent
from locksmith.update.verify import _assert_current_for_brand


def _mkstate(events):
    return KelState(publisher_aid="Epub", current_sn=events[-1].sn,
                    current_said=events[-1].said, current_keys=("K",),
                    next_digest="N", toad=3, events=events)


def _mkev(sn, brand, ver):
    rel = {"v": ver, "artifacts": []}
    if brand is not None:
        rel["brand"] = brand
    return ReplayedEvent(sn=sn, said=f"E{sn}", ilk="ixn",
                         seals=[{"release": rel}], receipts=3)


def test_current_for_brand_passes_when_not_tip_but_same_version():
    # Reproduces v0.2.18: Locksmith (sn=12) is NOT the tip (Usurance sn=13 is),
    # yet it must pass because no higher Locksmith version exists.
    st = _mkstate([_mkev(12, "locksmith", "0.2.18"), _mkev(13, "usurance", "0.2.18")])
    _assert_current_for_brand(st, version="0.2.18", embedded_brand="locksmith",
                              anchor_said="E12")  # no raise
    _assert_current_for_brand(st, version="0.2.18", embedded_brand="usurance",
                              anchor_said="E13")  # no raise


def test_current_for_brand_rejects_cross_brand_anchor():
    st = _mkstate([_mkev(12, "locksmith", "0.2.18")])
    with pytest.raises(SignatureError):
        _assert_current_for_brand(st, version="0.2.18", embedded_brand="usurance",
                                  anchor_said="E12")


def test_current_for_brand_rejects_freeze_when_higher_version_exists():
    st = _mkstate([_mkev(12, "locksmith", "0.2.18"), _mkev(14, "locksmith", "0.2.19")])
    with pytest.raises(StaleAppcastError):
        _assert_current_for_brand(st, version="0.2.18", embedded_brand="locksmith",
                                  anchor_said="E12")


def test_current_for_brand_brandless_anchor_is_locksmith():
    st = _mkstate([_mkev(12, None, "0.2.18")])
    _assert_current_for_brand(st, version="0.2.18", embedded_brand="locksmith",
                              anchor_said="E12")  # no raise
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/update/test_verify.py::test_current_for_brand_passes_when_not_tip_but_same_version -q --import-mode=importlib`
Expected: FAIL — `ImportError: cannot import name '_assert_current_for_brand'`.

- [ ] **Step 3: Add imports + the check helper**

In `src/locksmith/update/verify.py`:

Add `_semver_key` to the existing `from locksmith.update.appcast import (...)` block, and `highest_version_for_brand` to the existing `from locksmith.update.kel_replay import (...)` block (both import blocks already exist).

Add this module-level function (near `verify_artifact`):

```python
def _assert_current_for_brand(state, *, version, embedded_brand, anchor_said):
    """Brand-aware, version-based stale/spoofing defense.

    Rejects (1) an anchor whose seal brand isn't this app's brand, and (2) a
    release that a higher-version anchor for THIS brand supersedes (freeze).
    A seal with no ``brand`` field counts as ``"locksmith"``.
    """
    seal = extract_release_seal(state, anchor_said=anchor_said)
    anchor_brand = seal["release"].get("brand", "locksmith")
    if anchor_brand != embedded_brand:
        raise SignatureError(
            f"anchor brand {anchor_brand!r} does not match app brand {embedded_brand!r}",
            log_fields={"anchor_brand": anchor_brand, "embedded_brand": embedded_brand},
        )
    highest = highest_version_for_brand(state, embedded_brand)
    if highest is not None and _semver_key(highest) > _semver_key(version):
        raise StaleAppcastError(
            f"a newer {embedded_brand} release (v{highest}) exists; "
            f"appcast points at v{version}",
            log_fields={"brand": embedded_brand, "latest_version": highest,
                        "appcast_version": version},
        )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/update/test_verify.py -k current_for_brand -q --import-mode=importlib`
Expected: PASS (4 new tests).

- [ ] **Step 5: Wire the helper into `verify_artifact` and add `embedded_brand`**

In `src/locksmith/update/verify.py`, change the `verify_artifact` signature to add `embedded_brand`:

```python
def verify_artifact(
    *,
    artifact_path: Path,
    appcast_raw: str | bytes,
    platform: str,
    embedded_publisher_aid: str,
    embedded_kel_sn: int,
    embedded_kel_said: str | None,
    toad: int,
    embedded_brand: str = "locksmith",
) -> VerificationResult:
```

Then **replace** the KEL-position stale block (currently the `anchor_event = matching[0]` line through the second `raise StaleAppcastError(...)` — the whole `if anchor_event.sn < state.current_sn:` branch) with:

```python
    anchor_event = matching[0]
    _assert_current_for_brand(state, version=rel.version,
                              embedded_brand=embedded_brand,
                              anchor_said=rel.anchor_said)
```

Leave the rest of the function (fetch anchor URL, SAID match, downgrade re-check, artifact hashing, `VerificationResult`) unchanged — `anchor_event.receipts` is still used at the return.

- [ ] **Step 6: Run the full verify + kel_replay suites**

Run: `.venv/bin/python -m pytest tests/unit/update/test_verify.py tests/unit/update/test_kel_replay.py -q --import-mode=importlib`
Expected: PASS — the new tests plus all existing fixture tests (happy path, stale, downgrade, hash-mismatch) stay green: existing fixtures have brand-less seals + default `embedded_brand="locksmith"`, and the highest Locksmith version equals the appcast's current version, so nothing regresses.

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/update/verify.py tests/unit/update/test_verify.py
git commit -m "feat(update): brand-aware version-based stale defense in verify_artifact

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: App gate — pass `embedded_brand`; half-filled anchor is off

**Files:**
- Modify: `src/locksmith/core/apping.py` (`_anchor_and_appcast_or_dark`, `_run_verify_artifact`, imports)
- Test: `tests/unit/update/test_updater_gate.py`

**Interfaces:**
- Consumes: `branding.brand().id` (Task 1), `verify_artifact(..., embedded_brand=...)` (Task 4), `_load_anchor_and_appcast` (returns `(appcast_raw, aid, sn, said, toad, platform)`).
- Produces: the gate skips (returns `None`) when the anchor's `sn`/`said` is `None`; `verify_artifact` is always called with `embedded_brand=branding.brand().id`.

- [ ] **Step 1: Write the failing test (half-filled anchor is off)**

Add to `tests/unit/update/test_updater_gate.py`:

```python
def test_gate_dark_when_anchor_half_filled(monkeypatch):
    # A present-but-incomplete anchor (null sn/said) must be treated as OFF,
    # not fed into verify_artifact (which would raise TypeError).
    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast",
        lambda platform: ("<appcast/>", "Epub", None, None, 3, platform),
        raising=True,
    )
    assert apping._anchor_and_appcast_or_dark("macos") is None


def test_gate_returns_tuple_when_anchor_complete(monkeypatch):
    complete = ("<appcast/>", "Epub", 5, "Esaid", 3, "macos")
    monkeypatch.setattr(
        apping, "_load_anchor_and_appcast", lambda platform: complete, raising=True,
    )
    assert apping._anchor_and_appcast_or_dark("macos") == complete
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/update/test_updater_gate.py::test_gate_dark_when_anchor_half_filled -q --import-mode=importlib`
Expected: FAIL — `_anchor_and_appcast_or_dark` returns the tuple (not `None`) for a half-filled anchor.

- [ ] **Step 3: Treat a half-filled anchor as off**

In `src/locksmith/core/apping.py`, replace `_anchor_and_appcast_or_dark` body:

```python
def _anchor_and_appcast_or_dark(platform: str):
    """Return the loaded ``(appcast_raw, aid, sn, said, toad, platform)`` tuple,
    or ``None`` when OFF (no enforceable publisher anchor injected yet).

    OFF means: the anchor file is missing (``FileNotFoundError``), OR it is
    present but half-filled — no pinned KEL ``sn``/``said`` to enforce against.
    A ``NetworkError`` from the appcast fetch propagates so the gate fails closed.
    """
    try:
        loaded = _load_anchor_and_appcast(platform)
    except FileNotFoundError:
        return None
    _appcast_raw, _aid, kel_sn, kel_said, _toad, _plat = loaded
    if kel_sn is None or kel_said is None:
        return None
    return loaded
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/update/test_updater_gate.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 5: Write the failing test (embedded_brand is passed)**

Add to `tests/unit/update/test_updater_gate.py`:

```python
def test_run_verify_artifact_passes_embedded_brand(monkeypatch):
    from locksmith.core import branding
    monkeypatch.setattr(branding, "brand", lambda: types.SimpleNamespace(id="usurance"), raising=True)
    seen = {}
    monkeypatch.setattr(apping, "verify_artifact", lambda **k: seen.update(k), raising=True)
    loaded = ("<appcast/>", "Epub", 5, "Esaid", 3, "macos")
    apping._run_verify_artifact(Path("/tmp/x"), loaded, "macos")
    assert seen["embedded_brand"] == "usurance"
```

Ensure `types` and `Path` are imported at the top of the test file (add `import types` / `from pathlib import Path` if absent).

- [ ] **Step 6: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/update/test_updater_gate.py::test_run_verify_artifact_passes_embedded_brand -q --import-mode=importlib`
Expected: FAIL — `KeyError: 'embedded_brand'` (not yet passed).

- [ ] **Step 7: Pass `embedded_brand` from the running app's brand**

In `src/locksmith/core/apping.py`, add the import near the other `locksmith.core` imports:

```python
from locksmith.core import branding
```

and in `_run_verify_artifact`, add `embedded_brand`:

```python
    appcast_raw, publisher_aid, kel_sn, kel_said, toad, _plat = loaded
    return verify_artifact(
        artifact_path=artifact_path,
        appcast_raw=appcast_raw,
        platform=platform,
        embedded_publisher_aid=publisher_aid,
        embedded_kel_sn=kel_sn,
        embedded_kel_said=kel_said,
        toad=toad,
        embedded_brand=branding.brand().id,
    )
```

- [ ] **Step 8: Run the full updater-gate suite**

Run: `.venv/bin/python -m pytest tests/unit/update/test_updater_gate.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 9: Run the whole update + branding suite (regression)**

Run: `.venv/bin/python -m pytest tests/unit/update tests/unit/branding -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/locksmith/core/apping.py tests/unit/update/test_updater_gate.py
git commit -m "feat(update): gate passes embedded_brand; half-filled anchor stays off

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

Run both suites from their correct roots:

```bash
.venv/bin/python -m pytest tests/unit/update tests/unit/branding -q --import-mode=importlib
cd tools/publisher && ../../.venv/bin/python -m pytest tests/ -q
```

Both must be green. The load-bearing outcome: `test_current_for_brand_passes_when_not_tip_but_same_version` reproduces today's v0.2.18 situation (Locksmith not at the KEL tip) and passes — confirming the fix without re-anchoring.
