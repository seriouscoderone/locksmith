# Update Discovery / Delivery Fix — Design

**Date:** 2026-06-24
**Status:** Approved (brainstorm) — ready for implementation plan
**Repo:** locksmith (`~/code/locksmith`); publisher tool at `tools/publisher/`

## Summary

The in-app KERI update **verification gate is correct and live** (`verify_artifact` PASSes against the live CDN for 0.1.7/0.2.0). But the **discovery/delivery** half is broken: an installed build is never actually offered or given an update, on either platform. This effort makes native discovery→download→install work by feeding Sparkle/WinSparkle an **XML appcast** they can parse (they currently receive JSON they cannot), fixing a macOS wiring bug, and consolidating the update trigger onto the native path. The proven JSON verifier is left untouched.

## The four confirmed gaps (code-verified)

1. **SEV 1 — BLOCKER, both platforms.** Sparkle (`SUFeedURL`, set in `brandlib.macos_info_plist` → `brand.toml` `appcast_macos`) and WinSparkle (`win_sparkle_set_appcast_url`, `winsparkle_init.py:55`) are pointed at the custom **JSON** appcast (`…/appcast/v1/{macos,windows}.json`). Both are RSS/**XML** parsers; no XML appcast is generated anywhere. They fetch JSON, fail to parse silently, and never raise the native "update available → download → install" UI.
2. **SEV 2 — BLOCKER, macOS.** `sparkle_init.py:64` returns a 2-tuple `(controller, py_delegate)`; `apping.py:206` stores the whole tuple as `self._native_updater`; `apping.py:224` then checks `hasattr(updater, "checkForUpdates_")` on a *tuple* → always `False` → `checkForUpdates_` is never invoked even in a correctly-built `.app`. The Sparkle controller is constructed and immediately orphaned.
3. **SEV 3 — behavioral, both platforms.** `controller.check_now()` documents "bypasses auto-check pref" but routes `trigger_now → check_requested → _on_check_requested`, which early-returns on `not prefs.check_automatically` (`controller.py:107`). Manual "Check now" silently no-ops when auto-check is off.
4. **SEV 4 — dev-only crash.** `decision._compare` does `int(x)` over `version.split(".")`; `int("0+dev")` raises `ValueError` (the dev-tree `build_info.LOCKSMITH_VERSION = "0.0.0+dev"`). Packaged builds carry clean semver so it doesn't bite there, but it blocks exercising the controller path from source.

**Structural root cause:** two half-built, disconnected paths. The JSON `controller`/`BridgeAdapter` correctly fetches+parses+compares but only shows a banner for *critical* updates and never installs; the native path installs but cannot read the feed.

## Locked decisions (from brainstorm)

1. **Keep Sparkle/WinSparkle** as the download+install engine; feed them an XML appcast. (Self-driven updater and JSON-discovers-native-installs hybrid both rejected — the former reimplements privileged install + signing trust; the latter fights the frameworks' appcast-centric design.)
2. **Native dialog UX.** "Check now" → the OS-standard Sparkle/WinSparkle update dialog drives discovery→download→KERI-gate→install. The controller's discovery role + custom in-app banner are **retired** (removed — one path, no dormant dead code). A custom in-app banner is deferred.
3. **Dual-feed split.** JSON appcast stays exactly as-is, serving only the KERI gate. A new XML appcast serves native discovery/download. Both are emitted from the same release data in one publisher step. (Single XML-with-custom-KERI-elements feed rejected — it forces a rewrite of the proven JSON verifier.)
4. **No verifier / JSON-gate changes.** `update/verify.py`, `update/appcast.py:parse_appcast`, and the JSON appcast schema are untouched (CLAUDE.md: the verifier is correct).
5. **Native signature stays OFF** (no `sparkle:edSignature`, `SUPublicEDKey` absent, WinSparkle DSA off). KERI is sole trust; transport authenticity is the Developer-ID/Authenticode code-signature plus the KERI gate at install time.

## Architecture — the dual-feed model

**XML = discovery/download (native frameworks); JSON = verification (KERI gate).** One source of truth in the publisher, two serializations, generated together so they cannot disagree (same version, artifact URL, bytes → the JSON `sha256` matches what the framework downloaded).

Data flow on "Check now" (packaged build):
1. "Check now" (or the scheduler tick) → `apping.check_for_updates_with_ui()` → native `checkForUpdates_` (macOS) / `win_sparkle_check_update_with_ui` (Windows).
2. The framework GETs the **XML** appcast, parses it, compares `sparkle:version` to the running build, and if newer shows its update dialog + downloads the enclosure artifact.
3. On install, the framework's callback (`shouldProceedWithInstall` / `can_shutdown_and_install`) runs the existing KERI verifier closure, which fetches the **JSON** appcast + KEL + anchor and runs `verify_artifact` against the downloaded bytes. Pass → the framework runs the privileged OS install; fail → install is refused (gate enforces once a real anchor is injected; it's injected as of 0.1.7).

## Change-set

1. **Publisher: emit XML.** Add an RSS/XML appcast builder beside the JSON builder in `tools/publisher/src/locksmith_publisher/appcast.py`; the `publish` command uploads `appcast/v1/{macos,windows}.xml` alongside the JSON. Each `<item>` carries `<enclosure url=… sparkle:version=… sparkle:shortVersionString=… length=… type="application/octet-stream">` (no `sparkle:edSignature`). Populate the **real artifact byte size** in both the XML `length` and the JSON `artifact_size` (currently `0`).
2. **Point the frameworks at XML.** Add per-brand XML feed URLs to `brands/<brand>/brand.toml` (mirroring the existing `appcast_macos`/`appcast_windows` JSON URLs); `brandlib.macos_info_plist`'s `SUFeedURL` uses the **XML** URL; the WinSparkle init's `win_sparkle_set_appcast_url` uses the **XML** URL. The JSON URLs remain (the KERI gate consumes them). This extends the just-shipped branding engine — a clean addition; the keystone brand-regression test is updated for the new fields.
3. **Fix the macOS orphan (SEV 2).** In `apping._init_native_updater`, unpack `controller, _delegate = init_sparkle(...)` and store the controller in `self._native_updater` so `checkForUpdates_` is reachable. (Keep a reference to the delegate so it isn't garbage-collected.)
4. **Consolidate the trigger onto native.** "Check now" (settings widget callback + `window._on_check_for_updates_clicked`) and the auto-check scheduler tick drive `check_for_updates_with_ui()`. Remove the `UpdateController`/`BridgeAdapter`/`scheduler`-discovery wiring and the `action_decided` banner path (SEV 3/4 dissolve with the removed code). Keep our scheduler as the cadence source (it now calls the native check); do not re-enable Sparkle/WinSparkle's own auto-cadence.
5. **No verifier changes.** `verify.py` / `parse_appcast` / JSON appcast schema untouched.

## The primary risk + contingency

**Will the native frameworks install a code-signed update with no appcast signature?** Never validated. Sparkle 2 supports code-signed-only updates (verifies the update's Developer-ID matches the running app); our DMG is Developer-ID signed + notarized, so it should accept it. WinSparkle with DSA off relies on the MSI's Authenticode signature; older lines were stricter. **Design for no-signature first.** If a real build shows either framework refusing a signature-less appcast, the documented contingency is to add that framework's **native signature** (a second, non-KERI transport key) purely as a wire check — KERI remains the trust authority. This contingency is out of the initial build scope unless validation forces it.

## Testing

- **Unit:** XML appcast generation (enclosure URL, `sparkle:version`/`shortVersionString`, real `length`, no `edSignature`); the real-size population in both feeds; `brandlib` `SUFeedURL` resolves to the XML URL; the macOS tuple fix (the object stored in `_native_updater` exposes `checkForUpdates_`). Run with `.venv/bin/python -m pytest <path> -q --import-mode=importlib`; publisher tests from `tools/publisher/`.
- **Real end-to-end (keystone — the whole point):** build a packaged app at a version *below* the published latest (a local `0.1.99-test` build, or a `0.2.1` cut after this lands), install it, run it, click **Check now** → the native dialog must offer the newer version → download → the **KERI gate runs and passes** → the app is replaced. Performed in the main session (real UI). This is the proof that converts "verified-but-undeliverable" into "actually auto-updates."

## Scope

- **In:** publisher XML emission + real sizes; brand-manifest/`brandlib`/`SUFeedURL`/WinSparkle rewire to the XML feed; the macOS tuple fix; consolidating "Check now"/scheduler onto the native path + removing the controller discovery/banner code; the real-build validation.
- **Out:** a custom in-app update banner (deferred); any `verify.py`/`parse_appcast`/JSON-schema change; re-enabling the frameworks' own auto-check cadence; adding native appcast signatures (contingency only, if validation forces it); the broader Phase-3 branding pipeline wiring.

## Definition of done

The publisher emits valid XML appcasts (with real artifact sizes) to `appcast/v1/{macos,windows}.xml`; Sparkle/WinSparkle are pointed at the XML; the macOS Sparkle controller is reachable (`checkForUpdates_` fires); "Check now" and the scheduler drive the native updater and the dead controller-discovery path is removed; the JSON verifier is unchanged and still PASSes; unit tests cover the XML generation + the `SUFeedURL`/tuple fixes; and a real packaged build at a lower version is offered the newer version via the native dialog, the KERI gate verifies it, and it installs — on at least one platform end-to-end, with the second platform's native dialog confirmed to at least *discover* the update.

## Risks

1. **No-signature install refusal** (primary, above) — *Mitigation:* design no-sig first; native-sig contingency documented; the real-build validation catches it before announcing.
2. **JSON/XML feed divergence** — *Mitigation:* both generated from the same release data in one publisher step; a unit test asserts the XML enclosure URL + version match the JSON entry.
3. **Removing the controller breaks something that depended on it** (e.g. the critical-update banner, `last_checked` display) — *Mitigation:* audit consumers of `UpdateController`/`action_decided`/`check_failed` signals before removal; preserve the `last_checked` timestamp update on the native trigger; the critical-banner is YAGNI-deferred with the rest of the custom UI.
4. **macOS self-replacement / notarization of the updater helpers** — *Mitigation:* `Autoupdate`/`Installer.xpc` are already bundled + signed (`signLibs.sh`); the real-build validation exercises the actual replacement.
