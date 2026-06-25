# Native Update Bridge Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **READ THIS FIRST — execution shape.** This is a debugging/validation effort, not greenfield. Tasks split into two kinds, marked on each:
> - **[SUBAGENT/TDD]** — codeable now with complete code + unit tests (publisher guard, devbuild script, Windows logging). Dispatch as normal.
> - **[MAIN-SESSION RUNBOOK]** — the fix is *discovered by running* (macOS Sparkle UI iteration, the receipt re-collection's real-witness validation, Windows diagnosis, the signed-install CI cut). These are procedures executed in the main session (real UI / the Parallels VM / a live witness round), NOT pre-coded subagent tasks. Do them yourself, following systematic-debugging.

**Goal:** Make in-app auto-update actually deliver a verified update on macOS (and diagnose+fix Windows), and make the publisher refuse to ship an under-receipted release.

**Architecture:** A local PyInstaller build-and-run loop validates macOS Sparkle UI fixes in ~1 min (vs CI cuts). Two macOS Sparkle bugs are already fixed on `development` (`be102a4` import, `d12179a` startUpdater); iterate the loop until the dialog renders + an update installs. The publisher gains a receipt-wait (before KEL export) and a self-verify-before-upload guard (replays its own KEL through the toad-gated verifier). Windows is diagnosed via added file logging, then fixed.

**Tech Stack:** PyObjC (`objc.loadBundle`, bundled Sparkle.framework), PySide6/Qt, PyInstaller, keripy (`Habery`, `db.wigs`, `Kever`), WinSparkle (ctypes), pytest, Click.

## Global Constraints

- Tests: `.venv/bin/python -m pytest <path> -q --import-mode=importlib`; publisher from `tools/publisher/` (`cd tools/publisher && ../../.venv/bin/python -m pytest tests/ -q --import-mode=importlib`).
- **Do NOT touch the KERI verifier / trust model** (`src/locksmith/update/verify.py`, `kel_replay.py`, `appcast.py:parse_appcast`, the JSON schema). The publisher self-verify *reuses* `replay_kel` unchanged.
- **Native transport signature stays OFF** (no `sparkle:edSignature`/`SUPublicEDKey`, WinSparkle DSA off) UNLESS the signed-install validation proves a framework refuses a code-signed-only update — then the native-signature contingency is invoked (separate, out of this plan's default scope).
- keripy wig count for `(pre, latest)`: `from keri.db import dbing; len(hby.db.wigs.get(keys=dbing.dgKey(hab.pre, hab.kever.serder.said)) or [])`. toad: `hab.kever.toader.num`. (Use the memory's `~/code/KERI-COMMUNICATION-MODEL.md` model: receipts via `Receiptor`/mailbox — never the event POST; never `WitnessReceiptor` over HTTP.)
- Already on `development`: the macOS `objc.loadBundle` import fix (`be102a4`) + `startUpdater()` fix (`d12179a`). This plan starts from there.
- Commit footer (own line after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. No push/merge during task execution.

## File structure

- `tools/publisher/src/locksmith_publisher/publish.py` — `anchor_release` gains a receipt-wait; a new `assert_kel_anchors_release(...)` self-verify helper.
- `tools/publisher/src/locksmith_publisher/cli.py` — `publish` calls the self-verify guard before upload.
- `scripts/devbuild-macos.sh` (new) — local unsigned build + Sparkle/objc staging for the iteration loop.
- `src/locksmith/update/sparkle_init.py`, `sparkle_bridge.py` — any further macOS Sparkle fixes the loop surfaces (unknown until run).
- `src/locksmith/core/apping.py` or a logging-setup module + `src/locksmith/update/winsparkle_init.py` — Windows diagnostic file logging.
- Tests under `tools/publisher/tests/` and `tests/unit/update/`.

---

### Task 1 — [SUBAGENT/TDD] Publisher self-verify-before-upload guard

The durable fix for the under-receipted-KEL class: before `publish` uploads, replay the locally-exported KEL through the same toad-gated `replay_kel` the client gate uses, and refuse to upload unless the release's anchor is accepted at the expected sn.

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/publish.py` (add helper)
- Modify: `tools/publisher/src/locksmith_publisher/cli.py` (call it in `publish_cmd` before upload)
- Test: `tools/publisher/tests/test_self_verify.py` (create)

**Interfaces:**
- Produces: `assert_kel_anchors_release(*, kel_bytes: bytes, publisher_aid: str, version: str, anchor_said: str, toad: int) -> None` in `publish.py`. Replays `kel_bytes` via `locksmith.update.kel_replay.replay_kel` (embedded_sn=0, embedded_said=publisher_aid, the given toad) and raises `RuntimeError` unless an accepted event in `state.events` has `said == anchor_said` AND its `seals` carry `{"release": {"v": version}}`. (Accepted = present in `state.events`, which `replay_kel` only includes for toad-satisfied events — an under-receipted anchor is escrowed and absent, exactly the 0.2.4 failure.)

- [ ] **Step 1: Write the failing test** — `tools/publisher/tests/test_self_verify.py`:

```python
import types
import pytest
from locksmith_publisher import publish

_AID = "EHjWPRGoY9PV_tjNUJ7_XgwXLWg77fDm3BSGHd3lDFhD"


def _state(events):
    # Mimic kel_replay.KelState/ReplayedEvent shape (only fields the guard reads).
    ev = [types.SimpleNamespace(sn=e[0], said=e[1], seals=e[2]) for e in events]
    return types.SimpleNamespace(publisher_aid=_AID, current_sn=ev[-1].sn if ev else 0,
                                 events=ev)


def test_guard_passes_when_anchor_accepted(monkeypatch):
    monkeypatch.setattr(publish, "replay_kel", lambda **kw: _state([
        (0, "Eicp", []),
        (1, "Eanchor", [{"release": {"v": "0.2.4"}}]),
    ]))
    # Should not raise.
    publish.assert_kel_anchors_release(
        kel_bytes=b"x", publisher_aid=_AID, version="0.2.4",
        anchor_said="Eanchor", toad=3)


def test_guard_raises_when_anchor_not_accepted(monkeypatch):
    # Under-receipted anchor → escrowed → absent from state.events (the 0.2.4 bug).
    monkeypatch.setattr(publish, "replay_kel", lambda **kw: _state([
        (0, "Eicp", []),
    ]))
    with pytest.raises(RuntimeError, match="not anchored|not present|not accepted"):
        publish.assert_kel_anchors_release(
            kel_bytes=b"x", publisher_aid=_AID, version="0.2.4",
            anchor_said="Eanchor", toad=3)
```

- [ ] **Step 2: Run → fail** — `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_self_verify.py -q --import-mode=importlib` → `AttributeError: ... has no attribute 'assert_kel_anchors_release'`.

- [ ] **Step 3: Implement** — in `publish.py`, add the import + helper:

```python
from locksmith.update.kel_replay import replay_kel


def assert_kel_anchors_release(*, kel_bytes: bytes, publisher_aid: str,
                               version: str, anchor_said: str, toad: int) -> None:
    """Replay the exported KEL through the toad-gated verifier and confirm the
    release's anchor is ACCEPTED. Raises if the anchor is missing/escrowed —
    e.g. published with < toad witness receipts (the 0.2.4-class failure)."""
    state = replay_kel(kel_stream=kel_bytes, publisher_aid=publisher_aid,
                       embedded_sn=0, embedded_said=publisher_aid, toad=toad)
    for ev in state.events:
        if ev.said == anchor_said:
            for s in ev.seals:
                if isinstance(s, dict) and s.get("release", {}).get("v") == version:
                    return
            raise RuntimeError(
                f"anchor {anchor_said} accepted but does not carry release v{version}")
    raise RuntimeError(
        f"release v{version} anchor {anchor_said} not accepted in published KEL "
        f"(missing/escrowed — likely < toad={toad} witness receipts)")
```

- [ ] **Step 4: Wire into `publish_cmd`** — in `cli.py`, after reading `kel = (out / f"{aid}-kel.cesr").read_bytes()` and before the `s3.upload_release(...)` call, add:

```python
    from .publish import assert_kel_anchors_release
    assert_kel_anchors_release(kel_bytes=kel, publisher_aid=aid, version=version,
                               anchor_said=anchor_said, toad=cfg.get("toad", 3))
```

(`cfg` is the loaded deploy_config; `toad` defaults to 3 — the federation threshold. Add `"toad": 3` to `deploy_config.example.json` for explicitness.)

- [ ] **Step 5: Run → pass** — `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_self_verify.py tests/ -q --import-mode=importlib` (full publisher suite stays green).

- [ ] **Step 6: Commit** — `git add tools/publisher/src/locksmith_publisher/publish.py tools/publisher/src/locksmith_publisher/cli.py tools/publisher/tests/test_self_verify.py src/locksmith/release/deploy_config.example.json && git commit -m "feat(publisher): self-verify the exported KEL before upload (reject under-receipted release)"`

---

### Task 2 — [SUBAGENT/TDD for the read-side; MAIN-SESSION for real-witness validation] Receipt-wait in `anchor_release`

After `kli interact` and before the KEL export, wait until the new ixn has ≥ `toad` witness receipts, re-collecting from the witnesses if they lag. Fail loudly on timeout. The wig-count + loop are unit-testable (monkeypatch the DB read); the *re-collection actually gathering receipts* is validated against the live federation in Task 5's anchor run.

**Files:**
- Modify: `tools/publisher/src/locksmith_publisher/publish.py` (`anchor_release` + a `_wait_for_receipts` helper)
- Test: `tools/publisher/tests/test_receipt_wait.py` (create)

**Interfaces:**
- Produces: `_wait_for_receipts(hby, hab, *, toad: int, timeout_s: float = 90.0, recollect) -> int` — polls `len(hby.db.wigs.get(keys=dbing.dgKey(hab.pre, hab.kever.serder.said)) or [])`; while `< toad` and time remains, calls `recollect()` (a 0-arg callable that runs a receipt-collection pass) then re-polls; returns the final count; raises `TimeoutError` if `< toad` at timeout. `recollect` is injected so the unit test passes a no-op/fake and the real caller passes the keripy receipt pass.

- [ ] **Step 1: Write the failing test** — `tools/publisher/tests/test_receipt_wait.py`:

```python
import types
import pytest
from locksmith_publisher import publish


def _fake_hby_hab(counts):
    """counts: list of wig-counts returned on successive polls."""
    seq = iter(counts)
    class _Wigs:
        def get(self, *, keys):
            return ["w"] * next(seq)
    hby = types.SimpleNamespace(db=types.SimpleNamespace(wigs=_Wigs()))
    hab = types.SimpleNamespace(
        pre="Epre",
        kever=types.SimpleNamespace(serder=types.SimpleNamespace(said="Esaid")),
    )
    return hby, hab


def test_wait_returns_once_toad_met(monkeypatch):
    hby, hab = _fake_hby_hab([1, 2, 3])           # third poll meets toad=3
    calls = []
    n = publish._wait_for_receipts(hby, hab, toad=3, timeout_s=5.0,
                                   recollect=lambda: calls.append(1))
    assert n >= 3
    assert len(calls) >= 1                          # re-collected while short


def test_wait_raises_on_timeout(monkeypatch):
    hby, hab = _fake_hby_hab([1, 1, 1, 1, 1, 1])    # never reaches toad
    with pytest.raises(TimeoutError):
        publish._wait_for_receipts(hby, hab, toad=3, timeout_s=0.3,
                                   recollect=lambda: None)
```

- [ ] **Step 2: Run → fail** — `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_receipt_wait.py -q --import-mode=importlib` → no `_wait_for_receipts`.

- [ ] **Step 3: Implement the helper** — in `publish.py` (add `import time` and `from keri.db import dbing`):

```python
def _wait_for_receipts(hby, hab, *, toad, timeout_s=90.0, recollect):
    """Poll the latest event's witness-receipt count until >= toad, re-collecting
    from the witnesses each round while short. Raises TimeoutError on timeout."""
    deadline = time.monotonic() + timeout_s
    def _count():
        dgkey = dbing.dgKey(hab.pre, hab.kever.serder.said)
        return len(hby.db.wigs.get(keys=dgkey) or [])
    n = _count()
    while n < toad and time.monotonic() < deadline:
        recollect()
        time.sleep(2.0)
        n = _count()
    if n < toad:
        raise TimeoutError(
            f"only {n}/{toad} witness receipts for sn={hab.kever.sn} after {timeout_s}s")
    return n
```

- [ ] **Step 4: Run → pass** — `cd tools/publisher && ../../.venv/bin/python -m pytest tests/test_receipt_wait.py -q --import-mode=importlib`.

- [ ] **Step 5: Wire into `anchor_release` — [MAIN-SESSION: determine the keripy re-collect pass against the live federation].** In `anchor_release`, after `kli.kli_interact(...)` and after opening `hby`/`hab`, call `_wait_for_receipts(hby, hab, toad=hab.kever.toader.num, recollect=<receipt pass>)` BEFORE the `clonePreIter` export. The `recollect` callable runs a keripy `agenting.Receiptor` pass for `hab` against its configured witnesses (per `~/code/KERI-COMMUNICATION-MODEL.md`: `Receiptor`, NOT `WitnessReceiptor`). **This step is validated in Task 5** by anchoring a real release and confirming the wait gathers ≥3 receipts (the publisher's prior `kli interact --receipt-endpoint` already uses `Receiptor`, so the re-collect mirrors that). If a clean keripy `Receiptor` pass proves awkward, the acceptable fallback is re-invoking the publisher's existing `kli` receipt path (`kli_interact`'s `--receipt-endpoint` collects receipts; a `kli query`/witness-receipt subcommand re-collects without a new ixn) — confirm the exact subcommand against the installed `kli`. Commit once the real anchor (Task 5) shows the wait reaching toad.

- [ ] **Step 6: Commit** (after Task 5 validates) — `git add tools/publisher/src/locksmith_publisher/publish.py tools/publisher/tests/test_receipt_wait.py && git commit -m "feat(publisher): wait for >= toad witness receipts before KEL export"`

---

### Task 3 — [SUBAGENT/TDD] Local macOS build-and-run loop (`scripts/devbuild-macos.sh`)

A script that produces a runnable, unsigned `.app` carrying the current `development` code at a chosen version, with `Sparkle.framework`/`objc` staged exactly as `build-macos.sh` does — the fast iteration loop for Tasks 4–5.

**Files:**
- Create: `scripts/devbuild-macos.sh`
- Test: `tests/unit/update/test_devbuild_script.py` (create — static checks on the script)

**Interfaces:**
- Produces: `scripts/devbuild-macos.sh [VERSION]` — runs PyInstaller against `packaging/Locksmith.macos.spec` with the publisher anchor + deploy_config present (gate live, `SUFeedURL` resolves), overriding the build version to `$1` (default `0.0.0-dev`); copies `packaging/macos/Sparkle.framework` into the built `dist/Locksmith.app/Contents/Frameworks/` (mirroring `build-macos.sh`); skips signing/notarization; prints the path to launch (`dist/Locksmith.app/Contents/MacOS/Locksmith`).

- [ ] **Step 1: Read `packaging/build-macos.sh`** to copy its exact PyInstaller invocation + the post-build `Sparkle.framework` staging (the `cp -R packaging/macos/Sparkle.framework dist/Locksmith.app/Contents/Frameworks/` step), and how it sets the version (the spec reads `pyproject` version → for an override, the script may set a temp env or sed a copy; reuse build-macos.sh's mechanism if it has one, else build at the current `pyproject` version and document that the *feed* must advertise higher).
- [ ] **Step 2: Write the script** — `scripts/devbuild-macos.sh` with: `set -euo pipefail`; ensure the anchor/deploy_config are present (or `$LOCKSMITH_PUBLISHER_ANCHOR`/`$LOCKSMITH_DEPLOY_CONFIG` set); `.venv/bin/pyinstaller --noconfirm packaging/Locksmith.macos.spec`; `cp -R packaging/macos/Sparkle.framework dist/Locksmith.app/Contents/Frameworks/` (only if not already present from the spec); `echo` the launch path. Make it executable (`chmod +x`).
- [ ] **Step 3: Write a static test** — `tests/unit/update/test_devbuild_script.py`: assert the script exists, is executable, has `set -euo pipefail`, references `Locksmith.macos.spec`, and stages `Sparkle.framework` into `Contents/Frameworks/`. (No actual build in CI — PyInstaller is slow/mac-only; this guards the script's shape.)
- [ ] **Step 4: Run the test** → PASS.
- [ ] **Step 5: Smoke-run locally [MAIN-SESSION]** — run `scripts/devbuild-macos.sh 0.2.3`, confirm `dist/Locksmith.app/Contents/Frameworks/Sparkle.framework` exists and the app launches + logs `native=yes`. (This is the loop Tasks 4–5 use.)
- [ ] **Step 6: Commit** — `git add scripts/devbuild-macos.sh tests/unit/update/test_devbuild_script.py && git commit -m "feat(build): local macOS build-and-run loop for Sparkle iteration"`

---

### Task 4 — [MAIN-SESSION RUNBOOK] Iterate the macOS Sparkle dialog to render + install

Drive the local loop (Task 3) until **the native update dialog renders** against a published-higher feed, fixing whatever Sparkle layers surface beyond the two already fixed. Follow systematic-debugging: one hypothesis at a time, instrument via the app's stderr + macOS unified log.

- [ ] **Step 1:** Ensure the live feed advertises a version higher than the local build (e.g. `0.2.4` is published; build local `0.2.3`).
- [ ] **Step 2:** `scripts/devbuild-macos.sh 0.2.3` → launch `dist/Locksmith.app/Contents/MacOS/Locksmith` with stderr captured → Check now.
- [ ] **Step 3:** Read the app log for `native_updater.checkForUpdates_called` + the macOS unified log (`log show --last 3m --predicate 'process == "Locksmith"' --debug`, and a full-log grep for `Sparkle`/`SUUpdater`/`appcast`) to see what Sparkle does. Candidate layers if the dialog still doesn't appear: the `SPUStandardUserDriver` / user-driver wiring; the delegate selector signatures in `sparkle_bridge.make_objc_delegate` not matching Sparkle 2's protocol; the run-loop interaction with Qt; a first-launch permission prompt being suppressed incorrectly. Fix one, rebuild, re-check.
- [ ] **Step 4:** Once the dialog renders, commit each real fix (`fix(update): <sparkle layer>`), with a one-line note in the commit on how the loop confirmed it.
- [ ] **Step 5:** STOP and record in the ledger when the dialog reliably renders; proceed to Task 5 for the signed install.

---

### Task 5 — [MAIN-SESSION RUNBOOK] Signed-install + receipt-wait validation (one CI cut)

Prove the full chain on a signed build: discovery → download → KERI gate → install, and validate the publisher receipt-wait against the live federation. This is also where the **no-`edSignature` signature-acceptance** question resolves.

- [ ] **Step 1:** Merge the Task 1–4 work to `development`.
- [ ] **Step 2:** Cut a release `vX` (with all fixes) → install the signed build. Cut `vX+1` → **anchor it (this exercises Task 2's receipt-wait — confirm the wait reaches ≥3 receipts before export, and Task 1's self-verify passes)** → publish.
- [ ] **Step 3:** In the installed `vX`, Check now → dialog offers `vX+1` → **Install** → confirm the download + the KERI gate (`shouldProceedWithInstall`) passes + the app relaunches at `vX+1`.
- [ ] **Step 4:** If Sparkle REFUSES the no-`edSignature` update at install → the signature-acceptance contingency is confirmed needed: STOP, record it, and scope the native-signature follow-on (add `SUPublicEDKey` + publisher EdDSA appcast signing) — out of this plan's default scope.
- [ ] **Step 5:** Record the result (full e2e PASS, or the contingency triggered) in the ledger + memory.

---

### Task 6 — [SUBAGENT/TDD] Windows diagnostic file logging

A Windows GUI app has no console stderr, so before diagnosing WinSparkle we need its logs on disk.

**Files:**
- Modify: the app's logging setup (locate where `keri.help.ogler` is configured at startup — likely `src/locksmith/main.py` or `core/apping.py`) to also write a rotating file log under the per-OS data dir (`%LOCALAPPDATA%/Locksmith/logs/` on Windows; reuse `src/locksmith/update/log.py`'s data-dir resolver).
- Test: `tests/unit/update/test_file_logging.py` (create)

**Interfaces:**
- Produces: a `setup_file_logging() -> Path` (or extension of the existing logging setup) that ensures `[update] …`/`native_updater.*`/`winsparkle.*` lines land in a file under the data dir on all platforms; returns the log path.

- [ ] **Step 1:** Locate the current ogler/logging setup + the data-dir resolver in `src/locksmith/update/log.py` (the `~/Library/Application Support/Locksmith` / `%LOCALAPPDATA%/Locksmith` logic).
- [ ] **Step 2: Write the failing test** — assert `setup_file_logging()` returns a path under the data dir and that a logged line is written to it (use a tmp data dir via monkeypatch).
- [ ] **Step 3:** Implement the file handler (attach to the keri ogler / root logger), platform-correct path.
- [ ] **Step 4:** Run → pass; import smoke (`.venv/bin/python -c "import locksmith.main"`).
- [ ] **Step 5: Commit** — `git commit -m "feat(update): write diagnostic file log (enables Windows update debugging)"`

---

### Task 7 — [MAIN-SESSION / VM RUNBOOK] Diagnose + fix Windows WinSparkle

With file logging (Task 6) in a build, diagnose why no dialog appears on Windows, then fix.

- [ ] **Step 1:** Cut/obtain a Windows build with Task 6's logging; install the MSI in the Parallels VM.
- [ ] **Step 2:** Run it, Check now, retrieve `%LOCALAPPDATA%/Locksmith/logs/` — look for `winsparkle.initialized`, `native_updater.check_update_with_ui_called` / `unavailable`, and any `win_sparkle` errors.
- [ ] **Step 3:** Diagnose: did `load_winsparkle_dll()` succeed (DLL bundled + found)? did `win_sparkle_set_appcast_url` get the `.xml` URL? did the check fire? did WinSparkle reject the no-DSA feed? (Likely analogous to macOS — init/start ordering, DLL path, or the DSA-off posture.)
- [ ] **Step 4:** Fix the root cause (one hypothesis at a time), rebuild, re-test in the VM until the dialog offers + installs an update.
- [ ] **Step 5:** Record the Windows root cause + fix in the ledger + memory; if WinSparkle refuses the no-signature feed → the native-signature contingency (shared with Task 5's finding).

---

## Self-Review

**1. Spec coverage:** Local loop → Task 3. macOS Sparkle correctness → Tasks 4 (+ already-landed fixes). Signature-acceptance question → Task 5. Publisher receipt-wait → Task 2. Publisher self-verify guard → Task 1. Windows diagnosis+fix → Tasks 6–7. KERI-verifier-untouched → Global Constraints (no task touches it). ✓

**2. Placeholder scan:** Codeable tasks (1, 3, 6) carry full code/tests. The genuinely-discovered work (Tasks 4, 7) and the real-witness/keripy-Receiptor wiring (Task 2 Step 5, Task 5) are explicitly marked **[MAIN-SESSION RUNBOOK]** with concrete procedures — not hidden placeholders, but acknowledged investigation steps (this is a debugging effort; the fixes for unknown Sparkle/WinSparkle layers cannot be pre-coded without lying).

**3. Type consistency:** `assert_kel_anchors_release(*, kel_bytes, publisher_aid, version, anchor_said, toad)` — same in Task 1 def + cli.py call. `_wait_for_receipts(hby, hab, *, toad, timeout_s, recollect)` — same in Task 2 def + test. `replay_kel(...)→state.events[].said/.sn/.seals` — matches the extracted `KelState`/`ReplayedEvent`. wig-count + toad calls match the extracted keripy API. ✓

**Execution note:** dispatch Tasks 1, 3, 6 as subagents (clean TDD). Execute Tasks 2-Step-5, 4, 5, 7 in the main session (real witnesses / UI / VM). Task 2's read-side (Steps 1–4) is subagent-able; its wiring (Step 5) + commit wait for the main-session validation.
