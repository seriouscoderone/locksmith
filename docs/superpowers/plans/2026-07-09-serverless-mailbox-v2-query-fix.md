# Serverless-Mailbox v2 Query Fix + Vault Doer-Crash Resilience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the serverless-mailbox poller from crashing the vault on the KERI-v2 base, and make a background-doer crash tear the vault down honestly instead of leaving a live-but-dead reference.

**Architecture:** L1 v1-pins both mailbox query builders (clean v1 JSON, no v2 `Labeler` rejection of `/receipt` topic labels). L2a isolates the poller doer so a poll-cycle exception can't escape to the host Doist. L2b adds a `QtTask` `on_error` backstop wired to an honest vault teardown (close + navigate home + notice). L1+L2a land in the `keri-serverless-mailbox` package; L2b in Locksmith core/UI.

**Tech Stack:** Python 3.14, keri 2.0.0-dev6, hio Doist/DoDoer, PySide6 (QtTask over QTimer), pytest + pytest-qt.

## Global Constraints

- **Two repos, two branches (already created):**
  - Package: `~/code/keri-serverless-mailbox` on `fix/v2-query-serialization` (off `main`) — Tasks 1, 2.
  - Locksmith: `/Users/seriouscoderone/code/locksmith` on `fix/mailbox-v2-query` (off `development`) — Tasks 3, 4, 5.
- **Do NOT push either repo.** Package push to usuranceai and the Locksmith dependency re-pin are explicitly user-gated (a separate step after this plan). Local validation uses an editable install.
- **Test commands:**
  - Package: from `~/code/keri-serverless-mailbox`, `/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest -q` (pyproject sets `pythonpath = ["src", "../keripy/src"]`; baseline = 31 passed, 1 pre-existing pysodium warning).
  - Locksmith: `.venv/bin/python -m pytest <files> -q --import-mode=importlib`.
- **v1-hold marker:** every v1 pin carries a `# TRANSITIONAL (KERI v2 v1-hold)` comment (lifts jointly with the ecosystem's broader hold).
- **Commit trailers** (both repos, every commit):
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn
  ```
- Real-wallet/UI validation (Task 5) is **main-session only** (not a subagent); kill only PIDs you spawn.

---

### Task 1: L1 — v1-pin both mailbox query builders (package)

**Files:**
- Modify: `~/code/keri-serverless-mailbox/src/keri_serverless_mailbox/fetch.py` (imports + `build_and_post` ~line 83)
- Modify: `~/code/keri-serverless-mailbox/src/keri_serverless_mailbox/serverless.py` (imports + subscribe builder ~line 113)
- Test: `~/code/keri-serverless-mailbox/tests/test_query_v1.py` (new)

**Interfaces:**
- Consumes: keri `hab.query(pre, src, query, **kwa)` forwards `**kwa` to `eventing.query`, which accepts `version=` and `kind=`.
- Produces: both builders emit v1 JSON (`{"v":"KERI10JSON…}`) regardless of the keri global default.

- [ ] **Step 1: Write the failing test**

Create `~/code/keri-serverless-mailbox/tests/test_query_v1.py`:

```python
"""The mailbox query builders must serialize v1 JSON.

Regression: on the v2 base, hab.query defaults to v2 CESR-native serialization, whose
Labeler rejects the '/receipt' (slash-prefixed) topic map label -> SerializeError, which
crashed the vault. The wire protocol requires slash-prefixed query topics, so v1 JSON is
the compatible serialization.
"""
from types import SimpleNamespace

from keri.app import habbing
from keri.core import signing
from keri.kering import Vrsn_1_0

from keri_serverless_mailbox import fetch as fetch_mod
from keri_serverless_mailbox import serverless as serverless_mod


def _v1_hab():
    hby = habbing.Habery(name="q", bran="A" * 21,
                         salt=signing.Salter(raw=b"0123456789abcdef").qb64,
                         temp=True, version=Vrsn_1_0)
    hab = hby.makeHab(name="a", isith="1", icount=1, transferable=True,
                      version=Vrsn_1_0)
    return hby, hab


def test_build_and_post_serializes_v1_json(monkeypatch):
    hby, hab = _v1_hab()
    try:
        captured = {}
        monkeypatch.setattr(fetch_mod.httping, "createCESRRequest",
                            lambda msg, client, dest: captured.__setitem__("msg", bytes(msg)))
        cursor_store = SimpleNamespace(get=lambda *a, **k: None)
        # Would raise SerializeError today (v2 default) on the '/receipt' label.
        fetch_mod.build_and_post(hab, hab.pre, ["/receipt", "/replay"],
                                 cursor_store, client=object())
        assert captured["msg"].startswith(b'{"v":"KERI10JSON'), captured["msg"][:24]
    finally:
        hby.close()


def test_subscribe_builder_serializes_v1_json(monkeypatch):
    """Drive run_serverless via its injectable ws_factory seam so the REAL
    _subscribe_builder (serverless.py:113) runs; assert the envelope qry is v1 JSON."""
    import base64
    import pytest

    hby, hab = _v1_hab()
    try:
        monkeypatch.setattr(hab, "fetchUrl", lambda eid, scheme=None: "wss://x")
        captured = {}

        class _Stop(Exception):
            pass

        def fake_ws_factory(*, hab, eid, url, subscribe_builder, **kw):
            captured["env"] = subscribe_builder()   # exercises serverless.py:113
            raise _Stop()

        gen = serverless_mod.run_serverless(
            hab=hab, eid="Embx", topics=["/receipt"],
            on_message=lambda t, r: None,
            cursor_store=SimpleNamespace(get=lambda *a, **k: None),
            scheduler=SimpleNamespace(extend=lambda d: None, remove=lambda d: None),
            ws_factory=fake_ws_factory)
        next(gen)                       # advance past the initial `yield tock`
        with pytest.raises(_Stop):
            gen.send(0.0)               # reach ws_factory -> subscribe_builder() -> _Stop
        qry = base64.b64decode(captured["env"]["qry"])
        assert qry.startswith(b'{"v":"KERI10JSON'), qry[:24]
    finally:
        hby.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/code/keri-serverless-mailbox && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_query_v1.py -q`
Expected: BOTH tests FAIL — each raises `keri.kering.SerializeError: Invalid value while serializing` (v2 `Labeler` rejects the `/receipt` label) inside the query builder under test. `test_build_and_post_serializes_v1_json` fails at `build_and_post`; `test_subscribe_builder_serializes_v1_json` fails when the real `_subscribe_builder()` runs (the `SerializeError` escapes `pytest.raises(_Stop)`). Both go green once their pins land (Steps 3-4).

- [ ] **Step 3: Pin `build_and_post` to v1 JSON**

In `fetch.py`, add to the imports (after `from keri.app import agenting, httping`, line 20):

```python
from keri.kering import Vrsn_1_0, Kinds
```

Change the `build_and_post` query call (currently line 83):

```python
    # TRANSITIONAL (KERI v2 v1-hold): the mailbox wire protocol keys query topics by
    # slash-prefixed labels ('/receipt', ...), which v2 CESR Labeler forbids. Serialize
    # the qry as v1 JSON (compatible with the deployed federation). Lifts with the hold.
    msg = querier.query(pre=hab.pre, src=eid, route="mbx", query=q,
                        version=Vrsn_1_0, kind=Kinds.json)
```

- [ ] **Step 4: Pin the subscribe-envelope builder to v1 JSON**

In `serverless.py`, ensure `from keri.kering import Vrsn_1_0, Kinds` is imported (extend the existing `from keri.kering import ...` line if present, else add the line with the other keri imports). Change the `_subscribe_builder` query call (currently line 113):

```python
        # TRANSITIONAL (KERI v2 v1-hold): v1 JSON qry (slash-prefixed topic labels are
        # illegal as v2 CESR map labels). Matches the deployed mailbox wire contract.
        msg = querier.query(pre=hab.pre, src=eid, route="mbx",
                            query=dict(pre=hab.pre, topics=q_topics),
                            version=Vrsn_1_0, kind=Kinds.json)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ~/code/keri-serverless-mailbox && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_query_v1.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Confirm the package suite stays green**

Run: `cd ~/code/keri-serverless-mailbox && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest -q`
Expected: 33 passed (31 baseline + 2 new), 1 pre-existing pysodium warning.

- [ ] **Step 7: Commit (package repo)**

```bash
cd ~/code/keri-serverless-mailbox
git add src/keri_serverless_mailbox/fetch.py src/keri_serverless_mailbox/serverless.py tests/test_query_v1.py
git commit -m "fix(query): v1-pin the mbx qry builders for the KERI-v2 base

hab.query defaulted to v2 CESR-native serialization, whose Labeler rejects the
slash-prefixed '/receipt' topic map label -> SerializeError, which crashed the host
vault. Pin both builders (fetch.build_and_post + serverless subscribe envelope) to
v1 JSON, matching the deployed mailbox wire contract. TRANSITIONAL v1-hold.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 2: L2a — isolate the poller doer (package)

**Files:**
- Modify: `~/code/keri-serverless-mailbox/src/keri_serverless_mailbox/client.py` (`MailboxClientDoer.runDo`, the `yield from strategy.run(...)` ~line 50)
- Test: `~/code/keri-serverless-mailbox/tests/test_client.py` (add one test)

**Interfaces:**
- Consumes: `MailboxClientDoer(client)` with `client.resolve()` / `client.strategy_for(eid)` (monkeypatchable).
- Produces: a poll-cycle exception inside `strategy.run` is caught, logged, and ends the doer cleanly — it never propagates to the host Doist.

- [ ] **Step 1: Write the failing test**

Add to `~/code/keri-serverless-mailbox/tests/test_client.py`:

```python
def test_poller_swallows_strategy_error(monkeypatch):
    """A poll-cycle exception must not escape the doer into the host Doist.

    Regression: an unpinned v2 qry raised SerializeError inside strategy.run; it
    propagated out of the vault Doist and closed the whole vault db.
    """
    from hio.base import doing
    from keri_serverless_mailbox import MailboxClient, client as client_mod

    class BoomStrategy:
        def run(self, **kw):
            raise RuntimeError("boom")
            yield  # unreachable; makes run() a generator

    mc = MailboxClient(SimpleNamespace(pre="Edoi"), topics=["/x"],
                       on_message=lambda t, r: None,
                       cursor_store=SimpleNamespace(get=lambda *a, **k: None))
    monkeypatch.setattr(mc, "resolve", lambda: "Embx")
    monkeypatch.setattr(mc, "strategy_for", lambda eid: BoomStrategy())

    doer = client_mod.MailboxClientDoer(mc)
    doist = doing.Doist(doers=[doer], limit=1.0, tock=0.1, real=False)
    doist.do()  # must NOT raise; the doer stops itself after logging
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/code/keri-serverless-mailbox && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_client.py::test_poller_swallows_strategy_error -q`
Expected: FAIL — `RuntimeError: boom` propagates out of `doist.do()`.

- [ ] **Step 3: Wrap the strategy run in the doer**

In `client.py`, change `MailboxClientDoer.runDo`'s tail (the `yield from strategy.run(...)`, line ~50):

```python
        strategy = c.strategy_for(eid)
        try:
            yield from strategy.run(hab=c.hab, eid=eid, topics=c.topics,
                                    on_message=c.on_message, cursor_store=c.cursor_store,
                                    retry_ms=c.retry_ms, scheduler=self)
        except Exception as e:  # noqa: BLE001 — a poll failure must not crash the host Doist
            logger.exception(f"mailbox poller for {c.hab.pre} stopped after error: {e}")
            return
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/code/keri-serverless-mailbox && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_client.py -q`
Expected: PASS (existing client tests + the new one).

- [ ] **Step 5: Confirm the package suite stays green**

Run: `cd ~/code/keri-serverless-mailbox && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest -q`
Expected: 34 passed, 1 pre-existing pysodium warning.

- [ ] **Step 6: Commit (package repo)**

```bash
cd ~/code/keri-serverless-mailbox
git add src/keri_serverless_mailbox/client.py tests/test_client.py
git commit -m "fix(client): isolate the poller doer from the host Doist

A poll-cycle exception inside strategy.run used to propagate out of the host vault
Doist and tear down the whole vault db. Catch it in MailboxClientDoer.runDo: log and
stop this poller cleanly; never propagate. A degraded poller must not crash its host.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 3: L2b-core — `QtTask` on_error backstop + vault wiring (Locksmith)

**Files:**
- Modify: `src/locksmith/core/tasking.py` (`QtTask.__init__` + `run` except branch)
- Modify: `src/locksmith/core/vaulting.py` (`run_vault_controller` passes `on_error`)
- Modify: `src/locksmith/core/apping.py` (`LocksmithApplication.__init__` sets `self.on_vault_crash = None`)
- Test: `tests/test_qttask_on_error.py` (new)

**Interfaces:**
- Produces: `QtTask(doist, timer, limit=None, tyme=None, on_error=None)`. When `on_error` is set, `run` calls `on_error(exc)` on a doer exception and does NOT re-raise; when `None`, it re-raises (unchanged). `LocksmithApplication.on_vault_crash` is a callable-or-None attribute the window sets (Task 4); `run_vault_controller` invokes it (deferred) via the `QtTask` `on_error` hook.

- [ ] **Step 1: Write the failing test**

Create `tests/test_qttask_on_error.py`:

```python
"""QtTask must not silently leave a live-but-dead vault: on a doer exception it invokes
on_error (if set) instead of re-raising, so the host can tear down honestly."""
import pytest
from hio.base import doing
from PySide6.QtCore import QTimer

from locksmith.core.tasking import QtTask


def _boom_doer():
    def _boom(tymth=None, tock=0.0, **kwa):
        yield tock
        raise RuntimeError("boom")
    return doing.doify(_boom)


def test_on_error_called_and_not_reraised(qapp):
    doist = doing.Doist(doers=[_boom_doer()], tock=0.01, real=False)
    captured = {}
    qt = QtTask(doist, QTimer(), on_error=lambda e: captured.__setitem__("e", e))
    qt.run()  # recur -> doer raises -> except -> on_error, no re-raise
    assert isinstance(captured.get("e"), RuntimeError)


def test_reraises_without_on_error(qapp):
    doist = doing.Doist(doers=[_boom_doer()], tock=0.01, real=False)
    qt = QtTask(doist, QTimer())  # on_error defaults None -> preserve re-raise
    with pytest.raises(RuntimeError):
        qt.run()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_qttask_on_error.py -q --import-mode=importlib`
Expected: `test_on_error_called_and_not_reraised` FAILS — `QtTask.__init__` got an unexpected keyword argument `on_error` (and, once that's added, would still re-raise). `test_reraises_without_on_error` passes.

- [ ] **Step 3: Add the on_error hook to QtTask**

In `src/locksmith/core/tasking.py`, change `QtTask.__init__` signature and store the hook:

```python
    def __init__(self, doist, timer, limit=None, tyme=None, on_error=None):
```

Immediately after `self.shutdown_requested = False` (line 26), add:

```python
        self.on_error = on_error
```

Change the `except Exception` branch in `run` (currently lines 82-85) to:

```python
        except Exception as e:
            logger.exception(f'QtTask exception: {e}')
            self.timer.stop()
            if self.on_error is not None:
                self.on_error(e)
            else:
                raise
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_qttask_on_error.py -q --import-mode=importlib`
Expected: PASS (2 passed).

- [ ] **Step 5: Wire run_vault_controller + the app attribute**

In `src/locksmith/core/apping.py`, in `LocksmithApplication.__init__`, add (near the other instance attributes, e.g. alongside `self.vault = None`):

```python
        # Set by the window (ui/window.py): called when a vault background doer crashes,
        # so the vault is torn down honestly instead of left live-but-dead. None until set.
        self.on_vault_crash = None
```

In `src/locksmith/core/vaulting.py` `run_vault_controller`, replace the `QtTask` construction so a doer crash defers to the app's crash handler (deferred one event-loop turn so teardown does not re-enter the crashed tick):

```python
    def _on_doer_crash(exc):
        # Defer: run the teardown on a fresh event-loop turn, not inside the crashed tick.
        handler = getattr(app, "on_vault_crash", None)
        if handler is not None:
            QTimer.singleShot(0, lambda: handler(exc))
        else:
            logger.error(f"Vault doer crashed and no crash handler is set: {exc}")

    qtask = QtTask(doist=doist, timer=timer, limit=expire, on_error=_on_doer_crash)
```

(`QTimer` is already imported in `vaulting.py`.)

- [ ] **Step 6: Run the QtTask test + a vaulting import sanity check**

Run: `.venv/bin/python -m pytest tests/test_qttask_on_error.py -q --import-mode=importlib && .venv/bin/python -c "import locksmith.core.vaulting, locksmith.core.apping"`
Expected: 2 passed; imports clean (no output).

- [ ] **Step 7: Commit (Locksmith)**

```bash
git add src/locksmith/core/tasking.py src/locksmith/core/vaulting.py src/locksmith/core/apping.py tests/test_qttask_on_error.py
git commit -m "feat(tasking): QtTask on_error backstop for vault doer crashes

A background doer crash used to re-raise into Qt after stopping the timer, leaving
app.vault live-but-dead (db closed, reference kept). QtTask gains an optional on_error
hook: on a doer exception it calls on_error(exc) instead of re-raising. run_vault_controller
wires it to app.on_vault_crash (deferred one event-loop turn), which the window sets to an
honest teardown. Default (no on_error) preserves the re-raise for existing callers/tests.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 4: L2b-ui — window crash handler (Locksmith)

**Files:**
- Modify: `src/locksmith/ui/window.py` (set `self.app.on_vault_crash` + add `_on_vault_crash`)

**Interfaces:**
- Consumes: `app.on_vault_crash` (Task 3); the existing `on_lock_vault` teardown sequence (window.py:539-562), `self.nav_manager`, `self.toolbar`, `Pages.HOME`, `locksmith.core.branding.app_title`.

- [ ] **Step 1: Wire the app callback in window setup**

In `src/locksmith/ui/window.py`, immediately after `self.app = LocksmithApplication(config=config)` (line 46), add:

```python
        self.app.on_vault_crash = self._on_vault_crash
```

- [ ] **Step 2: Add the crash handler (mirrors on_lock_vault + a notice)**

In `src/locksmith/ui/window.py`, add this method next to `on_lock_vault` (after line 562):

```python
    def _on_vault_crash(self, exc):
        """A vault background doer crashed. Tear down honestly (close + home + notice)
        instead of leaving a live-but-dead app.vault. Wired via app.on_vault_crash and
        invoked (deferred) from run_vault_controller's QtTask on_error hook."""
        logger.error(f"Vault background task crashed; closing vault: {exc}")
        if self.app.is_vault_open:
            self._disconnect_toast_signals()
            if self.current_toast:
                self.current_toast.close_toast()
            self.app.close_vault()
        self.nav_manager.clear_navigation_stack()
        self.nav_manager.navigate_to(Pages.HOME)
        from locksmith.core.branding import app_title
        self.setWindowTitle(app_title(None))
        self.toolbar.set_vault_name(None)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            self, "Vault closed",
            "The vault closed because a background task failed. Your data is safe — "
            "please reopen the vault to continue.")
```

- [ ] **Step 3: Import sanity + focused window construction check**

Run: `.venv/bin/python -c "import locksmith.ui.window"`
Expected: clean import (no output). (The handler is exercised live in Task 5; it is UI-plumbing that mirrors the already-tested `on_lock_vault` path, so no separate unit test — verified in the real wallet.)

- [ ] **Step 4: Commit (Locksmith)**

```bash
git add src/locksmith/ui/window.py
git commit -m "feat(window): honest vault teardown on a background-doer crash

Set app.on_vault_crash to a handler that mirrors on_lock_vault (close vault, clear nav,
navigate home, reset title) plus a 'Vault closed' notice, so a crashed vault becomes an
honest closed state instead of a live-but-dead reference the user is stranded on.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q2VVcBXPMPfy75MqXPo8kn"
```

---

### Task 5: Live validation (Locksmith, MAIN SESSION)

Real-wallet validation is the acceptance gate. Main session only. Kill only PIDs you spawn.

- [ ] **Step 1: Editable-install the fixed package into the Locksmith venv**

```bash
cd /Users/seriouscoderone/code/locksmith
.venv/bin/pip install -e ~/code/keri-serverless-mailbox
.venv/bin/python -c "import keri_serverless_mailbox as m; print(m.__file__)"
```
Expected: the printed path is under `~/code/keri-serverless-mailbox/src/…` (the editable branch, carrying L1+L2a), not `site-packages/keri_serverless_mailbox` from the old wheel.

- [ ] **Step 2: Launch the wallet with the log captured**

```bash
LOG_LEVEL=INFO .venv/bin/python -m locksmith.main > /tmp/mbxfix.log 2>&1 &
```
Wait for `DevControlServer listening` in `/tmp/mbxfix.log`, then drive via `.venv/bin/devctl` (objectName selectors).

- [ ] **Step 3: Open carrier2 and confirm L1 (no crash, mailbox works, vault healthy)**

Drive: click `vaultDrawer.open.carrier2` → type `noble` into `openVaultDialog.passcodeField` → click `openVaultDialog.openButton`. Then:
- `grep -c "SerializeError\|QtTask exception" /tmp/mbxfix.log` → **0** (the crash is gone).
- `grep -c "Eligible local identifier load skipped: vault database is closed" /tmp/mbxfix.log` → **0** (db stays open).
- Click "KERI Foundation" (by text) → the onboarding page's AID selector lists the `primary` AID (not an empty selector). Screenshot to confirm.
- The Identifiers page shows `primary`. The vault is fully functional.
- Confirm a `/mbx` query was posted (log shows the mailbox poll running, no error).

- [ ] **Step 4: Confirm L2b (honest teardown) — optional injected-crash spot check**

In a throwaway edit (do NOT commit), make a vault doer raise once (e.g. temporarily raise inside a poll cycle before Task-1's pin, or add a one-shot `raise` in a background doer), relaunch, open a vault, and confirm: the "Vault closed" notice appears, the app navigates HOME, and `app.vault` is cleared (no crash, no stranded dead page). Revert the throwaway edit. (If this is impractical, note that L2b is covered by the Task-3 unit tests + the wired handler and skip the live injection.)

- [ ] **Step 5: Close the spawned wallet + record results**

Kill only the PID you launched. Write the validation results (log grep counts, screenshot path, L2b outcome) into the final report. No commit in this task (validation only).

---

## Final verification

- Package: `cd ~/code/keri-serverless-mailbox && /Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest -q` → 34 passed.
- Locksmith: `.venv/bin/python -m pytest tests/test_qttask_on_error.py -q --import-mode=importlib` → 2 passed; `import locksmith.ui.window` clean.
- Live: Task 5 Step 3 confirms no `SerializeError`, vault healthy, mailbox polling.

## Gated follow-up (NOT in this plan — do only on explicit user OK)
- Push the package branch to usuranceai (gh auth switch → push → restore seriouscoderone).
- Re-pin Locksmith's `keri-serverless-mailbox` dependency to the pushed commit and commit that on `fix/mailbox-v2-query`.
- Merge/PR per repo via finishing-a-development-branch.
