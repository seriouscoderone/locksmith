# Brand-Aware Release Publisher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the off-CI release publisher (`tools/publisher/`) resolve a brand's artifact prefix, S3 release prefix, and website from the active brand via `brandlib`, so `LOCKSMITH_BRAND=usurance locksmith-publisher …` anchors/enumerates/builds-the-appcast under `usurance/releases/…` — closing the last gap before the first Usurance cut, with Locksmith byte-identical.

**Architecture:** `brandlib` is the single brand-identity source. Its `id` CLI gains computed `release_prefix` (`releases` for locksmith, `<brand>/releases` else) and `website`. CI's `s3prefix` step calls it (dropping its duplicate bash `case`). A small publisher helper shells out to the same CLI; the publisher's 6 hardcoded `releases/` paths and its `locksmith.app` info URL become brand-derived.

**Tech Stack:** Python 3.14, `packaging/brandlib.py` (tomllib), GitHub Actions YAML, `tools/publisher/` (separate package, boto3, click), pytest.

## Global Constraints

- **Locksmith byte-identical.** `release_prefix` for `locksmith` is `releases` and its `website` is `https://locksmith.app`, so every locksmith S3 key, appcast URL, and info URL is unchanged. No regression to the live pipeline.
- **Shared publisher.** One keri.host AID / KEL / witnesses / S3 bucket / CDN for both brands; no per-brand AID or infra. `deploy_config.json` stays one shared infra file.
- **Single source of truth.** `release_prefix` is computed only in `brandlib`; CI and the publisher both call `python -m brandlib id release_prefix`. No duplicated rule.
- **No new `brand.toml` field.** `release_prefix` is a convention: `"releases"` if `brand.id == "locksmith"`, else `f"{brand.id}/releases"`.
- **Fail loud.** If the brandlib resolve fails (non-zero / empty), the publisher raises — it must never silently fall back to `releases/` for a non-locksmith brand.
- **Test env.** Repo venv `/Users/seriouscoderone/code/locksmith/.venv/bin/python`, always `--import-mode=importlib`. Branding tests run from the repo root; **publisher tests run from `tools/publisher/`**. The publisher bare-imports `locksmith.*` (resolves to the MAIN checkout from a worktree per CLAUDE.md) — the new logic is brand-string construction with the subprocess mocked, so its unit tests are validatable in isolation.
- **Worktree.** All work in `~/code/locksmith-branding` on `feat/white-label-logos`. Commit only each task's explicit files (never `git add -A`).

---

## File Structure

- `packaging/brandlib.py` — extend `_identity_value` with computed `release_prefix` + `website`; update the CLI usage string.
- `tests/unit/branding/test_brandlib_identity_cli.py` — add assertions for the two new fields.
- `tools/publisher/src/locksmith_publisher/brand.py` — **new**: shells out to `brandlib id <field>` for the active brand; fail-loud.
- `tools/publisher/tests/test_brand.py` — **new**: covers the resolver (subprocess mocked).
- `tools/publisher/src/locksmith_publisher/s3_client.py` — `list_release_versions` gains a `prefix` param.
- `tools/publisher/src/locksmith_publisher/appcast.py` — `GeneratorConfig` gains `release_prefix` + `release_notes_base` (+ optional `brand_title`); thread through the enumerate call + 3 URL builders + info URL + XML title.
- `tools/publisher/src/locksmith_publisher/cli.py` — `_artifact_url` + `publish_cmd._key` use `release_prefix`; `publish_cmd` + `appcast_cmd` resolve brand values from `brand.py`.
- `.github/workflows/release.ci.yml` — `s3prefix` step (both jobs) calls brandlib.

---

### Task 1: `brandlib id` — add `release_prefix` + `website`

**Files:**
- Modify: `packaging/brandlib.py` (`_identity_value` ~line 102, `_main` usage string ~line 124)
- Test: `tests/unit/branding/test_brandlib_identity_cli.py`

**Interfaces:**
- Consumes: existing `load_brand_manifest(brand_id)`.
- Produces: `python -m brandlib id release_prefix` → `releases` (locksmith) / `<brand>/releases` (else); `python -m brandlib id website` → `brand.toml [urls].website`.

- [ ] **Step 1: Add failing assertions**

Append to `tests/unit/branding/test_brandlib_identity_cli.py`:

```python
def test_release_prefix():
    assert _run("release_prefix", "locksmith").stdout.strip() == "releases"
    assert _run("release_prefix", "usurance").stdout.strip() == "usurance/releases"


def test_website():
    assert _run("website", "locksmith").stdout.strip() == "https://locksmith.app"
    assert _run("website", "usurance").stdout.strip() == "https://usurance.com"
```

- [ ] **Step 2: Run to verify they fail**

Run: `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/unit/branding/test_brandlib_identity_cli.py -q --import-mode=importlib -k "release_prefix or website"`
Expected: FAIL — `release_prefix`/`website` are unknown fields (exit 2 → empty stdout, assertion fails).

- [ ] **Step 3: Implement the two computed fields**

In `packaging/brandlib.py`, replace the body of `_identity_value`:

```python
def _identity_value(field: str, brand_id: str | None = None) -> str:
    m = load_brand_manifest(brand_id)
    if field == "id":
        return m["brand"]["id"]
    if field == "display_name":
        return m["brand"]["display_name"]
    if field == "release_prefix":
        # Convention (single source of truth for CI + publisher): locksmith is
        # back-compatible `releases`; every other brand is namespaced.
        bid = m["brand"]["id"]
        return "releases" if bid == "locksmith" else f"{bid}/releases"
    if field == "website":
        return m["urls"]["website"]
    ident = m.get("identity", {})
    if field not in ident:
        raise KeyError(field)
    return ident[field]
```

And update the usage string in `_main`:

```python
    print("usage: python -m brandlib id "
          "<display_name|artifact_prefix|bundle_id|data_dir|id|release_prefix|website>",
          file=sys.stderr)
```

- [ ] **Step 4: Run to verify pass**

Run: `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/unit/branding/test_brandlib_identity_cli.py -q --import-mode=importlib`
Expected: PASS (all, incl. the original 3).

- [ ] **Step 5: Commit**

```bash
git add packaging/brandlib.py tests/unit/branding/test_brandlib_identity_cli.py
git commit -m "feat(branding): brandlib id release_prefix + website"
```

---

### Task 2: CI `s3prefix` → brandlib (drop the bash case)

**Files:**
- Modify: `.github/workflows/release.ci.yml` (the two `Resolve S3 key prefix for brand` / `s3prefix` steps added in Phase-3 Task 5)

**Interfaces:**
- Consumes: Task 1 (`python -m brandlib id release_prefix`); the existing job-level `LOCKSMITH_BRAND` env.
- Produces: `steps.s3prefix.outputs.value` unchanged in name/meaning (`releases` / `usurance/releases`).

- [ ] **Step 1: Replace both `s3prefix` step bodies**

For each job (`build-macos`, `build-windows`), the `s3prefix` step's `run:` becomes (bash; brandlib needs `packaging/` on path, matching the other brandlib calls):

```yaml
      - name: Resolve S3 key prefix for brand
        id: s3prefix
        shell: bash
        run: |
          # Single source of truth: brandlib computes the per-brand prefix
          # (locksmith -> releases; else <brand>/releases). Keep in sync with
          # the off-CI publisher, which calls the same brandlib id.
          echo "value=$(cd packaging && python -m brandlib id release_prefix)" >> "$GITHUB_OUTPUT"
```

(macOS runs `python` inside `/tmp/venv`; ensure the step runs after venv activation like the sibling brandlib/prefix steps — mirror the existing `prefix` step's shell/activation.)

- [ ] **Step 2: Verify YAML + no leftover case statement**

Run (from worktree root):
```bash
/Users/seriouscoderone/code/locksmith/.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/release.ci.yml')); print('OK')"
grep -n "case \"\$LOCKSMITH_BRAND\"" .github/workflows/release.ci.yml || echo "no case statement (good)"
grep -c "brandlib id release_prefix" .github/workflows/release.ci.yml   # expect 2
```
Expected: `OK`; no `case` statement; count 2.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.ci.yml
git commit -m "ci(release): s3prefix from brandlib id release_prefix (single source)"
```

---

### Task 3: Publisher brand resolver (`brand.py`)

**Files:**
- Create: `tools/publisher/src/locksmith_publisher/brand.py`
- Test: `tools/publisher/tests/test_brand.py`

**Interfaces:**
- Consumes: Task 1 (`python -m brandlib id <field>`); `$LOCKSMITH_BRAND` (via brandlib's default).
- Produces: `release_prefix() -> str`, `artifact_prefix() -> str`, `website() -> str` — each returns the active brand's value; raises `RuntimeError` on brandlib failure (fail-loud).

- [ ] **Step 1: Write the failing test**

Create `tools/publisher/tests/test_brand.py`:

```python
import subprocess
import pytest
from locksmith_publisher import brand


class _R:
    def __init__(self, rc, out, err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_release_prefix_from_brandlib(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(0, "usurance/releases\n"))
    assert brand.release_prefix() == "usurance/releases"


def test_artifact_prefix_from_brandlib(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(0, "Usurance\n"))
    assert brand.artifact_prefix() == "Usurance"


def test_website_from_brandlib(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(0, "https://usurance.com\n"))
    assert brand.website() == "https://usurance.com"


def test_fail_loud_on_nonzero(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(1, "", "boom"))
    with pytest.raises(RuntimeError):
        brand.release_prefix()


def test_fail_loud_on_empty(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(0, "  \n"))
    with pytest.raises(RuntimeError):
        brand.artifact_prefix()
```

- [ ] **Step 2: Run to verify it fails**

Run (from `tools/publisher/`): `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_brand.py -q --import-mode=importlib`
Expected: FAIL — `No module named locksmith_publisher.brand`.

- [ ] **Step 3: Implement `brand.py`**

```python
# -*- encoding: utf-8 -*-
"""Resolve the active brand's identity for the publisher.

The publisher runs from the repo, so `packaging/brandlib.py` is present. We
shell out to the same `python -m brandlib id <field>` CLI the build scripts
use (single source of truth), rather than importing brandlib (keeps this
package decoupled from packaging/). Fail-loud: a failed resolve must never
silently fall back to the default `releases/` prefix for a non-locksmith brand.
"""
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "src" / "locksmith" / "release").is_dir():
            return parent
    raise RuntimeError(
        "could not locate repo root (src/locksmith/release/) — run from the repo"
    )


def _brandlib_id(field: str) -> str:
    res = subprocess.run(
        [sys.executable, "-m", "brandlib", "id", field],
        cwd=_repo_root() / "packaging",
        capture_output=True,
        text=True,
    )
    value = res.stdout.strip()
    if res.returncode != 0 or not value:
        raise RuntimeError(
            f"brandlib id {field!r} failed: rc={res.returncode} "
            f"stderr={res.stderr.strip()!r} — refusing to guess the brand prefix"
        )
    return value


def release_prefix() -> str:
    return _brandlib_id("release_prefix")


def artifact_prefix() -> str:
    return _brandlib_id("artifact_prefix")


def website() -> str:
    return _brandlib_id("website")
```

- [ ] **Step 4: Run to verify pass**

Run (from `tools/publisher/`): `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_brand.py -q --import-mode=importlib`
Expected: PASS (5).

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/brand.py tools/publisher/tests/test_brand.py
git commit -m "feat(publisher): active-brand resolver via brandlib (fail-loud)"
```

---

### Task 4: `s3_client.list_release_versions` — `prefix` param

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/s3_client.py` (`list_release_versions`, ~line 109-118)
- Test: `tools/publisher/tests/` (add `test_s3_prefix.py`)

**Interfaces:**
- Consumes: nothing new (plain param).
- Produces: `list_release_versions(self, *, bucket: str, prefix: str = "releases") -> list[str]` — enumerates `X.Y.Z` dirs under `<prefix>/`.

- [ ] **Step 1: Write the failing test**

Create `tools/publisher/tests/test_s3_prefix.py`:

```python
from locksmith_publisher.s3_client import S3


class _FakePaginator:
    def __init__(self, keys):
        self._keys = keys
        self.seen_prefix = None

    def paginate(self, *, Bucket, Prefix):
        self.seen_prefix = Prefix
        return [{"Contents": [{"Key": k} for k in self._keys]}]


class _FakeClient:
    def __init__(self, keys):
        self._pag = _FakePaginator(keys)

    def get_paginator(self, _name):
        return self._pag


def _s3(keys):
    s = S3.__new__(S3)
    s.client = _FakeClient(keys)
    return s


def test_default_prefix_is_releases():
    s = _s3(["releases/1.2.3/Locksmith-1.2.3.dmg"])
    assert s.list_release_versions(bucket="b") == ["1.2.3"]
    assert s.client._pag.seen_prefix == "releases/"


def test_branded_prefix_enumerates_under_it():
    s = _s3(["usurance/releases/0.3.0/Usurance-0.3.0.dmg"])
    got = s.list_release_versions(bucket="b", prefix="usurance/releases")
    assert got == ["0.3.0"]
    assert s.client._pag.seen_prefix == "usurance/releases/"
```

- [ ] **Step 2: Run to verify it fails**

Run (from `tools/publisher/`): `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_s3_prefix.py -q --import-mode=importlib`
Expected: FAIL — `list_release_versions()` has no `prefix` param / version parsing keys on literal `releases`.

- [ ] **Step 3: Implement**

Replace `list_release_versions` in `s3_client.py`:

```python
    def list_release_versions(self, *, bucket: str, prefix: str = "releases") -> list[str]:
        """Enumerate ``X.Y.Z`` directories under ``<prefix>/`` in S3."""
        paginator = self.client.get_paginator("list_objects_v2")
        versions: set[str] = set()
        depth = len(prefix.split("/"))  # index of the X.Y.Z segment after prefix
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
            for obj in page.get("Contents", []):
                parts = obj["Key"].split("/")
                if len(parts) > depth and "/".join(parts[:depth]) == prefix:
                    versions.add(parts[depth])
        return sorted(versions)
```

- [ ] **Step 4: Run to verify pass**

Run (from `tools/publisher/`): `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_s3_prefix.py -q --import-mode=importlib`
Expected: PASS (2). Also run the existing suite to confirm no regression: `… -m pytest -q --import-mode=importlib`.

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/s3_client.py tools/publisher/tests/test_s3_prefix.py
git commit -m "feat(publisher): list_release_versions accepts a brand prefix"
```

---

### Task 5: `appcast.py` rebuild path — brand prefix, info URL, XML title

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/appcast.py` (`GeneratorConfig` ~line 23-40; enumerate call line 168; URL builders 182/222/226; info URL 229; XML title 258)
- Modify: `tools/publisher/src/locksmith_publisher/cli.py` (`appcast_cmd`, `GeneratorConfig(...)` construction ~line 234)
- Test: `tools/publisher/tests/test_appcast_build.py`

**Interfaces:**
- Consumes: Task 3 (`brand.release_prefix()`, `brand.website()`, `brand.artifact_prefix()`); Task 4 (`list_release_versions(..., prefix=...)`).
- Produces: `GeneratorConfig` fields `release_prefix: str = "releases"`, `release_notes_base: str = "https://locksmith.app"`, `brand_title: str | None = None`.

- [ ] **Step 1: Add failing assertions**

Add to `tools/publisher/tests/test_appcast_build.py` (adapt construction to the file's existing `GeneratorConfig(...)`/`build_appcast(...)` test fixtures — pass the new fields):

```python
def test_appcast_urls_use_brand_prefix(...):
    # Build with a GeneratorConfig whose release_prefix="usurance/releases"
    # and release_notes_base="https://usurance.com"; a single anchored version.
    # Assert the emitted JSON contains:
    #   artifact_url  ending  "/usurance/releases/<v>/<file>"
    #   anchor_url    ending  "/usurance/releases/<v>/release-anchor-<v>.cesr"
    #   release_notes_url == "https://usurance.com/releases/<v>"
    ...
```

(Use the file's existing S3 stub + anchor fixture; the assertion targets the three URL fields above. If the file lacks a stub, mirror `test_s3_prefix.py`'s `_FakeClient` + a stubbed `get_object` returning the fixture anchor bytes.)

- [ ] **Step 2: Run to verify it fails**

Run (from `tools/publisher/`): `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_appcast_build.py -q --import-mode=importlib -k brand_prefix`
Expected: FAIL — URLs contain `releases/` not `usurance/releases/`; `release_notes_url` is `locksmith.app`.

- [ ] **Step 3: Implement — extend `GeneratorConfig` + thread through**

In `appcast.py`, add to the `GeneratorConfig` dataclass (keep defaults = locksmith values so existing callers/tests are byte-identical):

```python
    release_prefix: str = "releases"
    release_notes_base: str = "https://locksmith.app"
    brand_title: str | None = None
```

Then in the same file:
- Line 168 enumerate: `s3.list_release_versions(bucket=config.bucket, prefix=config.release_prefix)`
- Line 182 anchor read key: `Key=f"{config.release_prefix}/{v}/release-anchor-{v}.cesr"`
- Line 222 artifact_url: `f"{cdn_base}/{config.release_prefix}/{v}/{artifact['filename']}"`
- Line 226 anchor_url: `f"{cdn_base}/{config.release_prefix}/{v}/release-anchor-{v}.cesr"`
- Line 229 release_notes_url: `f"{config.release_notes_base}/releases/{v}"`  (literal `/releases/` on the website — locksmith `https://locksmith.app/releases/<v>` unchanged)
- Line ~258 XML title: `title=config.brand_title or config.publisher_aid,` (brand name now available; falls back to the old AID title if unset — resolves the `# brand name not available here` note)

- [ ] **Step 4: Wire `appcast_cmd` in `cli.py`**

In `appcast_cmd`, where `GeneratorConfig(...)` is built (~line 234), add the brand fields resolved via the Task-3 helper:

```python
    from . import brand
    config=GeneratorConfig(
        bucket=bucket,
        releases_cdn_base=releases_cdn_base,
        publisher_aid=publisher_aid,
        publisher_kel_url=publisher_kel_url,
        release_prefix=brand.release_prefix(),
        release_notes_base=brand.website(),
        brand_title=brand.artifact_prefix(),
        # ...preserve any other existing kwargs (schema_version/channel/etc.)
    )
```

- [ ] **Step 5: Run to verify pass**

Run (from `tools/publisher/`): `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_appcast_build.py tests/test_appcast_xml.py -q --import-mode=importlib`
Expected: PASS. New brand-prefix test green; existing locksmith-default tests still green (defaults preserve behavior).

- [ ] **Step 6: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/appcast.py tools/publisher/src/locksmith_publisher/cli.py tools/publisher/tests/test_appcast_build.py
git commit -m "feat(publisher): appcast rebuild uses brand prefix + website + title"
```

---

### Task 6: `cli.py` publish path — brand prefix + artifact prefix

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/cli.py` (`_artifact_url` line 65-67; `publish_cmd` `artifact_prefix`/`_key` lines ~281 & ~296)
- Test: `tools/publisher/tests/test_artifact_url.py`

**Interfaces:**
- Consumes: Task 3 (`brand.artifact_prefix()`, `brand.release_prefix()`).
- Produces: `_artifact_url(cdn, version, prefix, ext, release_prefix="releases")`; `publish_cmd` builds keys under the brand `release_prefix`.

- [ ] **Step 1: Add failing assertion**

Add to `tools/publisher/tests/test_artifact_url.py`:

```python
from locksmith_publisher.cli import _artifact_url


def test_artifact_url_default_prefix():
    assert _artifact_url("https://releases.keri.host", "1.2.3", "Locksmith", "dmg") \
        == "https://releases.keri.host/releases/1.2.3/Locksmith-1.2.3.dmg"


def test_artifact_url_brand_prefix():
    assert _artifact_url("https://releases.keri.host", "0.3.0", "Usurance", "dmg",
                         release_prefix="usurance/releases") \
        == "https://releases.keri.host/usurance/releases/0.3.0/Usurance-0.3.0.dmg"
```

- [ ] **Step 2: Run to verify it fails**

Run (from `tools/publisher/`): `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_artifact_url.py -q --import-mode=importlib -k brand_prefix`
Expected: FAIL — `_artifact_url()` has no `release_prefix` param / hardcodes `releases/`.

- [ ] **Step 3: Implement**

`_artifact_url` (line 65-67):

```python
def _artifact_url(cdn: str, version: str, prefix: str, ext: str,
                  release_prefix: str = "releases") -> str:
    """Return the CDN URL for a release artifact under the brand's prefix."""
    return f"{cdn.rstrip('/')}/{release_prefix}/{version}/{prefix}-{version}.{ext}"
```

In `publish_cmd`, resolve brand values and thread them:

```python
    from . import brand
    artifact_prefix = brand.artifact_prefix()
    release_prefix = brand.release_prefix()
```
(replaces `artifact_prefix = cfg.get("artifact_prefix", _DEFAULT_ARTIFACT_PREFIX)`)

`_key` (inside `publish_cmd`):

```python
    def _key(ext):
        return f"{release_prefix}/{version}/{artifact_prefix}-{version}.{ext}"
```

And pass `release_prefix` to the two `_artifact_url(...)` calls (the `_json` + `_xml` closures):

```python
               "artifact_url": _artifact_url(cdn, version, artifact_prefix, ext, release_prefix),
```

- [ ] **Step 4: Run to verify pass**

Run (from `tools/publisher/`): `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_artifact_url.py tests/test_cli.py -q --import-mode=importlib`
Expected: PASS. Then the full publisher suite: `… -m pytest -q --import-mode=importlib`.

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/cli.py tools/publisher/tests/test_artifact_url.py
git commit -m "feat(publisher): publish path uses brand prefix + artifact prefix"
```

---

## Self-Review

**Spec coverage:**
- brandlib `release_prefix` + `website` → Task 1. ✅
- CI `s3prefix` from brandlib (single source) → Task 2. ✅
- Publisher resolves from active brand, fail-loud → Task 3. ✅
- 6 hardcoded `releases/`: `s3_client.py:113` → Task 4; `appcast.py:182/222/226` → Task 5; `cli.py:67/296` → Task 6. ✅
- `appcast.py:229` info URL → `{website}/releases/{v}` → Task 5. ✅ (locksmith byte-identical, verified `website == https://locksmith.app`)
- `deploy_config` stays shared infra; publisher stops reading `artifact_prefix` from it → Task 6 (replaces the `cfg.get` line). ✅
- Bonus resolved: `appcast.py:258` XML title `# brand name not available` → `brand_title` (Task 5). ✅

**Placeholder scan:** Task 5 Step 1 describes the test in prose because the assertions must slot into the file's existing `GeneratorConfig`/`build_appcast` fixtures (which the implementer reads); the three concrete URL assertions + fallback-to-`_FakeClient` instruction are given. All other steps carry exact code. No `TBD`/`handle edge cases`.

**Type consistency:** `release_prefix` is a `str` everywhere; brandlib emits it, `brand.release_prefix()` returns it, `GeneratorConfig.release_prefix`/`_artifact_url(..., release_prefix=...)`/`list_release_versions(..., prefix=...)` consume it (note: the s3_client param is named `prefix`, deliberately, since it's generic). `brand.website()` → `GeneratorConfig.release_notes_base`. `brand.artifact_prefix()` → `GeneratorConfig.brand_title` + `publish_cmd.artifact_prefix`. Consistent.

**Note for the executor:** the publisher's full behavior only proves against the real `locksmith` tree (worktree import caveat) and a live S3; these unit tests pin the string logic with the subprocess/S3 mocked. Final cross-tree validation is the throwaway matrix dry-run + a `--dry-run`/staging publish, out of scope here.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-brand-aware-publisher.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks (as we did for Phase-3 CI wiring).
2. **Inline Execution** — execute here with checkpoints.

Which approach?
