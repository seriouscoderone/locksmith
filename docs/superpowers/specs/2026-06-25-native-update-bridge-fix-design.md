# Native Update Bridge Fix — Design

**Date:** 2026-06-25
**Status:** Approved (brainstorm) — ready for implementation plan
**Repo:** locksmith (`~/code/locksmith`); publisher at `tools/publisher/`
**Follows:** the update discovery/delivery fix (`2026-06-24-update-discovery-delivery-fix*`, merged) — which fixed the *feed* but surfaced that the native *bridges* were never functional.

## Summary

Make the in-app auto-update path **actually work end-to-end**, validated properly rather than assumed. The discovery/delivery effort shipped a correct XML feed + KERI gate, but real-build validation exposed three independent defects: (1) the macOS Sparkle bridge was never functional (multiple stacked bugs); (2) the Windows/WinSparkle path is undiagnosed (no dialog, separate mechanism); (3) the publisher's KEL export is receipt-timing-fragile, so a freshly-anchored release can be published under-receipted and the install gate would reject it. This is one combined effort because all three block "a user clicks Check now and gets a verified update," and the macOS work needs a fast local validation loop the others benefit from.

## Context — what real-build validation found (versions 0.2.0–0.2.4)

- **macOS Sparkle, bug 1 (fixed, proven):** `from Sparkle import SPUStandardUpdaterController` never resolved (no `pyobjc-framework-Sparkle`; Sparkle is third-party). The updater never initialized. Fixed (dev `be102a4`) via `objc.loadBundle` on the bundled `Sparkle.framework` + `objc.lookUpClass`; `0.2.3` built with `native=yes` (proven in the frozen app).
- **macOS Sparkle, bug 2 (fix applied, dialog unverified):** the controller was constructed `startingUpdater:False` and `startUpdater()` was never called → `checkForUpdates_` is a silent no-op (fired but Sparkle stayed silent, no dialog). Fixed (dev `d12179a`) by calling `startUpdater()`. The dialog can only be confirmed in a running frozen build (Qt run loop + Sparkle UI), which is the validation gap this effort closes.
- **Publisher receipt-timing (unfixed):** `anchor_release` (`publish.py`) runs `kli interact` then immediately `clonePreIter`-exports. The new ixn's witness receipts arrive async (eventually-consistent on the DynamoDB-backed federation), so the exported KEL can carry `< toad` (3) receipts for the latest anchor → `replay_kel`'s toad check escrows it → `verify_artifact` raises `StaleAppcastError` → the install gate rejects a legit update. Intermittent: `0.2.0`/`0.2.2` gathered enough in time; `0.2.4` did not.
- **Windows (undiagnosed):** same "no dialog," but a separate ctypes → `WinSparkle.dll` path (no PyObjC), so the macOS fixes don't touch it. A Windows GUI app has no console stderr, so it needs diagnostic visibility before a root cause.

## Locked decisions (from brainstorm)

1. **One combined spec** covering macOS Sparkle + publisher receipt-timing + Windows.
2. **A local build-and-run validation loop** for macOS, so Sparkle UI fixes validate in ~1 minute instead of ~12-min CI cuts. Unsigned is fine for **discovery** iteration (launch the inner executable directly, bypassing Gatekeeper); the **signed install** path is proven once at the end via a real CI cut (or a local Developer-ID-signed build if the cert is available).
3. **Design for no native (transport) signature first.** Keep the existing stance — KERI is sole trust, Sparkle EdDSA / WinSparkle DSA OFF — and *validate* that the frameworks accept a code-signed update with no appcast signature. Add a native transport signature (a second, non-KERI key) **only if** validation proves a framework refuses it; documented contingency, not built otherwise.
4. **The KERI verifier / trust model is untouched** (`update/verify.py`, `parse_appcast`, `replay_kel`, the JSON schema). The publisher self-verify in §C reuses `replay_kel` as-is.
5. **Two macOS fixes already landed** on `development` (`be102a4`, `d12179a`); this effort builds on them.

## A. Local build-and-run validation loop

Add `scripts/devbuild-macos.sh` (or a documented sequence) that produces a runnable `.app` for fast iteration:
1. Run PyInstaller against `packaging/Locksmith.macos.spec` with the publisher anchor + deploy_config injected (so the gate is live and `SUFeedURL` resolves), at a version **below** the live feed (e.g. set an override so the built app is `0.2.3` while the feed serves `0.2.4`).
2. Replicate the framework staging `build-macos.sh` does *after* PyInstaller — copy `Sparkle.framework` (and confirm `objc`) into `Contents/Frameworks/` (a bare PyInstaller run omits this; that's why a hand-rolled build wouldn't load Sparkle).
3. **Skip signing/notarization** for discovery runs.
4. Launch via `Contents/MacOS/Locksmith` with stderr captured; the controller is driven through "Check now."

The loop: edit `sparkle_init`/bridge → `devbuild-macos.sh` → launch → Check now → read the log + watch for the dialog. The signed-install half (download → gate → replace) is validated once via a CI cut at the end.

## B. macOS Sparkle correctness

With bugs 1–2 fixed, iterate the local loop until **the dialog renders and an update installs**, fixing whatever further layers surface — candidates: the user-driver / `SPUStandardUserDriver` wiring, the run-loop interaction with Qt, first-launch permission-prompt suppression (`SUEnableAutomaticChecks=False` should suppress it — confirm), and the delegate protocol selectors (`sparkle_bridge.make_objc_delegate`) actually matching Sparkle 2's expected signatures. Each fix is verified in the loop before moving on (systematic-debugging: one hypothesis at a time).

**The no-`edSignature` fork (the primary unknown):** Sparkle 2 can update a Developer-ID-signed app with no EdDSA appcast signature (it validates the downloaded app's code signature). Design for that; the loop's signed-install step (final CI cut) is what proves or disproves it. If Sparkle refuses, the contingency is adding `SUPublicEDKey` + signing the appcast enclosures with an EdDSA key (and the publisher emitting `sparkle:edSignature`) — a second non-KERI transport key, built only if forced.

## C. Publisher receipt-timing robustness

Both layers fail-closed:
1. **Wait-for-receipts in `anchor_release`** (`tools/publisher/src/locksmith_publisher/publish.py`): after `kli_interact` and before the `clonePreIter` export, poll the new ixn's witness receipts (`hby.db.getWigs` / count the receipt couples for `(pre, sn)`) until `≥ toad` (3), with a bounded timeout (e.g. ~60s) and periodic re-query of the witnesses (mailbox/`Receiptor`) if they lag. Export only once the threshold is met; **raise loudly** on timeout (never emit an under-receipted KEL). `toad` comes from the publisher's witness config (the 5-of-5 federation, toad 3).
2. **Self-verify before upload (the durable guard):** before `publish` uploads, replay the locally-exported KEL through `replay_kel` (the same toad-gated path the client gate uses) and assert the *latest* release's anchor is accepted at the expected sn; refuse to upload otherwise. This catches the `0.2.4`-class failure at the publisher, before it can reach any user's install gate — independent of the timing fix.

## D. Windows / WinSparkle

Diagnosis-first, because a Windows GUI app has no console stderr:
1. **Visibility:** determine where keri-ogler writes on Windows; if it doesn't write a discoverable file, add a file log under `%LOCALAPPDATA%/Locksmith` (or a console-enabled diagnostic build) capturing startup + Check-now (`winsparkle.initialized` / `native_updater.*` / `win_sparkle_*` errors).
2. **Diagnose** from the captured log: DLL loaded? appcast fetched? rejected (no DSA)? check called?
3. **Fix** the root cause (likely analogous to macOS — init/start ordering, or the DSA-off signature posture, or the DLL path), then validate.

Windows validation runs in the operator's Parallels VM (the agent cannot reach it), so this piece is more hands-on and may land slightly behind macOS.

## Testing

- **macOS — local loop:** discovery proven when the native dialog renders against a local unsigned build below the live feed.
- **macOS — keystone (one CI cut):** an installed lower-version signed build discovers + downloads + the KERI gate verifies + installs a newer published version, relaunching at the new version. This proves the signature-acceptance question.
- **Publisher — unit:** the receipt-wait helper (polls to `toad`, raises on timeout) and the self-verify-before-upload guard (rejects an under-receipted KEL, accepts a fully-receipted one). Real-path: an actual anchor/publish whose published latest-anchor verifies via `verify_artifact` (the check that failed for `0.2.4`).
- **Windows:** the diagnostic log captures the failure; the fix is validated by Check-now offering + installing an update in the VM.
- Tests run with `.venv/bin/python -m pytest … --import-mode=importlib`; publisher from `tools/publisher/`.

## Scope

- **In:** the local macOS build/run loop; macOS Sparkle correctness through a rendered dialog + installed update; the publisher receipt-wait + self-verify-before-upload guard; Windows diagnostic visibility + root-cause fix.
- **Out:** any change to the KERI verifier / trust model; the second-key native appcast signature (contingency only, built solely if the macOS/Windows signed-install validation forces it); auto-update *cadence* changes (we keep driving from our scheduler); the brand engine.

## Definition of done

A local macOS build loop exists and is documented; the macOS native dialog renders and a published update installs through the KERI gate (signed, one CI cut), resolving the no-`edSignature` question (or the contingency is invoked + documented); the publisher waits for `≥ toad` receipts before export and self-verifies its KEL before upload (an under-receipted release can no longer be published); Windows has diagnostic visibility, a diagnosed root cause, and a validated fix (dialog offers + installs in the VM); the KERI verifier is unchanged.

## Risks

1. **Frameworks reject the no-`edSignature` feed** (primary unknown, both platforms). *Mitigation:* the signed-install validation surfaces it deterministically; the native-transport-signature contingency is scoped and ready if needed.
2. **Further hidden macOS Sparkle layers** (run-loop/user-driver) beyond startUpdater. *Mitigation:* the fast local loop makes iterating them cheap; systematic-debugging one at a time.
3. **Receipt-wait timeout on a slow witness round** legitimately blocks a release. *Mitigation:* bounded timeout + re-query + loud failure (operator re-runs) is correct fail-closed behavior; the self-verify guard is the backstop.
4. **Windows is only operator-validatable** (VM, no agent access). *Accepted:* diagnosis-first + file logging makes the hand-off concrete; Windows may trail macOS.
