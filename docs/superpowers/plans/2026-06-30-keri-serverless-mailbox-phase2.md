# keri-serverless-mailbox Package (Phase 2 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a standalone, reusable `keri-serverless-mailbox` package — a universal `MailboxClient` that resolves a mailbox via `agenting.mailbox`, discovers its delivery capability from a KEL-advertised `wss` loc scheme, and runs a swappable retrieval strategy (Phase 2 = `StandardStrategy` SSE; `ServerlessStrategy` is a Phase-3 stub) — and wire Locksmith to it, retiring Locksmith's forked `Poller` poll-loop.

**Architecture:** The package is **transport + cursor only**: it fetches CESR and calls `on_message(topic, raw_cesr_bytes)` + advances a host-supplied `CursorStore`. It does NOT parse (the host parses — Locksmith via its existing director parser, keeping `msgDo`/`escrowDo`; a standalone consumer via `psr.parse` in its `on_message`). Capability is discovered KERI-natively via `hab.fetchUrl(eid, scheme=wss)` (a new keripy loc scheme). One `hio` DoDoer adapter lets a host mount the client.

**Tech Stack:** Python 3.14; stock keripy primitives ONLY in the package (`agenting.mailbox`, `agenting.httpClient`, `hab.query`, `hab.fetchUrl`, `httping.createCESRRequest`, `hio` `doing`); pytest. No `locksmith` import in the package. WebSockets (`websockets` lib) are Phase 3, NOT this plan.

## Global Constraints

- **BE KERI NATIVE:** target resolution via `agenting.mailbox(hab, cid)` (role-first, witness-fallback); capability discovery via a signed `wss` loc scheme read through `hab.fetchUrl(eid, scheme=wss)` — no HTTP side-channel. Witnesses are the fallback mailbox, never the concept.
- **Package builds on stock keripy ONLY** — no `import locksmith`. It must be usable by any KERI Python client.
- **Phase 2 scope:** `MailboxClient` + `CursorStore` + `Strategy` + `StandardStrategy` (SSE) + capability discovery + the `wss` keripy scheme (CLIENT-READ) + Locksmith integration + the 2 carried review items. `ServerlessStrategy` is a **stub that raises `NotImplementedError("Phase 3: WS notify-and-fetch")`** so the discovery seam exists but WS is not built. NO WebSocket code, NO server-side `wss` publish, NO abuse-gating (all Phase 3).
- **keripy `wss` change is CLIENT-READ only** (so a standard mailbox returns `None` → `StandardStrategy`); no server advertises `wss` yet.
- **Package = transport + cursor, not parse.** `on_message(topic: str, raw_cesr: bytes)`; the host parses.
- **Branches:** keripy on a fresh branch off `development` (push to `fork` only); locksmith on a fresh branch off `development`; the new package is its own repo `~/code/keri-serverless-mailbox` on its own `main`. Commit per repo; do NOT push unless asked.
- **Locksmith pytest:** always `--import-mode=importlib`. Package pytest: standard (no shadow). keripy/concierge tests run with `~/code/locksmith/.venv/bin/python` (the only venv with keri).
- **wss-keri on the path (env — surfaced in Task 1):** keri is a NON-editable wheel in the venv, so the new `wss` scheme lives only in `~/code/keripy/src` on branch `feat/wss-loc-scheme`. Any process importing `keri.kering.Schemes.wss` (package runtime, package tests, locksmith integration) MUST have `~/code/keripy/src` ahead of the wheel: package tests via the pyproject `pythonpath=[…,"../keripy/src"]`; other invocations via a prepended `PYTHONPATH=~/code/keripy/src`. Keep `~/code/keripy` on `feat/wss-loc-scheme` for all of Phase 2. (No venv mutation; production gets `wss` via the keri-fork release path — a Phase-3 boundary.)
- **Test-setup lesson from Phase 1:** `makeEndRole`/`makeLocScheme` build a reply bytearray and do NOT persist to `db.ends`/`db.locs` without a parse pipeline. To set up an end-role/loc in a test, pin the record directly: `db.ends.pin(keys=(pre, Roles.mailbox, eid), val=EndpointRecord(allowed=True))` / `db.locs.pin(keys=(eid, scheme), val=LocationRecord(url=...))` (`EndpointRecord`/`LocationRecord` from `keri.recording`).

---

## File Structure

| File | Repo | Responsibility |
|---|---|---|
| `src/keri/kering.py:375` | keripy (fork) | add `wss` to `Schemes` (1-line) |
| `tests/core/test_wss_scheme.py` (or nearest) | keripy | round-trip `db.locs` `wss` → `fetchUrl(eid, scheme=wss)` |
| `pyproject.toml`, `src/keri_serverless_mailbox/__init__.py` | NEW pkg | package metadata + public exports |
| `src/keri_serverless_mailbox/cursor.py` | NEW pkg | `CursorStore` Protocol |
| `src/keri_serverless_mailbox/strategy.py` | NEW pkg | `Strategy` ABC + `ServerlessStrategy` stub |
| `src/keri_serverless_mailbox/standard.py` | NEW pkg | `StandardStrategy` (SSE fetch, port of `Poller.eventDo`) |
| `src/keri_serverless_mailbox/client.py` | NEW pkg | `MailboxClient` (resolve + discover + select) + `MailboxClientDoer` (hio adapter) |
| `tests/test_*.py` | NEW pkg | unit tests with fakes |
| `src/locksmith/core/indirecting.py` | locksmith | `add_poller` dedup-merge guard; retire `Poller`; mount `MailboxClient` |
| `src/locksmith/core/mailbox_cursor.py` (new) | locksmith | `DbTopsCursorStore` adapter over `db.tops` |
| `tests/test_mailbox_kel_seed.py` | locksmith | add negative/idempotency cases |
| `tests/test_mailbox_client_integration.py` (new) | locksmith | MailboxClient mounts + on_message feeds the parser |
| `pyproject.toml` | locksmith | add `keri-serverless-mailbox` dep |

---

## Task 1: keripy — add the `wss` loc scheme (client read)

**Files:**
- Modify: `~/code/keripy/src/keri/kering.py:375`
- Test: `~/code/keripy/tests/core/test_wss_scheme.py` (create)

**Interfaces:**
- Produces: `kering.Schemes.wss == "wss"`; `hab.fetchUrl(eid, scheme=Schemes.wss)` returns a pinned `wss` loc URL or `None`.

- [ ] **Step 1: Write the failing test.**

Create `~/code/keripy/tests/core/test_wss_scheme.py`:
```python
from keri.app import habbing
from keri.core import signing
from keri.kering import Schemes
from keri.recording import LocationRecord


def test_wss_loc_scheme_round_trips():
    assert getattr(Schemes, "wss", None) == "wss"          # scheme is registered
    with habbing.openHby(name="wsstest", temp=True) as hby:
        hab = hby.makeHab(name="svc")
        # Pin a wss loc directly (makeLocScheme builds a reply; it does not persist to db.locs).
        hab.db.locs.pin(keys=(hab.pre, Schemes.wss),
                        val=LocationRecord(url="wss://mailbox.example/prod"))
        assert hab.fetchUrl(hab.pre, scheme=Schemes.wss) == "wss://mailbox.example/prod"
        assert hab.fetchUrl(hab.pre, scheme=Schemes.https) == ""   # absent scheme -> empty
```

- [ ] **Step 2: Run it to verify it fails.**

Run (from `~/code/keripy`):
```bash
~/code/locksmith/.venv/bin/python -m pytest tests/core/test_wss_scheme.py -q 2>&1 | tail -15
```
Expected: FAIL at `Schemes.wss` (AttributeError — `wss` not yet in `Schemes`). (If `LocationRecord`'s import path differs, the implementer confirms it in `keri/recording.py` — it lives beside `EndpointRecord:229`.)

- [ ] **Step 3: Add `wss` to `Schemes`.**

In `~/code/keripy/src/keri/kering.py:374-375`, change BOTH lines:
```python
# Before:
Schemage = namedtuple("Schemage", 'tcp http https')
Schemes = Schemage(tcp='tcp', http='http', https='https')
# After:
Schemage = namedtuple("Schemage", 'tcp http https wss')
Schemes = Schemage(tcp='tcp', http='http', https='https', wss='wss')
```
**This is the ONLY keripy file to edit** (confirmed by exploration). It mirrors exactly how
keripy added `gateway` to `Roles` — a 2-line namedtuple edit; `db.locs`/`db.ends` are
free-form string stores, so no migration. `Schemes` is a **closed allowlist**: a
`/loc/scheme` reply with `scheme="wss"` is rejected at `eventing.py:5120`
(`if scheme not in Schemes`) — and at the REST gate `ending.py:452` — BEFORE the DB, so the
enum edit is required (you cannot duck-type around it, and you cannot piggyback a `wss://`
URL on the `http` scheme — `eventing.py:5126-5128` validates the URL's scheme-prefix against
the `scheme` field). After the edit: the gate accepts `wss`, `db.locs` stores it under
`(eid, "wss")`, and `hab.fetchUrl(eid, scheme=Schemes.wss)` returns it.
**Blast radius (verified, benign + additive, stays on the endpoint/loc seam):** only
`agenting.schemes()` (`agenting.py:1095`) and `kli ends export` (`export.py:65`)
additionally iterate `wss` — desired (they propagate/export the advertisement); every other
consumer (OOBI/DID generation, messenger factories, witness resolution) selects
`http`/`https`/`tcp` by name and ignores `wss`. In practice only mailbox AIDs carry a `wss`
loc, so the effect is confined to the mailbox capability.

- [ ] **Step 4: Run it to verify it passes.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/core/test_wss_scheme.py -q 2>&1 | tail -8`
Expected: PASS.

- [ ] **Step 5: Sanity-check no scheme regressions.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/app/test_habbing.py -q -k "loc or scheme or url" 2>&1 | tail -10`
Expected: PASS (existing loc/scheme behavior unaffected by the additive enum field).

- [ ] **Step 6: Commit (keripy fork branch).**

```bash
cd ~/code/keripy && git checkout -b feat/wss-loc-scheme development
git add src/keri/kering.py tests/core/test_wss_scheme.py
git commit -m "feat(kering): add wss loc scheme (client-side mailbox capability discovery)

Lets a client discover a serverless notify-and-fetch mailbox via a KEL-advertised wss
loc: hab.fetchUrl(eid, scheme=Schemes.wss). Additive enum field; validation/parse paths
already key off Schemes. Server-side advertisement is Phase 3.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: package scaffold + `CursorStore` + `Strategy` interface + capability discovery

**Files:**
- Create: `~/code/keri-serverless-mailbox/pyproject.toml`, `src/keri_serverless_mailbox/__init__.py`, `src/keri_serverless_mailbox/cursor.py`, `src/keri_serverless_mailbox/strategy.py`
- Test: `~/code/keri-serverless-mailbox/tests/test_discovery.py`

**Interfaces:**
- Produces:
  - `CursorStore` Protocol: `get(self, eid: str, topic: str) -> int | None`; `set(self, eid: str, topic: str, idx: int) -> None`.
  - `Strategy(ABC)`: `run(self, *, hab, eid, topics, on_message, cursor_store) -> Generator` (an `hio` doer generator).
  - `ServerlessStrategy(Strategy)`: `run(...)` raises `NotImplementedError("Phase 3: WS notify-and-fetch")`.
  - `discover_strategy(hab, eid) -> Strategy`: returns `ServerlessStrategy()` if `hab.fetchUrl(eid, scheme=Schemes.wss)` is truthy, else `StandardStrategy()` (imported in Task 3; until then `discover_strategy` returns the class flag — see Step 3).

- [ ] **Step 1: Write the failing test.**

Create `~/code/keri-serverless-mailbox/tests/test_discovery.py`:
```python
from keri.app import habbing
from keri.kering import Schemes
from keri.recording import LocationRecord

from keri_serverless_mailbox import discover_strategy, StandardStrategy, ServerlessStrategy


def test_discover_standard_when_no_wss_loc():
    with habbing.openHby(name="disc1", temp=True) as hby:
        hab = hby.makeHab(name="svc")
        assert isinstance(discover_strategy(hab, hab.pre), StandardStrategy)


def test_discover_serverless_when_wss_loc_present():
    with habbing.openHby(name="disc2", temp=True) as hby:
        hab = hby.makeHab(name="svc")
        hab.db.locs.pin(keys=(hab.pre, Schemes.wss),
                        val=LocationRecord(url="wss://mailbox.example/prod"))
        assert isinstance(discover_strategy(hab, hab.pre), ServerlessStrategy)
```

- [ ] **Step 2: Run it to verify it fails.**

Run (from `~/code/keri-serverless-mailbox`, after `pip install -e .` into the locksmith venv — see Step 3):
```bash
~/code/locksmith/.venv/bin/python -m pytest tests/test_discovery.py -q 2>&1 | tail -15
```
Expected: FAIL — `ModuleNotFoundError: keri_serverless_mailbox` (package not yet created).

- [ ] **Step 3: Create the package scaffold + cursor + strategy.**

`~/code/keri-serverless-mailbox/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "keri-serverless-mailbox"
version = "0.1.0"
description = "Universal KERI mailbox client: resolve via agenting.mailbox, discover capability from the KEL, run a swappable retrieval strategy (Standard SSE; Serverless WS in Phase 3)."
requires-python = ">=3.12"
dependencies = ["keri", "hio"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src", "../keripy/src"]
testpaths = ["tests"]
```
Then install editable into the shared venv: `~/code/locksmith/.venv/bin/python -m pip install -e ~/code/keri-serverless-mailbox`. The `../keripy/src` pythonpath puts the **wss-edited fork keri ahead of the venv wheel** for the package's tests (keri is a non-editable wheel; the wss scheme is only in `~/code/keripy/src` on `feat/wss-loc-scheme`, which must stay checked out). Without it, `Schemes.wss` raises AttributeError at import of `discover_strategy`.

`src/keri_serverless_mailbox/cursor.py`:
```python
"""CursorStore port: the host supplies per-(eid, topic) cursor persistence."""
from __future__ import annotations
from typing import Protocol


class CursorStore(Protocol):
    def get(self, eid: str, topic: str) -> int | None:
        """Last-seen index for (eid, topic), or None if never seen."""
        ...

    def set(self, eid: str, topic: str, idx: int) -> None:
        """Persist the last-seen index for (eid, topic)."""
        ...
```

`src/keri_serverless_mailbox/strategy.py`:
```python
"""Retrieval strategy interface + the Phase-3 Serverless stub.

A Strategy is transport + cursor only: it fetches CESR for the resolved mailbox EID and
calls on_message(topic, raw_cesr_bytes) per message, advancing the CursorStore. It does
NOT parse — the host parses (its own Parser, or psr.parse)."""
from __future__ import annotations
from abc import ABC, abstractmethod


class Strategy(ABC):
    @abstractmethod
    def run(self, *, hab, eid, topics, on_message, cursor_store, retry_ms=1000):
        """An hio doer generator: yields control, fetches, calls on_message + cursor_store."""
        raise NotImplementedError


class ServerlessStrategy(Strategy):
    """Phase 3: WebSocket notify-and-fetch. Selected when the mailbox advertises a wss loc."""
    def run(self, *, hab, eid, topics, on_message, cursor_store, retry_ms=1000):
        raise NotImplementedError("Phase 3: WS notify-and-fetch")
        yield  # pragma: no cover  (keeps this a generator function)
```

`src/keri_serverless_mailbox/__init__.py`:
```python
from .cursor import CursorStore
from .strategy import Strategy, ServerlessStrategy
from .standard import StandardStrategy
from .client import MailboxClient, MailboxClientDoer, discover_strategy

__all__ = ["CursorStore", "Strategy", "ServerlessStrategy", "StandardStrategy",
           "MailboxClient", "MailboxClientDoer", "discover_strategy"]
```
(`standard.py` / `client.py` land in Tasks 3-4; `__init__` importing them now means Task 2's test is run after Task 3-4 OR temporarily import only what exists. To keep TDD honest: in Task 2, have `__init__` export only `CursorStore`, `Strategy`, `ServerlessStrategy`, and define `discover_strategy` **in `strategy.py`** returning `ServerlessStrategy()` when `hab.fetchUrl(eid, scheme=Schemes.wss)` is truthy else a placeholder `StandardStrategy` imported lazily. Simplest: put `discover_strategy` + a minimal `StandardStrategy` shell in `strategy.py` in Task 2, and flesh `StandardStrategy.run` in Task 3.)

Concretely, add to `strategy.py` in Task 2:
```python
from keri.kering import Schemes


class StandardStrategy(Strategy):
    """SSE/poll retrieval for non-serverless mailboxes. run() implemented in standard.py
    (Task 3) via _run_standard; this shell exists so discovery can select it now."""
    def run(self, *, hab, eid, topics, on_message, cursor_store, retry_ms=1000):
        from .standard import run_standard
        yield from run_standard(hab=hab, eid=eid, topics=topics,
                                on_message=on_message, cursor_store=cursor_store,
                                retry_ms=retry_ms)


def discover_strategy(hab, eid) -> Strategy:
    """KERI-native capability discovery: a wss loc scheme on the mailbox EID => Serverless."""
    return ServerlessStrategy() if hab.fetchUrl(eid, scheme=Schemes.wss) else StandardStrategy()
```
And `__init__.py` exports `StandardStrategy`, `discover_strategy` from `strategy` (Task 4 adds `MailboxClient`/`MailboxClientDoer`).

- [ ] **Step 4: Run it to verify it passes.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/test_discovery.py -q 2>&1 | tail -10`
Expected: PASS (`discover_strategy` returns Standard with no wss loc, Serverless with one). Requires Task 1's `wss` scheme on path (`../keripy`).

- [ ] **Step 5: Commit (new package repo).**

```bash
cd ~/code/keri-serverless-mailbox && git init -q && git add -A
git commit -m "feat: scaffold keri-serverless-mailbox (CursorStore, Strategy, KERI-native discovery)

Universal mailbox client foundation: CursorStore port, Strategy ABC, ServerlessStrategy
Phase-3 stub, and discover_strategy() selecting by a wss loc scheme (hab.fetchUrl).
Builds on stock keripy only.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `StandardStrategy` — SSE fetch (port of `Poller.eventDo`)

**Files:**
- Create: `~/code/keri-serverless-mailbox/src/keri_serverless_mailbox/standard.py`
- Test: `~/code/keri-serverless-mailbox/tests/test_standard_strategy.py`

**Interfaces:**
- Consumes: `CursorStore` (Task 2); stock keripy `agenting.httpClient`, `hab.query`, `httping.createCESRRequest`.
- Produces: `run_standard(*, hab, eid, topics, on_message, cursor_store, retry_ms=1000)` — an `hio` doer generator that SSE-polls `eid`'s mailbox and calls `on_message(topic, raw_bytes)` + `cursor_store.set(eid, topic, idx)` per event.

- [ ] **Step 1: Write the failing test (fake HTTP client + fake CursorStore — deterministic, no network).**

Create `~/code/keri-serverless-mailbox/tests/test_standard_strategy.py`:
```python
from types import SimpleNamespace
from hio.base import doing

from keri_serverless_mailbox import standard


class _FakeCursorStore:
    def __init__(self): self.saved = {}
    def get(self, eid, topic): return self.saved.get((eid, topic))
    def set(self, eid, topic, idx): self.saved[(eid, topic)] = idx


def test_run_standard_delivers_events_and_advances_cursor(monkeypatch):
    received = []
    cur = _FakeCursorStore()

    # Fake the keripy transport: httpClient returns a client whose .events yields one SSE
    # event then drains; .requests empties immediately.
    class _Client:
        def __init__(self):
            self.requests = []
            self.events = __import__("collections").deque(
                [{"id": "0", "name": "/credential", "data": "AAAA-cesr"}])
    fake_client, fake_doer = _Client(), doing.Doer()
    monkeypatch.setattr(standard.agenting, "httpClient", lambda hab, eid: (fake_client, fake_doer))
    monkeypatch.setattr(standard.httping, "createCESRRequest", lambda msg, client, dest=None: None)

    hab = SimpleNamespace(pre="Edoi", query=lambda **kw: b"qry",
                          db=SimpleNamespace(tops=SimpleNamespace(get=lambda k: None)))
    gen = standard.run_standard(hab=hab, eid="Embx", topics=["/credential"],
                                on_message=lambda topic, raw: received.append((topic, raw)),
                                cursor_store=cur, retry_ms=1)
    # Drive the generator enough to process the queued event (bounded so the test can't hang).
    g = gen
    for _ in range(50):
        try: g.send(None) if received == [] else g.close()
        except StopIteration: break
        if received: break

    assert received and received[0][0] == "/credential"
    assert received[0][1] == b"AAAA-cesr"            # raw CESR bytes, NOT parsed
    assert cur.saved[("Embx", "/credential")] == 0   # cursor advanced to the event id
```
(The implementer may refine the driving loop; the assertions — `on_message` gets `(topic, raw_bytes)` and the cursor advances — are the contract.)

- [ ] **Step 2: Run it to verify it fails.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/test_standard_strategy.py -q 2>&1 | tail -15`
Expected: FAIL — `AttributeError: module 'keri_serverless_mailbox.standard' has no attribute ...` (module/func not defined).

- [ ] **Step 3: Implement `run_standard` (faithful port of `Poller.eventDo`, parse removed).**

Create `~/code/keri-serverless-mailbox/src/keri_serverless_mailbox/standard.py`:
```python
"""StandardStrategy transport: SSE/poll a mailbox EID for CESR, host parses.

Ported from Locksmith's Poller.eventDo (core/indirecting.py:320-406), with two changes:
(1) it does NOT parse — it calls on_message(topic, raw_bytes); (2) cursors live in the
host's CursorStore, not db.tops directly. Stock keripy primitives only."""
from __future__ import annotations
import datetime

from hio.help import helping
from keri.app import agenting, habbing
from keri.help import helping as _h  # nowUTC
from keri import help
from keri.end import ending  # noqa: F401  (keeps keri.end importable in some layouts)
import sys
import traceback

from keri import kering
from keri.core import routing  # noqa: F401
from keri.app import httping

logger = help.ogler.getLogger(__name__)


def run_standard(*, hab, eid, topics, on_message, cursor_store, retry_ms=1000):
    """hio doer generator. SSE-polls eid's mailbox; per event calls
    on_message(topic, raw_cesr_bytes) and cursor_store.set(eid, topic, idx)."""
    tock = 0.0
    _ = (yield tock)
    retry = retry_ms

    while retry > 0:
        try:
            client, clientDoer = agenting.httpClient(hab, eid)
        except kering.MissingEntryError as e:
            traceback.print_exception(e, file=sys.stderr)
            yield tock
            continue

        # Build the mbx query from per-topic cursors (last-seen + 1, or 0 if unseen).
        q_topics = {}
        for topic in topics:
            seen = cursor_store.get(eid, topic)
            q_topics[topic] = (seen + 1) if seen is not None else 0
        q = dict(pre=hab.pre, topics=q_topics)

        mhab = getattr(hab, "mhab", None)         # GroupHab: query via the member hab
        querier = mhab if mhab is not None else hab
        msg = querier.query(pre=hab.pre, src=eid, route="mbx", query=q)
        httping.createCESRRequest(msg, client, dest=eid)

        while client.requests:
            yield tock

        created = helping.nowUTC()
        while True:
            if helping.nowUTC() - created > datetime.timedelta(seconds=30):
                break
            while client.events:
                evt = client.events.popleft()
                if "retry" in evt:
                    retry = evt["retry"]
                if "id" not in evt or "data" not in evt or "name" not in evt:
                    logger.error(f"bad mailbox event: {evt}")
                    continue
                idx, data, tpc = evt["id"], evt["data"], evt["name"]
                if idx == "" or not data or not tpc:
                    logger.error(f"bad mailbox event: {evt}")
                    continue
                on_message(tpc, data.encode("utf-8") if isinstance(data, str) else data)
                cursor_store.set(eid, tpc, int(idx))
                yield tock
            yield 0.25
        yield retry / 1000
```
(Note: `idx == ""` not `not idx` — index 0 is valid. Imports trimmed of unused ones is fine; keep `agenting`, `httping`, `kering`, `helping`, `datetime`, `logger`.)

- [ ] **Step 4: Run it to verify it passes.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/test_standard_strategy.py -q 2>&1 | tail -10`
Expected: PASS — `on_message` received `("/credential", b"AAAA-cesr")`, cursor `("Embx","/credential")==0`.

- [ ] **Step 5: Commit.**

```bash
cd ~/code/keri-serverless-mailbox && git add -A
git commit -m "feat(standard): SSE fetch strategy (port of Poller.eventDo, parse removed)

run_standard SSE-polls a mailbox EID and delivers raw CESR via on_message + advances the
CursorStore. Host parses (Locksmith via its director parser; standalone via psr.parse).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `MailboxClient` + `MailboxClientDoer` (resolve + discover + mount)

**Files:**
- Create: `~/code/keri-serverless-mailbox/src/keri_serverless_mailbox/client.py`
- Test: `~/code/keri-serverless-mailbox/tests/test_client.py`

**Interfaces:**
- Consumes: `agenting.mailbox` (resolve); `discover_strategy` (Task 2); `Strategy.run` (Tasks 2-3).
- Produces:
  - `MailboxClient(hab, *, topics, on_message, cursor_store, retry_ms=1000)` with `.resolve() -> str|None` (`agenting.mailbox(hab, hab.pre)`) and `.strategy_for(eid) -> Strategy` (`discover_strategy(hab, eid)`).
  - `MailboxClientDoer(client)` — an `hio` `doing.DoDoer` that, on run, resolves the EID, selects the strategy, and runs `strategy.run(...)`; no-op (logs) if the EID resolves to `None`.

- [ ] **Step 1: Write the failing test.**
```python
from types import SimpleNamespace
from keri_serverless_mailbox import MailboxClient, StandardStrategy, client as client_mod


def test_client_resolves_and_selects_strategy(monkeypatch):
    monkeypatch.setattr(client_mod.agenting, "mailbox", lambda hab, cid: "Embx")
    hab = SimpleNamespace(pre="Edoi", fetchUrl=lambda eid, scheme="": "")   # no wss -> Standard
    mc = MailboxClient(hab, topics=["/credential"], on_message=lambda t, r: None,
                       cursor_store=SimpleNamespace(get=lambda e, t: None, set=lambda e, t, i: None))
    assert mc.resolve() == "Embx"
    assert isinstance(mc.strategy_for("Embx"), StandardStrategy)


def test_client_doer_noop_when_no_mailbox(monkeypatch):
    monkeypatch.setattr(client_mod.agenting, "mailbox", lambda hab, cid: None)
    hab = SimpleNamespace(pre="Edoi", fetchUrl=lambda eid, scheme="": "")
    mc = MailboxClient(hab, topics=[], on_message=lambda t, r: None,
                       cursor_store=SimpleNamespace(get=lambda e, t: None, set=lambda e, t, i: None))
    assert mc.resolve() is None      # no crash; the doer will simply not poll
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/test_client.py -q 2>&1 | tail -12`
Expected: FAIL — `MailboxClient` not defined.

- [ ] **Step 3: Implement `client.py`.**
```python
"""MailboxClient: resolve the mailbox (agenting.mailbox), discover its capability, run the
selected strategy. MailboxClientDoer mounts it under a host hio Doist."""
from __future__ import annotations

from hio.base import doing
from keri.app import agenting
from keri import help

from .strategy import discover_strategy

logger = help.ogler.getLogger(__name__)


class MailboxClient:
    def __init__(self, hab, *, topics, on_message, cursor_store, retry_ms=1000):
        self.hab = hab
        self.topics = list(topics)
        self.on_message = on_message
        self.cursor_store = cursor_store
        self.retry_ms = retry_ms

    def resolve(self):
        """The mailbox EID for this AID: its mailbox end-role, else a witness, else None."""
        return agenting.mailbox(self.hab, self.hab.pre)

    def strategy_for(self, eid):
        return discover_strategy(self.hab, eid)


class MailboxClientDoer(doing.DoDoer):
    """Mounts a MailboxClient: resolves the EID, selects the strategy, runs it. If no mailbox
    resolves, it logs and idles (does not crash)."""
    def __init__(self, client: MailboxClient, **kwa):
        self.client = client
        super().__init__(doers=[doing.doify(self.runDo)], **kwa)

    def runDo(self, tymth=None, tock=0.0, **kwa):
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)
        c = self.client
        eid = c.resolve()
        if eid is None:
            logger.info(f"no mailbox resolved for {c.hab.pre}; not polling")
            return
        strategy = c.strategy_for(eid)
        yield from strategy.run(hab=c.hab, eid=eid, topics=c.topics,
                                on_message=c.on_message, cursor_store=c.cursor_store,
                                retry_ms=c.retry_ms)
```

- [ ] **Step 4: Run it to verify it passes.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/ -q 2>&1 | tail -10`
Expected: PASS (all package tests: discovery, standard, client).

- [ ] **Step 5: Commit.**

```bash
cd ~/code/keri-serverless-mailbox && git add -A
git commit -m "feat(client): MailboxClient + hio MailboxClientDoer (resolve, discover, run)

Resolves the mailbox via agenting.mailbox, selects the strategy by KEL-advertised
capability, runs it under the host Doist; idles cleanly when no mailbox resolves.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: locksmith — `add_poller` dedup-merge guard + `seed_kel_mailboxes` negative tests

**Files:**
- Modify: `~/code/locksmith/src/locksmith/core/indirecting.py:154-175` (`add_poller`)
- Test: `~/code/locksmith/tests/test_mailbox_poller_topics.py` (add dedup case), `~/code/locksmith/tests/test_mailbox_kel_seed.py` (add negative/idempotency cases)

**Interfaces:**
- Consumes: existing `MailboxDirector.add_poller(hab, mailbox, extra_topics=None)`, `self.pollers`.
- Produces: `add_poller` is idempotent per `(hab.pre, mailbox)` — a repeat call MERGES `extra_topics` into the existing poller's `topics` instead of appending a second poller.

- [ ] **Step 1: Write the failing tests.**

Add to `~/code/locksmith/tests/test_mailbox_poller_topics.py`:
```python
def test_add_poller_is_idempotent_and_merges_topics():
    hby = _hby()
    try:
        hab = hby.makeHab(name="svc")
        mbd = indirecting.MailboxDirector(hby=hby, topics=list(BASE_TOPICS))
        mbd.add_poller(hab=hab, mailbox="BWan")                       # standard topics
        mbd.add_poller(hab=hab, mailbox="BWan", extra_topics=["insurance"])  # SAME (hab,mbx)
        same = [p for p in mbd.pollers if p.hab.pre == hab.pre and p.mailbox == "BWan"]
        assert len(same) == 1                       # ONE poller, not two
        assert "insurance" in same[0].topics        # extra topic merged in
        assert all(t in same[0].topics for t in BASE_TOPICS)
    finally:
        hby.close()
```
Add to `~/code/locksmith/tests/test_mailbox_kel_seed.py` (mirror the existing test's vault setup; reuse its imports + `_NoTurret` + monkeypatches):
```python
def test_seed_kel_mailboxes_skips_when_no_mailbox_resolves(monkeypatch, tmp_path):
    from keri.app import agenting
    # ... build the headless vault exactly as test_seed_kel_mailboxes_pins_designated_mailbox does ...
    # then, with a hab that has NO mailbox role and NO witnesses:
    monkeypatch.setattr(agenting, "mailbox", lambda hab, cid: None)
    before = len(list(vault.db.mbx.getTopItemIter()))
    vault.seed_kel_mailboxes()
    after = len(list(vault.db.mbx.getTopItemIter()))
    assert after == before                       # None -> nothing pinned
    # ... close vault/rgy/hby in finally ...


def test_seed_kel_mailboxes_leaves_explicit_designation_untouched(monkeypatch, tmp_path):
    from keri.app import agenting
    from locksmith.db.basing import MailboxListener
    # ... build the headless vault; make doi; pin an EXPLICIT db.mbx entry the user "designated":
    vault.db.mbx.pin(keys=("Embx",), val=MailboxListener(cid=doi.pre, eid="Embx", name="my-mailbox"))
    monkeypatch.setattr(agenting, "mailbox", lambda hab, cid: "Embx")   # resolver returns same EID
    vault.seed_kel_mailboxes()
    kept = vault.db.mbx.get(keys=("Embx",))
    assert kept.name == "my-mailbox"             # explicit designation NOT clobbered
    # ... close in finally ...
```
(The implementer fills the vault-construction boilerplate by copying the existing `test_seed_kel_mailboxes_pins_designated_mailbox` setup.)

- [ ] **Step 2: Run them to verify they fail.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/test_mailbox_poller_topics.py tests/test_mailbox_kel_seed.py -q --import-mode=importlib 2>&1 | tail -15`
Expected: the dedup test FAILS (`len(same) == 2` — current `add_poller` appends blindly); the negative tests PASS or FAIL depending — the skip-when-None and leave-explicit tests should already pass IF `seed_kel_mailboxes` is correct (they verify existing behavior). If `leaves_explicit_designation` fails, that's a real bug to note. (The dedup test is the new-behavior driver.)

- [ ] **Step 3: Add the dedup-merge guard to `add_poller`.**

In `~/code/locksmith/src/locksmith/core/indirecting.py`, replace the body of `add_poller` (lines 172-175, after the docstring) with:
```python
        extras = list(extra_topics or [])
        for poller in self.pollers:                          # idempotent per (hab.pre, mailbox)
            if poller.hab.pre == hab.pre and poller.mailbox == mailbox:
                for t in extras:                             # merge new topics into the existing poller
                    if t not in poller.topics:
                        poller.topics.append(t)
                return
        topics = self.topics + extras
        poller = Poller(hab=hab, topics=topics, mailbox=mailbox)
        self.pollers.append(poller)
        self.extend([poller])
```

- [ ] **Step 4: Run them to verify they pass.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/test_mailbox_poller_topics.py tests/test_mailbox_kel_seed.py -q --import-mode=importlib 2>&1 | tail -10`
Expected: PASS — one poller for repeat `(hab, mailbox)` with merged topics; existing topic tests still green; the negative/idempotency seed tests green.

- [ ] **Step 5: Commit (locksmith branch — create it first).**

```bash
cd ~/code/locksmith && git checkout -b feat/mailbox-client-phase2 development
git add src/locksmith/core/indirecting.py tests/test_mailbox_poller_topics.py tests/test_mailbox_kel_seed.py
git commit -m "fix(mailbox): make add_poller idempotent per (hab,mailbox); seed negative tests

add_poller now merges extra_topics into an existing poller instead of appending a second
one for the same (hab.pre, mailbox) — kills the Phase-1 double-poll at the source. Adds
seed_kel_mailboxes negative/idempotency tests (None -> no pin; explicit designation kept).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: locksmith — mount `MailboxClient`, retire the `Poller` poll-loop

**Files:**
- Create: `~/code/locksmith/src/locksmith/core/mailbox_cursor.py`
- Modify: `~/code/locksmith/src/locksmith/core/indirecting.py` (`add_poller` builds a `MailboxClientDoer`; retire `Poller.eventDo`), `~/code/locksmith/pyproject.toml` (dep)
- Test: `~/code/locksmith/tests/test_mailbox_client_integration.py` (create)

**Interfaces:**
- Consumes: `keri_serverless_mailbox.MailboxClient`, `MailboxClientDoer`; `CursorStore`.
- Produces: `DbTopsCursorStore(db, pre)` (CursorStore over `db.tops[(pre, eid)].topics`); `add_poller` mounts a `MailboxClientDoer` whose `on_message` feeds `self.msgs` (the director's existing parse pipeline) — so `msgDo`/`escrowDo` are unchanged.

- [ ] **Step 1: Write the failing integration test.**

Create `~/code/locksmith/tests/test_mailbox_client_integration.py`:
```python
"""The MailboxDirector mounts a keri-serverless-mailbox MailboxClient whose on_message feeds
the director's existing parse pipeline (self.msgs -> msgDo -> parser). Verifies wiring, not
live SSE: a fake delivered message lands in self.msgs as raw bytes."""
from keri.app import habbing
from keri.core import signing
from locksmith.core import indirecting
from locksmith.core.mailbox_cursor import DbTopsCursorStore

BASE_TOPICS = ["/receipt", "/credential", "/reply"]


def test_director_mounts_client_and_on_message_feeds_msgs():
    hby = habbing.Habery(name="mbxclient", temp=True,
                         salt=signing.Salter(raw=b'0123456789abcdef').qb64)
    try:
        hab = hby.makeHab(name="svc")
        mbd = indirecting.MailboxDirector(hby=hby, topics=list(BASE_TOPICS))
        mbd.add_poller(hab=hab, mailbox="BWan", extra_topics=["insurance"])
        client_doer = mbd.pollers[-1]
        # The mounted doer is the package client doer (not the retired Poller).
        assert client_doer.__class__.__name__ == "MailboxClientDoer"
        # Its on_message feeds the director's msgs deque as raw bytes.
        client_doer.client.on_message("/credential", b"AAAA-cesr")
        assert b"AAAA-cesr" in list(mbd.msgs)
    finally:
        hby.close()


def test_db_tops_cursor_store_round_trips():
    hby = habbing.Habery(name="curs", temp=True,
                         salt=signing.Salter(raw=b'0123456789abcdef').qb64)
    try:
        hab = hby.makeHab(name="svc")
        cs = DbTopsCursorStore(hby.db, hab.pre)
        assert cs.get("BWan", "/credential") is None
        cs.set("BWan", "/credential", 3)
        assert cs.get("BWan", "/credential") == 3
    finally:
        hby.close()
```
(`mbd.msgs`: the director must expose the deque the client feeds — see Step 3; today `Poller` owned `msgs` and `processPollIter` drained pollers' `.msgs`. The new model gives the director a single `self.msgs` deque that `on_message` appends to and `processPollIter`/`msgDo` drains.)

- [ ] **Step 2: Run it to verify it fails.**

Run: `~/code/locksmith/.venv/bin/python -m pytest tests/test_mailbox_client_integration.py -q --import-mode=importlib 2>&1 | tail -15`
Expected: FAIL — `mailbox_cursor` module / `DbTopsCursorStore` missing; `add_poller` still builds a `Poller`.

- [ ] **Step 3: Implement the cursor adapter + rewire `add_poller`.**

Create `~/code/locksmith/src/locksmith/core/mailbox_cursor.py`:
```python
"""CursorStore adapter over Locksmith's db.tops (TopicsRecord keyed by (pre, eid))."""
from __future__ import annotations
from locksmith.db import basing


class DbTopsCursorStore:
    def __init__(self, db, pre):
        self.db = db
        self.pre = pre

    def get(self, eid, topic):
        rec = self.db.tops.get((self.pre, eid))
        if rec is None or topic not in rec.topics:
            return None
        return rec.topics[topic]

    def set(self, eid, topic, idx):
        rec = self.db.tops.get((self.pre, eid)) or basing.TopicsRecord(topics=dict())
        rec.topics[topic] = int(idx)
        self.db.tops.pin((self.pre, eid), rec)
```
In `~/code/locksmith/src/locksmith/core/indirecting.py`:
- Give `MailboxDirector` a single `self.msgs = decking.Deck()` in `__init__` (alongside `self.pollers`).
- Replace `add_poller`'s poller construction (the dedup guard from Task 5 stays; only the *object created* changes) so that, instead of `Poller(...)`, it builds:
```python
        from keri_serverless_mailbox import MailboxClient, MailboxClientDoer
        from locksmith.core.mailbox_cursor import DbTopsCursorStore
        topics = self.topics + extras
        client = MailboxClient(hab, topics=topics,
                               on_message=lambda topic, raw: self.msgs.append(raw),
                               cursor_store=DbTopsCursorStore(self.hby.db, hab.pre))
        doer = MailboxClientDoer(client)
        doer.hab = hab           # so the dedup guard's poller.hab.pre / poller.mailbox checks work
        doer.mailbox = mailbox
        doer.topics = topics     # the dedup guard merges into this list
        self.pollers.append(doer)
        self.extend([doer])
```
  (The dedup guard from Task 5 compares `poller.hab.pre`/`poller.mailbox`/`poller.topics`; the `MailboxClientDoer` is given those attributes so the guard is type-agnostic.)
- Update `processPollIter` to drain `self.msgs` directly (it currently drains each `poller.msgs`):
```python
    def processPollIter(self):
        while self.msgs:
            yield self.msgs.popleft()
```
- Delete the `Poller` class (lines 290-406) — its SSE loop now lives in the package's `run_standard`. Leave `MailboxDirector`'s parser/`msgDo`/`escrowDo` untouched.

Add to `~/code/locksmith/pyproject.toml` dependencies: `keri-serverless-mailbox` (editable/local for dev: ensure it is installed in the venv via Task 2's `pip install -e`).

- [ ] **Step 4: Run it to verify it passes + no regression.**

Run:
```bash
~/code/locksmith/.venv/bin/python -m pytest tests/test_mailbox_client_integration.py tests/test_mailbox_poller_topics.py tests/test_mailbox_kel_seed.py -q --import-mode=importlib 2>&1 | tail -12
```
Expected: PASS — director mounts `MailboxClientDoer`; `on_message` feeds `self.msgs`; cursor adapter round-trips; dedup + seed tests still green.

- [ ] **Step 5: Cross-repo integration check (the Phase-2 acceptance).**

Confirm the hermetic in-vault gate still passes through the new client wiring (it feeds `vault.exc` directly, but the director construction must not break vault startup):
```bash
cd ~/code/locksmith-micro-app-designer && bash tests/integration/microapp_in_vault_e2e.sh 2>&1 | tail -3
```
Expected: `PASS: micro-app Service-AID issued a carrier_license hosted by the real vault`.

- [ ] **Step 6: Commit.**

```bash
cd ~/code/locksmith   # on feat/mailbox-client-phase2
git add src/locksmith/core/indirecting.py src/locksmith/core/mailbox_cursor.py tests/test_mailbox_client_integration.py pyproject.toml
git commit -m "refactor(mailbox): mount keri-serverless-mailbox MailboxClient; retire Poller

The director now mounts the package's MailboxClient (resolve+discover+strategy) instead of
the forked SSE Poller; on_message feeds the director's existing msgs->parser pipeline, so
msgDo/escrowDo + db.tops cursors are preserved (via DbTopsCursorStore). Standard SSE path
unchanged in behavior; serverless selection routes to the Phase-3 stub.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Known limitations / Phase-3 boundary (intentional)

- **`ServerlessStrategy` is a stub** — a `wss`-advertising mailbox selects it and raises `NotImplementedError("Phase 3: WS notify-and-fetch")`. No federation/serverless mailbox advertises `wss` yet (no server publish until Phase 3), so production selection stays `StandardStrategy`. Federation *retrieval* remains deferred to Phase 3 (Phase 1 proved the held-SSE doesn't serve a standard Poller).
- **No live serverless retrieval test** — Phase 2 acceptance is against a *standard* (non-serverless) mailbox + package unit tests with fakes. End-to-end serverless retrieval is Phase 3's gate.

## Publishing

When Phase 2 is complete + reviewed, publish the `keri-serverless-mailbox` repo **public on
GitHub under the `usurance` gh auth** (e.g. `gh repo create usurance/keri-serverless-mailbox
--public --source ~/code/keri-serverless-mailbox --push`, using the `usurance` account). It
builds on stock keripy only, so it stands alone as a reusable KERI-ecosystem client. Publish
only after the user confirms the package is ready (don't push during the build).

## Self-Review

- **Spec coverage:** §4.2 `wss` client-read → Task 1; §4.3 package (MailboxClient/CursorStore/Strategy/StandardStrategy/discovery/hio adapter) → Tasks 2-4; §4.4 Locksmith integration (retire Poller, keep msgDo/escrowDo + db.tops cursors) → Task 6; the 2 review first-items → Task 5; §6 Phase-2 acceptance (package unit tests + standard-mailbox retrieval + importlib) → Tasks 2-4 + 6 Steps 4-5. ServerlessStrategy correctly deferred (stub).
- **Placeholder scan:** none — each step has concrete code/commands. The two spots that say "copy the existing setup" (Task 5 negative tests' vault boilerplate) point at a named existing test to clone, not a vague TODO.
- **Type consistency:** `on_message(topic: str, raw: bytes)`, `CursorStore.get/set(eid, topic[, idx])`, `agenting.mailbox(hab, cid)`, `Strategy.run(*, hab, eid, topics, on_message, cursor_store, retry_ms)`, `discover_strategy(hab, eid)` — used identically across Tasks 2-6. `MailboxClientDoer` given `.hab/.mailbox/.topics` so Task 5's dedup guard is type-agnostic across `Poller`→`MailboxClientDoer`.
