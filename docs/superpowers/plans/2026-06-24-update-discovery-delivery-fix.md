# Update Discovery / Delivery Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make in-app auto-update *discovery/delivery* actually work — publish an XML appcast the native frameworks can parse, point Sparkle/WinSparkle at it (brand-driven), fix the macOS wiring bug, and consolidate the update trigger onto the native path — while the proven KERI JSON verifier is left untouched.

**Architecture:** Dual feed. The JSON appcast stays exactly as-is and serves only the KERI gate (`verify_artifact`, fetched in the frameworks' install callback). A new RSS/XML appcast (emitted by the publisher from the same release data) is what Sparkle/WinSparkle fetch for discovery→download→install. The `UpdateController` keeps prefs + scheduler + consent but its JSON discovery (BridgeAdapter, decision tree, `action_decided`) is removed; `check_now`/the scheduler tick now invoke the native check.

**Tech Stack:** Python 3.14, PySide6 (Qt), Sparkle 2 (macOS, via PyObjC), WinSparkle (Windows, via ctypes), Click (publisher CLI), boto3, pytest.

## Global Constraints

- **Run tests with `--import-mode=importlib`** from the repo venv: `.venv/bin/python -m pytest <path> -q --import-mode=importlib`. Publisher tests run from `tools/publisher/` (`cd tools/publisher && ../../.venv/bin/python -m pytest tests/ -q --import-mode=importlib`).
- **Do NOT touch the JSON verifier**: `src/locksmith/update/verify.py`, `src/locksmith/update/appcast.py` (`parse_appcast`/`select_latest_for_platform`/`Release`), or the JSON appcast schema. The JSON `build_appcast` stays; we *add* an XML builder beside it.
- **Native signature stays OFF**: no `sparkle:edSignature` in the XML; `SUPublicEDKey` absent; WinSparkle `win_sparkle_set_dsa_pub_pem(None)`. Trust = Developer-ID/Authenticode code-signature + the KERI gate at install. (If a real build proves a framework refuses a signature-less appcast, that contingency — adding a native transport signature — is a separate effort, out of this plan.)
- **Brand-driven feeds**: the XML appcast URLs live in `brands/<brand>/brand.toml` `[urls]` (per-brand), flow through `brandlib`/`core.branding` like the existing JSON URLs. macOS reads its feed from the Info.plist `SUFeedURL` (build-time); WinSparkle reads it from the runtime `brand()` (no hard-coded domain).
- **Publisher AID + KEL are unchanged** by this work (no new anchor/ceremony). Only the appcast *format/contents* change.
- DRY, YAGNI, TDD, frequent commits. Commit footer (own line after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Do not push/merge during task execution.

**Scope:** publisher XML emission + real artifact sizes (Tasks 1–3); brand-driven XML feed URLs + `SUFeedURL` → XML (Task 4); native init reads the brand XML URL (Task 5); macOS tuple fix (Task 6); retire controller discovery + route to native (Tasks 7–8); real packaged-build end-to-end validation (Task 9). **Out:** custom in-app banner; verifier/JSON-schema changes; re-enabling the frameworks' own auto-cadence; native appcast signatures.

## File structure

- `tools/publisher/src/locksmith_publisher/appcast.py` — **add** `build_appcast_xml(...)` beside `build_appcast`; **edit** `generate_and_upload_appcasts` to also emit `.xml`.
- `tools/publisher/src/locksmith_publisher/cli.py` — **edit** `publish_cmd`: compute real sizes via `s3.head_object_size`, build+upload XML for both platforms, populate JSON `artifact_size`.
- `brands/{locksmith,example}/brand.toml` — **add** `appcast_macos_xml` / `appcast_windows_xml` to `[urls]`.
- `packaging/brandlib.py` — **edit** `macos_info_plist` (`SUFeedURL` → XML); **edit** `runtime_brand_json` (carry the XML URLs).
- `src/locksmith/core/branding.py` — **edit** `Brand` dataclass + `_DEFAULT` + `_from_dict` (carry `appcast_macos_xml`/`appcast_windows_xml`).
- `src/locksmith/update/winsparkle_init.py`, `sparkle_init.py` — **edit** to read the XML feed URL from `brand()`.
- `src/locksmith/core/apping.py` — **edit** `_init_native_updater` (tuple fix); **edit** `_init_update_controller` (drop BridgeAdapter; inject `on_check`).
- `src/locksmith/update/controller.py` — **refactor** (gut discovery; keep prefs/scheduler; `on_check`).
- `src/locksmith/update/bridge_adapter.py`, `src/locksmith/update/decision.py` — **delete**.
- `src/locksmith/update/__init__.py` — **edit** exports.
- `src/locksmith/ui/window.py`, `src/locksmith/ui/dialogs/app_settings.py` — **edit** check-now wiring; remove `action_decided`/critical-banner handlers.
- `src/locksmith/ui/banners/critical_update.py` — **delete** (orphaned once the decision tree is gone).
- Tests: see each task.

---

### Task 1: XML appcast builder (`build_appcast_xml`)

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/appcast.py` (add a function)
- Test: `tools/publisher/tests/test_appcast_xml.py` (create)

**Interfaces:**
- Produces: `build_appcast_xml(*, title: str, releases: list[dict], channel: str = "stable") -> str` — an RSS 2.0 appcast string with the Sparkle namespace. Each release dict needs `version`, `artifact_url`, `artifact_size` (int bytes), `released_at` (str, optional). Each `<item>` has `<title>`, optional `<pubDate>`, and `<enclosure url=… sparkle:version=… sparkle:shortVersionString=… length=… type="application/octet-stream"/>`. **No** `sparkle:edSignature`. Newest release first.

- [ ] **Step 1: Write the failing test**

Create `tools/publisher/tests/test_appcast_xml.py`:

```python
import xml.etree.ElementTree as ET

from locksmith_publisher.appcast import build_appcast_xml

_SPARKLE = "http://www.andymatuschak.org/xml-namespaces/sparkle"


def test_xml_has_enclosure_with_version_and_length():
    xml = build_appcast_xml(
        title="Locksmith",
        releases=[{
            "version": "0.2.0",
            "artifact_url": "https://releases.keri.host/releases/0.2.0/Locksmith-0.2.0.dmg",
            "artifact_size": 62567411,
            "released_at": "",
        }],
    )
    root = ET.fromstring(xml)
    enc = root.find(".//item/enclosure")
    assert enc is not None
    assert enc.get("url") == "https://releases.keri.host/releases/0.2.0/Locksmith-0.2.0.dmg"
    assert enc.get("length") == "62567411"
    assert enc.get(f"{{{_SPARKLE}}}version") == "0.2.0"
    assert enc.get(f"{{{_SPARKLE}}}shortVersionString") == "0.2.0"
    assert enc.get("type") == "application/octet-stream"
    # native signature verification stays OFF — no edSignature
    assert enc.get(f"{{{_SPARKLE}}}edSignature") is None


def test_xml_orders_newest_first():
    xml = build_appcast_xml(title="Locksmith", releases=[
        {"version": "0.1.7", "artifact_url": "u/0.1.7.dmg", "artifact_size": 1},
        {"version": "0.2.0", "artifact_url": "u/0.2.0.dmg", "artifact_size": 2},
    ])
    root = ET.fromstring(xml)
    versions = [e.get(f"{{{_SPARKLE}}}version")
                for e in root.findall(".//item/enclosure")]
    assert versions == ["0.2.0", "0.1.7"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_appcast_xml.py -q --import-mode=importlib`
Expected: FAIL — `ImportError: cannot import name 'build_appcast_xml'`.

- [ ] **Step 3: Implement `build_appcast_xml`**

Add to `tools/publisher/src/locksmith_publisher/appcast.py` (after `build_appcast`; `_semver_key` already exists in this module):

```python
def build_appcast_xml(
    *,
    title: str,
    releases: list[dict[str, Any]],
    channel: str = "stable",
) -> str:
    """Build an RSS 2.0 appcast Sparkle/WinSparkle can parse.

    Native signature verification stays OFF (no ``sparkle:edSignature``) —
    trust is the OS code-signature on the wire plus the KERI gate at install.
    Items are emitted newest-first by semver.
    """
    if not releases:
        raise ValueError("build_appcast_xml requires at least one release")
    ordered = sorted(releases, key=lambda r: _semver_key(r["version"]), reverse=True)
    items: list[str] = []
    for r in ordered:
        v = r["version"]
        pubdate = f"    <pubDate>{r['released_at']}</pubDate>\n" if r.get("released_at") else ""
        items.append(
            f"  <item>\n"
            f"    <title>{title} {v}</title>\n"
            f"{pubdate}"
            f'    <enclosure url="{r["artifact_url"]}" '
            f'sparkle:version="{v}" sparkle:shortVersionString="{v}" '
            f'length="{int(r["artifact_size"])}" type="application/octet-stream"/>\n'
            f"  </item>"
        )
    items_xml = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0" '
        'xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">\n'
        "  <channel>\n"
        f"    <title>{title} ({channel})</title>\n"
        f"{items_xml}\n"
        "  </channel>\n"
        "</rss>\n"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_appcast_xml.py -q --import-mode=importlib`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/appcast.py tools/publisher/tests/test_appcast_xml.py
git commit -m "feat(publisher): RSS/XML appcast builder for Sparkle/WinSparkle (no native sig)"
```

---

### Task 2: `publish_cmd` emits XML + real artifact sizes

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/cli.py` (`publish_cmd`)
- Test: `tools/publisher/tests/test_cli.py` (update `test_publish_uploads_kel_anchor_and_two_appcasts`)

**Interfaces:**
- Consumes: `build_appcast` (JSON, existing), `build_appcast_xml` (Task 1), `S3.head_object_size` (existing — `s3_client.py`), `S3.upload_release`/`S3.put_object` (existing), `_artifact_url`/`artifact_prefix` (existing in `publish_cmd`).
- Produces: after publish, S3 has `appcast/v1/{macos,windows}.json` (with real `artifact_size`) AND `appcast/v1/{macos,windows}.xml`.

- [ ] **Step 1: Update the failing test**

In `tools/publisher/tests/test_cli.py`, extend `test_publish_uploads_kel_anchor_and_two_appcasts` so it (a) stubs `S3.head_object_size` to return a fixed size, and (b) asserts both XML keys are put. Add these assertions to that test (the test already invokes `publish_cmd` and captures `put_object`/`upload_release` calls — add to its captured-keys assertions):

```python
    # XML appcasts are uploaded for both platforms (Sparkle/WinSparkle feed).
    assert "appcast/v1/macos.xml" in put_keys
    assert "appcast/v1/windows.xml" in put_keys
    # the macOS XML enclosure carries the real size from head_object_size
    macos_xml = put_bodies["appcast/v1/macos.xml"].decode()
    assert 'length="424242"' in macos_xml
    assert 'sparkle:version="1.2.3"' in macos_xml
```

If the test's fake S3 does not yet record `head_object_size`, add to the fake: `def head_object_size(self, *, bucket, key): return 424242`. (Match the test's existing fake-S3 style; `put_keys`/`put_bodies` are the test's existing capture dicts — if named differently, use the existing names.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_cli.py -q -k publish --import-mode=importlib`
Expected: FAIL — the XML keys are not uploaded yet.

- [ ] **Step 3: Edit `publish_cmd`**

In `tools/publisher/src/locksmith_publisher/cli.py`, replace the body of `publish_cmd` from `out = Path(out_dir)` through the final `click.echo(...)` with:

```python
    out = Path(out_dir)
    kel = (out / f"{aid}-kel.cesr").read_bytes()
    anchor_bytes = (out / f"{anchor_said}.cesr").read_bytes()
    anchor_url = f"{cdn}/publisher/v1/anchors/{anchor_said}.cesr"

    s3 = S3.default()

    def _key(ext):
        return f"releases/{version}/{artifact_prefix}-{version}.{ext}"

    def _size(ext):
        return s3.head_object_size(bucket=bucket, key=_key(ext))

    def _json(platform, sha, ext):
        rel = {"version": version, "platform": platform, "anchor_said": anchor_said,
               "anchor_url": anchor_url, "artifact_sha256": sha,
               "artifact_url": _artifact_url(cdn, version, artifact_prefix, ext),
               "artifact_size": _size(ext)}
        return build_appcast(publisher_aid=aid, publisher_kel_url=kel_url,
                             releases=[rel], current_version=version).encode()

    def _xml(ext):
        rel = {"version": version,
               "artifact_url": _artifact_url(cdn, version, artifact_prefix, ext),
               "artifact_size": _size(ext), "released_at": ""}
        return build_appcast_xml(title=artifact_prefix, releases=[rel]).encode()

    s3.upload_release(bucket=bucket, kel=kel, anchors={anchor_said: anchor_bytes},
                      appcast=_json("macos", macos_sha256, "dmg"),
                      appcast_key="appcast/v1/macos.json")
    s3.put_object(bucket=bucket, key="appcast/v1/windows.json",
                  data=_json("windows", windows_sha256, "msi"),
                  content_type="application/json")
    s3.put_object(bucket=bucket, key="appcast/v1/macos.xml",
                  data=_xml("dmg"), content_type="application/xml")
    s3.put_object(bucket=bucket, key="appcast/v1/windows.xml",
                  data=_xml("msi"), content_type="application/xml")
    click.echo(f"published v{version}: publisher/v1/kel.cesr + anchors/{anchor_said}.cesr "
               f"+ appcast/v1/{{macos,windows}}.{{json,xml}}")
```

Add the import at the top of `cli.py` (next to the existing `from .appcast import build_appcast`): `from .appcast import build_appcast, build_appcast_xml`.

- [ ] **Step 4: Run to verify pass + full publisher suite**

Run: `cd tools/publisher && ../../.venv/bin/python -m pytest tests/ -q --import-mode=importlib`
Expected: PASS (all green, incl. the updated publish test).

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/cli.py tools/publisher/tests/test_cli.py
git commit -m "feat(publisher): publish uploads XML appcasts + real artifact sizes (head_object_size)"
```

---

### Task 3: regen generator (`generate_and_upload_appcasts`) emits XML

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/appcast.py` (`generate_and_upload_appcasts`)
- Test: `tests/unit/publisher/test_appcast_generator.py` (update `test_generator_writes_per_platform_appcasts`)

**Interfaces:**
- Consumes: `build_appcast_xml` (Task 1). The generator already has each release's real `artifact_size` (`seal["artifacts"][…]["size"]`).
- Produces: the regen path also writes `appcast/v1/{platform}.xml` + the archive `.xml`, keeping JSON and XML in lockstep.

- [ ] **Step 1: Update the failing test**

In `tests/unit/publisher/test_appcast_generator.py::test_generator_writes_per_platform_appcasts`, after the existing JSON-key assertions add:

```python
    assert "appcast/v1/macos.xml" in put_keys
    assert "appcast/v1/windows.xml" in put_keys
```

(Use the test's existing mechanism for capturing `put_object` keys — the fake S3's recorded keys list.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/publisher/test_appcast_generator.py -q --import-mode=importlib`
Expected: FAIL — XML keys not written.

- [ ] **Step 3: Edit `generate_and_upload_appcasts`**

In the `for platform, ext in [("macos", "dmg"), ("windows", "msi")]:` loop of `generate_and_upload_appcasts`, after the existing `s3.put_object(... archive_key ...)` block (the JSON puts), add the XML puts using the `releases` list already built in that loop:

```python
        xml_body = build_appcast_xml(
            title=config.publisher_aid,  # title is cosmetic in the feed; brand name not available here
            releases=[{"version": r["version"], "artifact_url": r["artifact_url"],
                       "artifact_size": r["artifact_size"],
                       "released_at": r["released_at"]} for r in releases],
        ).encode()
        s3.put_object(Bucket=config.bucket, Key=f"appcast/v1/{platform}.xml",
                      Body=xml_body, ContentType="application/xml")
        s3.put_object(Bucket=config.bucket, Key=f"appcast/archive/{timestamp}/{platform}.xml",
                      Body=xml_body, ContentType="application/xml")
```

(Note: the generator's `s3` uses boto3-style kwargs `Bucket=/Key=/Body=/ContentType=` — match the existing `put_object` calls in this function exactly, which differ from the `S3` wrapper's `bucket=/key=/data=` used in `cli.py`.) Add `build_appcast_xml` to this module's usage — it is defined in the same file, no import needed.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/unit/publisher/test_appcast_generator.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/publisher/src/locksmith_publisher/appcast.py tests/unit/publisher/test_appcast_generator.py
git commit -m "feat(publisher): regen generator emits XML appcasts alongside JSON"
```

---

### Task 4: Brand-driven XML feed URLs (manifest + brandlib + Brand)

**Files:**
- Modify: `brands/locksmith/brand.toml`, `brands/example/brand.toml` (`[urls]`)
- Modify: `packaging/brandlib.py` (`macos_info_plist`, `runtime_brand_json`)
- Modify: `src/locksmith/core/branding.py` (`Brand`, `_DEFAULT`, `_from_dict`)
- Test: `tests/unit/branding/test_brandlib.py`, `tests/unit/branding/test_runtime_brand_json.py`, `tests/unit/branding/test_spec_brand_values.py`, `tests/unit/branding/test_locksmith_brand_regression.py`, `tests/unit/update/test_macos_spec_has_sparkle.py`, `tests/unit/branding/test_branding_loader.py`

**Interfaces:**
- Produces: `brand.toml` `[urls]` gains `appcast_macos_xml`/`appcast_windows_xml`; `brandlib.macos_info_plist`'s `SUFeedURL` = `manifest["urls"]["appcast_macos_xml"]`; `runtime_brand_json` carries both XML URLs; `core.branding.Brand` gains `appcast_macos_xml: str` + `appcast_windows_xml: str`, exposed via `brand()`.

- [ ] **Step 1: Add the XML URLs to both brand manifests**

In `brands/locksmith/brand.toml` `[urls]`, add:

```toml
appcast_macos_xml   = "https://releases.keri.host/appcast/v1/macos.xml"
appcast_windows_xml = "https://releases.keri.host/appcast/v1/windows.xml"
```

In `brands/example/brand.toml` `[urls]`, add:

```toml
appcast_macos_xml   = "https://releases.example.com/appcast/v1/macos.xml"
appcast_windows_xml = "https://releases.example.com/appcast/v1/windows.xml"
```

- [ ] **Step 2: Write the failing tests**

In `tests/unit/branding/test_brandlib.py`, add:

```python
def test_macos_info_plist_sufeed_is_xml():
    m = brandlib.load_brand_manifest("locksmith")
    plist = brandlib.macos_info_plist(m, "0.2.1")
    assert plist["SUFeedURL"] == "https://releases.keri.host/appcast/v1/macos.xml"


def test_runtime_brand_json_carries_xml_feeds():
    doc = brandlib.runtime_brand_json(brandlib.load_brand_manifest("locksmith"))
    assert doc["appcast_macos_xml"] == "https://releases.keri.host/appcast/v1/macos.xml"
    assert doc["appcast_windows_xml"] == "https://releases.keri.host/appcast/v1/windows.xml"
```

In `tests/unit/branding/test_branding_loader.py`, add:

```python
def test_default_brand_carries_xml_feeds():
    b = branding.load_brand()
    assert b.appcast_macos_xml == "https://releases.keri.host/appcast/v1/macos.xml"
    assert b.appcast_windows_xml == "https://releases.keri.host/appcast/v1/windows.xml"
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/branding/test_brandlib.py tests/unit/branding/test_branding_loader.py -q --import-mode=importlib`
Expected: FAIL — `KeyError: 'appcast_macos'`-style or `AttributeError: 'Brand' object has no attribute 'appcast_macos_xml'`.

- [ ] **Step 4: Edit `brandlib.py`**

In `macos_info_plist`, change the `SUFeedURL` line to:

```python
        "SUFeedURL": manifest["urls"]["appcast_macos_xml"],
```

In `runtime_brand_json`, add two keys to the returned dict (after `"support": …`):

```python
        "appcast_macos_xml": manifest["urls"]["appcast_macos_xml"],
        "appcast_windows_xml": manifest["urls"]["appcast_windows_xml"],
```

- [ ] **Step 5: Edit `core/branding.py`**

Add the two fields to the `Brand` dataclass (after `support: str`):

```python
    appcast_macos_xml: str = ""
    appcast_windows_xml: str = ""
```

Add them to `_DEFAULT` (after `support="https://locksmith.app/support",`):

```python
    appcast_macos_xml="https://releases.keri.host/appcast/v1/macos.xml",
    appcast_windows_xml="https://releases.keri.host/appcast/v1/windows.xml",
```

Add them to `_from_dict` (after the `support=` line):

```python
        appcast_macos_xml=doc.get("appcast_macos_xml", _DEFAULT.appcast_macos_xml),
        appcast_windows_xml=doc.get("appcast_windows_xml", _DEFAULT.appcast_windows_xml),
```

- [ ] **Step 6: Update the dependent regression/spec tests**

- `tests/unit/branding/test_spec_brand_values.py::test_macos_info_plist_from_locksmith` — change its `SUFeedURL` assertion to `…/appcast/v1/macos.xml`.
- `tests/unit/update/test_macos_spec_has_sparkle.py::test_macos_spec_sets_sufeed_url` — change its `_locksmith_plist()["SUFeedURL"]` assertion to `…/appcast/v1/macos.xml`.
- `tests/unit/branding/test_locksmith_brand_regression.py` — if it asserts the runtime brand.json shape, add the two XML keys; its identity/wxs assertions are unaffected.
- `tests/unit/branding/test_runtime_brand_json.py` — the locksmith round-trip test still passes (extra keys are additive); no change required unless it asserts an exact dict equality (if so, add the two keys).

Leave `tests/unit/update/test_windows_spec_has_winsparkle.py::test_windows_spec_documents_appcast_url` for Task 5 (it asserts the WinSparkle URL in the spec/init).

- [ ] **Step 7: Run the branding + spec suites**

Run: `.venv/bin/python -m pytest tests/unit/branding tests/unit/update/test_macos_spec_has_sparkle.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add brands/locksmith/brand.toml brands/example/brand.toml packaging/brandlib.py src/locksmith/core/branding.py tests/unit/branding tests/unit/update/test_macos_spec_has_sparkle.py
git commit -m "feat(brand): XML appcast feed URLs in manifest/brandlib/Brand; SUFeedURL → XML"
```

---

### Task 5: Native init reads the XML feed URL from the brand

**Files:**
- Modify: `src/locksmith/update/winsparkle_init.py`
- Modify: `src/locksmith/update/sparkle_init.py`
- Test: `tests/unit/update/test_winsparkle_bridge.py`, `tests/unit/update/test_sparkle_bridge.py`, `tests/unit/update/test_windows_spec_has_winsparkle.py`

**Interfaces:**
- Consumes: `locksmith.core.branding.brand()` → `.appcast_windows_xml` / `.appcast_macos_xml` (Task 4).
- Produces: WinSparkle's `win_sparkle_set_appcast_url` receives the brand's `appcast_windows_xml` (bytes); the hard-coded `releases.keri.host` URLs are gone.

- [ ] **Step 1: Write/adjust the failing test**

In `tests/unit/update/test_winsparkle_bridge.py`, add a test that the URL is brand-derived (the init returns `(None, None, None)` off-Windows, so assert the helper the init uses):

```python
def test_winsparkle_appcast_url_is_brand_xml(monkeypatch):
    import locksmith.update.winsparkle_init as wi
    from locksmith.core import branding
    branding._reset_cache_for_tests()
    assert wi._appcast_url() == b"https://releases.keri.host/appcast/v1/windows.xml"
```

In `tests/unit/update/test_windows_spec_has_winsparkle.py::test_windows_spec_documents_appcast_url`, change the expected substring to `releases.keri.host/appcast/v1/windows.xml` (and if the assertion reads the spec comment, update the comment in Step 3 accordingly).

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/update/test_winsparkle_bridge.py -q -k appcast --import-mode=importlib`
Expected: FAIL — `AttributeError: module … has no attribute '_appcast_url'`.

- [ ] **Step 3: Edit `winsparkle_init.py`**

Replace the module-level `APPCAST_URL = b"https://releases.keri.host/appcast/v1/windows.json"` with a brand-derived helper:

```python
def _appcast_url() -> bytes:
    from locksmith.core.branding import brand
    return brand().appcast_windows_xml.encode()
```

In `init_winsparkle`, replace `dll.win_sparkle_set_appcast_url(APPCAST_URL)` with:

```python
    appcast_url = _appcast_url()
    dll.win_sparkle_set_appcast_url(appcast_url)
```

and the log line `…APPCAST_URL.decode()` with `appcast_url.decode()`. Update the module docstring's appcast comment to reference `windows.xml`.

- [ ] **Step 4: Edit `sparkle_init.py`**

macOS Sparkle reads its feed from the Info.plist `SUFeedURL` (set in Task 4), so `APPCAST_URL` here is only logged. Make it brand-derived for correctness:

```python
def _appcast_url() -> str:
    from locksmith.core.branding import brand
    return brand().appcast_macos_xml
```

Replace the `logger.info("[update] sparkle.initialized appcast=%s", APPCAST_URL)` with `logger.info("[update] sparkle.initialized appcast=%s", _appcast_url())` and remove the module-level `APPCAST_URL` constant. (`init_sparkle`'s 2-tuple return is fixed on the consumer side in Task 6.) `test_sparkle_bridge.py::test_sparkle_init_returns_none_off_darwin` is unaffected.

- [ ] **Step 5: Run the native-init tests**

Run: `.venv/bin/python -m pytest tests/unit/update/test_winsparkle_bridge.py tests/unit/update/test_sparkle_bridge.py tests/unit/update/test_windows_spec_has_winsparkle.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/update/winsparkle_init.py src/locksmith/update/sparkle_init.py tests/unit/update/test_winsparkle_bridge.py tests/unit/update/test_sparkle_bridge.py tests/unit/update/test_windows_spec_has_winsparkle.py
git commit -m "feat(update): native updaters read the brand XML appcast URL (no hard-coded domain)"
```

---

### Task 6: macOS tuple fix (`_init_native_updater`)

**Files:**
- Modify: `src/locksmith/core/apping.py` (`_init_native_updater`)
- Test: `tests/unit/update/test_apping_native_updater.py` (create)

**Interfaces:**
- Consumes: `init_sparkle(...) -> (controller, py_delegate)` (existing 2-tuple).
- Produces: on macOS, `self._native_updater` is the controller object (has `checkForUpdates_`), and `self._native_updater_delegate` retains the delegate so PyObjC doesn't GC it.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/update/test_apping_native_updater.py`:

```python
"""The macOS Sparkle controller must be stored unwrapped so
check_for_updates_with_ui() can call checkForUpdates_ (regression: a 2-tuple
was stored, so hasattr(updater, 'checkForUpdates_') was always False)."""
import sys
import types

import pytest


def test_darwin_stores_controller_not_tuple(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    class FakeController:
        def checkForUpdates_(self, _):
            self.called = True

    fake_controller = FakeController()
    fake_delegate = object()

    fake_init = types.ModuleType("locksmith.update.sparkle_init")
    fake_init.init_sparkle = lambda **kw: (fake_controller, fake_delegate)
    monkeypatch.setitem(sys.modules, "locksmith.update.sparkle_init", fake_init)

    from locksmith.core import apping
    app = apping.LocksmithApplication.__new__(apping.LocksmithApplication)
    app._native_updater = None
    app._native_updater_dll = None
    app._native_updater_callbacks = None
    app._native_updater_delegate = None
    app._init_native_updater()

    assert app._native_updater is fake_controller
    assert hasattr(app._native_updater, "checkForUpdates_")
    assert app._native_updater_delegate is fake_delegate
```

(If `_make_update_verifier()` is called inside `_init_native_updater` and requires app state, the test's `__new__`-constructed instance plus the monkeypatched `sparkle_init` is sufficient — `init_sparkle` is faked so the real verifier closure is built but never invoked. If the verifier import needs more, monkeypatch `apping._make_update_verifier` to `lambda: (lambda staged, info: True)`.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/update/test_apping_native_updater.py -q --import-mode=importlib`
Expected: FAIL — `assert app._native_updater is fake_controller` fails (a tuple is stored).

- [ ] **Step 3: Edit `_init_native_updater`**

In the `elif _sys.platform == "darwin":` branch of `src/locksmith/core/apping.py:_init_native_updater`, replace:

```python
                from locksmith.update.sparkle_init import init_sparkle
                updater = init_sparkle(
                    verifier=verifier,
                    log_recorder=lambda **kw: logger.info("[update] log %s", kw),
                    on_failure=lambda v: logger.warning("[update] verify_failed %s", v),
                )
                self._native_updater = updater
```

with:

```python
                from locksmith.update.sparkle_init import init_sparkle
                controller, py_delegate = init_sparkle(
                    verifier=verifier,
                    log_recorder=lambda **kw: logger.info("[update] log %s", kw),
                    on_failure=lambda v: logger.warning("[update] verify_failed %s", v),
                )
                self._native_updater = controller
                self._native_updater_delegate = py_delegate
```

In `_init_update_controller`, add `self._native_updater_delegate = None` beside the existing `self._native_updater = None` / `self._native_updater_dll = None` / `self._native_updater_callbacks = None` initializers (so the attribute always exists).

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/unit/update/test_apping_native_updater.py -q --import-mode=importlib`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/core/apping.py tests/unit/update/test_apping_native_updater.py
git commit -m "fix(update): store the macOS Sparkle controller unwrapped so checkForUpdates_ fires"
```

---

### Task 7: Refactor `UpdateController` — gut discovery, keep prefs/scheduler, route to native

**Files:**
- Modify: `src/locksmith/update/controller.py` (refactor)
- Delete: `src/locksmith/update/bridge_adapter.py`, `src/locksmith/update/decision.py`
- Modify: `src/locksmith/update/__init__.py` (exports)
- Delete: `tests/unit/update/test_bridge_adapter.py`, `tests/unit/update/test_decision.py`, `tests/integration/test_phase5_update_flow.py`
- Modify: `tests/unit/update/test_controller.py` (rewrite), `tests/unit/update/test_package_imports.py`

**Interfaces:**
- Produces: `UpdateController(*, prefs=None, scheduler=None, on_check=None, parent=None)`. `check_now()` always invokes `on_check` (manual bypasses the auto pref — fixes SEV 3). The scheduler tick invokes `on_check` only when `prefs.check_automatically`. Keeps `prefs`, `scheduler`, `start()`, `stop()`, `report_verification_failed(version)`, `verification_failed` signal. **Removed:** `set_bridge`, `_default_fetch_release`, the `action_decided`/`check_failed` signals, the `UpdateDecision` import, `current_version`/`platform` ctor args.

- [ ] **Step 1: Rewrite `test_controller.py`**

Replace `tests/unit/update/test_controller.py` with:

```python
"""UpdateController now owns prefs+scheduler and routes checks to a native
callback; it no longer does JSON discovery or emit action_decided."""
from locksmith.update.controller import UpdateController
from locksmith.update.prefs import UpdatePrefs


def test_check_now_invokes_on_check_even_when_auto_disabled():
    calls = []
    prefs = UpdatePrefs()
    prefs.check_automatically = False
    ctrl = UpdateController(prefs=prefs, on_check=lambda: calls.append(1))
    ctrl.check_now()
    assert calls == [1]  # manual bypasses the auto pref (SEV 3 fix)


def test_scheduled_tick_honors_auto_pref():
    calls = []
    prefs = UpdatePrefs()
    prefs.check_automatically = False
    ctrl = UpdateController(prefs=prefs, on_check=lambda: calls.append(1))
    ctrl.scheduler.trigger_now()      # simulate a scheduler tick
    assert calls == []                # suppressed when auto is off
    prefs.check_automatically = True
    ctrl.scheduler.trigger_now()
    assert calls == [1]


def test_report_verification_failed_emits_signal(qtbot=None):
    from PySide6.QtCore import QSignalSpy
    ctrl = UpdateController(on_check=lambda: None)
    spy = QSignalSpy(ctrl.verification_failed)
    ctrl.report_verification_failed("0.2.0")
    assert len(spy) == 1
```

(If the repo's tests construct a `QApplication` via a shared fixture, reuse it; `UpdateController` is a `QObject` and needs a `QApplication` instance to exist — add `from PySide6.QtWidgets import QApplication` and `QApplication.instance() or QApplication([])` at module top, matching the pattern in `tests/unit/branding/test_styles_branding.py`.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/update/test_controller.py -q --import-mode=importlib`
Expected: FAIL — `UpdateController` still requires `current_version`/`platform` and has no `on_check`.

- [ ] **Step 3: Rewrite `controller.py`**

Replace the entire body of `src/locksmith/update/controller.py` with:

```python
"""Top-level update controller (cross-platform).

Owns the update prefs (auto-check toggle, first-launch consent, last-seen
version) and the check cadence (UpdateScheduler). Discovery + download +
install are driven by the native Sparkle/WinSparkle frameworks; this
controller simply triggers the native check on a manual "Check now"
(``check_now``) or on a scheduled tick (when auto-check is enabled), via
the injected ``on_check`` callback.

UI signal:
    - ``verification_failed(str)`` — emitted (via ``report_verification_failed``)
      when the native KERI gate rejects a downloaded artifact (str = version).
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal
from keri import help

from locksmith.update.prefs import UpdatePrefs
from locksmith.update.scheduler import UpdateScheduler

logger = help.ogler.getLogger(__name__)


class UpdateController(QObject):
    """Owns update prefs + cadence; routes checks to the native updater."""

    verification_failed = Signal(str)  # version string

    def __init__(
        self,
        *,
        prefs: UpdatePrefs | None = None,
        scheduler: UpdateScheduler | None = None,
        on_check: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.prefs = prefs or UpdatePrefs()
        self.scheduler = scheduler or UpdateScheduler(self)
        self._on_check = on_check or (lambda: None)
        self.scheduler.check_requested.connect(self._on_scheduled_tick)

    def start(self) -> None:
        if self.prefs.check_automatically:
            logger.info("[update] controller.start check_automatically=True")
            self.scheduler.start()
        else:
            logger.info("[update] controller.start check_automatically=False (idle)")

    def stop(self) -> None:
        self.scheduler.stop()

    def check_now(self) -> None:
        """Manual 'Check now' — always fires (bypasses the auto-check pref)."""
        logger.info("[update] controller.check_now (manual)")
        self._on_check()

    def report_verification_failed(self, version: str) -> None:
        logger.warning("[update] controller.verification_failed version=%s", version)
        self.verification_failed.emit(version)

    def _on_scheduled_tick(self) -> None:
        if not self.prefs.check_automatically:
            logger.info("[update] controller.tick_skipped (auto disabled)")
            return
        logger.info("[update] controller.tick → native check")
        self._on_check()
```

- [ ] **Step 4: Delete the orphaned modules + their tests**

```bash
git rm src/locksmith/update/bridge_adapter.py src/locksmith/update/decision.py \
       tests/unit/update/test_bridge_adapter.py tests/unit/update/test_decision.py \
       tests/integration/test_phase5_update_flow.py
```

- [ ] **Step 5: Update `update/__init__.py` exports**

In `src/locksmith/update/__init__.py`, remove any import/`__all__` entry for `BridgeAdapter`, `decision`/`UpdateDecision`. Keep `UpdateController` and `UpdateScheduler` exports. Update the module docstring lines that described the discovery/decision tree.

- [ ] **Step 6: Update `test_package_imports.py`**

In `tests/unit/update/test_package_imports.py`, remove assertions referencing `UpdateDecision` and `bridge_adapter`; keep `UpdateController`/`UpdateScheduler` assertions. (The Phase-4 `appcast` export assertion stays.)

- [ ] **Step 7: Run the update unit suite (controller + scheduler + imports)**

Run: `.venv/bin/python -m pytest tests/unit/update/test_controller.py tests/unit/update/test_scheduler.py tests/unit/update/test_package_imports.py -q --import-mode=importlib`
Expected: PASS (`test_scheduler.py` is unchanged and still green).

- [ ] **Step 8: Commit**

```bash
git add -A src/locksmith/update tests/unit/update
git commit -m "refactor(update): controller keeps prefs/scheduler, routes to native; drop discovery (bridge_adapter+decision)"
```

---

### Task 8: Rewire `apping` + `window` + `app_settings` onto the native path

**Files:**
- Modify: `src/locksmith/core/apping.py` (`_init_update_controller`)
- Modify: `src/locksmith/ui/window.py` (check-now handler + signal wiring; remove action_decided/critical-banner)
- Modify: `src/locksmith/ui/dialogs/app_settings.py` (unchanged call, verify)
- Delete: `src/locksmith/ui/banners/critical_update.py` (+ its test if present)
- Test: `tests/test_app_settings_dialog.py`, and any `tests/**/critical_update*`/banner test

**Interfaces:**
- Consumes: `UpdateController(on_check=…)` (Task 7), `apping.check_for_updates_with_ui` (existing, fixed in Task 6).
- Produces: both the Help menu and Settings "Check now" trigger the native update dialog; the scheduler tick triggers it when auto-check is on; the consent/what's-new flows (read `ctrl.prefs`) are preserved; `verification_failed` still drives the failed-toast.

- [ ] **Step 1: Edit `_init_update_controller` in `apping.py`**

Replace the body from the `try:`-import block through the `set_bridge` call with the native-routed construction. Specifically, replace:

```python
        try:
            from locksmith.update.bridge_adapter import (
                BridgeAdapter,
                current_platform,
            )
            from locksmith.update.controller import UpdateController
            from locksmith.build_info import LOCKSMITH_VERSION
        except Exception as exc:  # noqa: BLE001 — defensive against import errors in tests
            logger.warning("update_controller.init_skipped reason=%s", exc)
            return

        self.update_bridge = BridgeAdapter()
        self.update_controller = UpdateController(
            current_version=LOCKSMITH_VERSION,
            platform=current_platform(),
        )
        self.update_controller.set_bridge(self.update_bridge)
```

with:

```python
        try:
            from locksmith.update.controller import UpdateController
        except Exception as exc:  # noqa: BLE001 — defensive against import errors in tests
            logger.warning("update_controller.init_skipped reason=%s", exc)
            return

        # Native updater first, so the controller's on_check can drive it.
        self._native_updater = None
        self._native_updater_dll = None
        self._native_updater_callbacks = None
        self._native_updater_delegate = None
        self._init_native_updater()

        self.update_controller = UpdateController(
            on_check=self.check_for_updates_with_ui,
        )
```

Then remove the now-duplicate `self._native_updater = None` / `_dll` / `_callbacks` / `_init_native_updater()` block that previously sat *after* `set_bridge` (those four lines + the call are moved above). Keep the closing `logger.info("update_controller.constructed …")` line but drop its `version=`/`platform=` args:

```python
        logger.info(
            "update_controller.constructed native=%s",
            "yes" if (self._native_updater_dll is not None or self._native_updater is not None) else "no",
        )
```

- [ ] **Step 2: Edit `window.py` — check-now + signal wiring**

In `_wire_update_controller_signals`, keep only the `verification_failed` connection; remove the `action_decided` and `check_failed` connects:

```python
    def _wire_update_controller_signals(self) -> None:
        """Connect the controller's verification_failed signal to the toast.
        No-op if the controller didn't construct (e.g., import failed in tests)."""
        ctrl = getattr(self.app, "update_controller", None)
        if ctrl is None:
            logger.info("update_controller.wire_skipped (no controller)")
            return
        ctrl.verification_failed.connect(self._on_update_verification_failed)
        self._last_verification_result = None
```

Replace `_on_check_for_updates_clicked` with a native-only trigger:

```python
    def _on_check_for_updates_clicked(self) -> None:
        """Help menu 'Check for updates…' and Settings → 'Check now' route here.
        Triggers the native Sparkle/WinSparkle update dialog (discovery →
        download → KERI gate → install)."""
        ctrl = getattr(self.app, "update_controller", None)
        if ctrl is None:
            logger.warning("update_controller.check_now.no_controller")
            return
        logger.info("update_controller.check_now.requested")
        ctrl.check_now()
```

Delete the methods `_on_update_action_decided` and `_on_update_check_failed`. Keep `_on_update_verification_failed`. Delete `_handle_critical_update_install_clicked` and the `critical_update_banner` construction block (the `from locksmith.ui.banners.critical_update import CriticalUpdateBanner` import, the `self.critical_update_banner = …`, the `.install_requested.connect(...)`, and the `outer_layout.addWidget(self.critical_update_banner)`). Keep `_maybe_show_first_launch_consent` and `_maybe_show_whats_new` (they read `ctrl.prefs` / call `ctrl.start()` — unchanged).

- [ ] **Step 3: Verify `app_settings.py`**

`set_check_now_callback(ctrl.check_now)` is correct as-is — `check_now` now routes to the native check. No change needed (confirm by reading lines 99–104). The `prefs=ctrl.prefs if ctrl else None` line is unchanged.

- [ ] **Step 4: Delete the orphaned critical-update banner**

```bash
git rm src/locksmith/ui/banners/critical_update.py
```
If a test references it (grep `CriticalUpdateBanner` under `tests/`), remove that test or the banner-specific assertions.

- [ ] **Step 5: Update `test_app_settings_dialog.py`**

`test_app_settings_dialog_wires_check_now_to_controller` asserts `set_check_now_callback` is called with the controller's `check_now`. That still holds (the fake controller has a `check_now`). If the fake controller in the test was a `SimpleNamespace` lacking `check_now`, add `check_now=lambda: None` to it. Run the file and fix any fake-controller attribute the new wiring expects (it now expects only `prefs` + `check_now`, no `action_decided`).

- [ ] **Step 6: Run the affected UI + update suites**

Run: `.venv/bin/python -m pytest tests/test_app_settings_dialog.py tests/unit/update -q --import-mode=importlib`
Expected: PASS. Then a focused import smoke check:
Run: `.venv/bin/python -c "import locksmith.ui.window, locksmith.core.apping, locksmith.ui.dialogs.app_settings"`
Expected: exit 0, no output.

- [ ] **Step 7: Commit**

```bash
git add -A src/locksmith tests/test_app_settings_dialog.py
git commit -m "refactor(update): Check now/scheduler drive the native updater; remove discovery banner wiring"
```

---

### Task 9: Real packaged-build end-to-end validation (runbook — main session)

> **This task is NOT subagent-buildable.** It is a manual/real-UI validation run done in the main session (per the "no subagents for UI work" rule). It produces no code; it proves the fix. Do it after Tasks 1–8 are merged and a fresh `0.2.1` (or a local `0.1.99-test`) release exists whose version is *below*… actually *above* the installed build — i.e., install an OLDER build and let it discover the newer published one.

**Procedure:**

- [ ] **Step 1: Ensure a published newer release exists.** The live feeds advertise `0.2.0` (current). To test discovery, the *installed* app must be an older version. Either (a) keep `0.2.0` as the published latest and build/install a local `0.1.7`-versioned packaged app, or (b) cut a new `0.2.1` through the normal release+anchor+publish flow (which now also emits XML) and install `0.2.0`.

- [ ] **Step 2: Build + install the older packaged app (macOS).** `bash packaging/build-macos.sh` for the lower version (inject the real publisher anchor + deploy_config as in a release build, so the gate is live), install the resulting `.app` into `/Applications`.

- [ ] **Step 3: Verify the feed is XML + reachable.** `curl -fsS https://releases.keri.host/appcast/v1/macos.xml | head` — confirm it's the RSS feed with a `<enclosure … sparkle:version="0.2.0" length="…">` (non-zero length).

- [ ] **Step 4: Run the installed app → Check now.** Launch the installed older `.app`; Settings → Updates → **Check now** (and Help → Check for updates…). **Expected:** the native Sparkle dialog appears offering the newer version (it did not before — JSON feed + tuple bug). Capture a screenshot.

- [ ] **Step 5: Install + confirm the KERI gate ran.** Proceed through the Sparkle install. **Expected:** the download completes, the KERI verifier gate runs in the install callback (check the app log for the `[update] log …`/verify lines), the gate passes (the published `0.2.0` is anchored + verified), and the app relaunches at the new version. Confirm the About version updated.

- [ ] **Step 6: Windows discovery check (Parallels VM).** Install the older MSI in the Windows VM, run it, Check now → confirm WinSparkle's dialog discovers the newer version (full install-replacement is the natural follow-up; discovery is the gate for this task).

- [ ] **Step 7: Record the result** in `.git/sdd/progress.md` and (if a real cut was used) note the new version in memory `project_publisher_wig_attachment_bug` / `project_white_label_branding_engine`. If either framework refused the signature-less appcast, STOP and escalate — that triggers the native-signature contingency (out of this plan's scope).

---

## Self-Review

**1. Spec coverage:**
- Dual-feed (JSON for gate untouched, XML added) → Tasks 1–3 (publisher) + Task 4 (`SUFeedURL` → XML). ✓
- XML for native; no `edSignature` → Task 1. ✓
- Real artifact sizes (fix `artifact_size: 0`) → Task 2 (`head_object_size`) + Task 3. ✓
- Brand-driven feeds → Task 4 (manifest/brandlib/Brand) + Task 5 (native init reads `brand()`). ✓
- macOS tuple fix (SEV 2) → Task 6. ✓
- SEV 3 (Check now ignores pref) → fixed by Task 7's `check_now` bypassing the pref. ✓
- SEV 4 (`_compare` dev crash) → `decision.py` deleted in Task 7, so the crash site is gone. ✓
- Retire controller discovery, keep prefs/scheduler/consent → Tasks 7 + 8. ✓
- No verifier/JSON changes → enforced in Global Constraints; no task touches `verify.py`/`parse_appcast`. ✓
- Real e2e validation → Task 9. ✓

**2. Placeholder scan:** No "TBD"/"handle errors"/"similar to". Code steps carry full code; test removals name the files/functions; the one judgment point (fake-S3 capture var names in Tasks 2/3) is bounded by "match the existing names." ✓

**3. Type consistency:** `build_appcast_xml(*, title, releases, channel)` — same signature in Tasks 1/2/3. `UpdateController(*, prefs, scheduler, on_check, parent)` — Task 7 definition matches Task 8's `UpdateController(on_check=…)` call and the rewritten `test_controller.py`. `Brand.appcast_macos_xml`/`appcast_windows_xml` — defined in Task 4, consumed in Task 5 (`brand().appcast_windows_xml`). `_native_updater`/`_native_updater_delegate` — set in Task 6, initialized in Tasks 6 + 8. `runtime_brand_json` keys — added in Task 4, asserted in Task 4's tests. ✓
