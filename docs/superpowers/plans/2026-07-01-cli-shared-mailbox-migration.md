# CLI → Shared Mailbox Library Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the concierge-api CLI Service-AID host's mailbox retrieval onto the shared `keri-serverless-mailbox` `MailboxClient` (WS notify-and-fetch), promoting `DbTopsCursorStore` into the library so the CLI and Locksmith share one client — fixing the "0 messages" frontier bug and unblocking the Stage-2 grant flow.

**Architecture:** Three components across three repos. (1) The durable cursor store `DbTopsCursorStore` moves from Locksmith into the library (it needs only `keri.db.basing`). (2) Locksmith re-exports it from the library so its import path stays stable. (3) concierge-api replaces its standalone keripy `MailboxDirector` — whose auto-created SSE `/mbx` pollers pull 0 from a serverless WS mailbox and hold a dead connection — with a tiny `MailboxDirector` subclass that reuses keripy's Parser/Kevery/Tevery machinery (routing drained exns to `hby.exc`) but suppresses SSE-poller creation, fed by the library `MailboxClient` over WebSocket.

**Tech Stack:** Python 3.13/3.14, keripy (fork), hio, `keri-serverless-mailbox` (editable in Locksmith's `.venv`), pytest.

## Refinement vs. the approved spec (read before Task 3)

The approved spec (`docs/superpowers/specs/2026-07-01-cli-shared-mailbox-migration-design.md`, Component 3) described the concierge mount as "delete the `MailboxDirector` block and **hand-roll a `parsing.Parser`** configured with the DOI's `kvy`/`tvy`/`vry` + `exc`." Reconnaissance against live source refined the *mechanism* (same net effect, less code, lower risk):

- keripy's `MailboxDirector.__init__` (`keri/app/indirecting.py:557-587`) already builds `rvy`/`kvy`/`tvy` from `hby` and the `verifier`, wires them into a `parsing.Parser(..., version=Vrsn_1_0)`, and drives it via a tested `msgDo` doer that routes exns to `exc`. Hand-rolling that plumbing in concierge would re-derive (and risk mis-wiring) `Kevery`/`Tevery`/`Revery` `lax`/`local`/`registerReplyRoutes` flags.
- The **actual** frontier bug is not just "no poller" — it is that keripy's `MailboxDirector.addPollers` (`indirecting.py:631-651`) *unconditionally* spawns an SSE `Poller` for any mailbox end-role, and a serverless (WS) mailbox does not serve the SSE `/mbx` long-poll, so that poller pulls 0 and holds a dead connection (documented: "why `kli mailbox debug` hangs").

So Task 3 uses a **4-line `MailboxDirector` subclass that no-ops `addPollers`** (reusing all of keripy's tested Parser machinery) rather than a hand-rolled parser. This is a "small local glue" that "mirrors Locksmith's director internals," exactly as the spec's own Component-3 prose also allows. It keeps concierge dependent on `keri` only (which it already is) — **no `locksmith` dependency**, honoring the spec's Locksmith-free constraint. Net behavior is identical to the spec's intent; the difference is implementation shape.

---

## Global Constraints

- **`keri-serverless-mailbox` stays Locksmith-free.** `DbTopsCursorStore` may import only stock keripy (`keri.db.basing`). No `locksmith` import in the library, ever.
- **concierge-api stays Locksmith-free.** It gains a dependency on `keri-serverless-mailbox` only (never `locksmith`). Its `pyproject.toml` `dependencies` list is currently `[]`.
- **Test runner (all three repos):** run with Locksmith's interpreter `/Users/seriouscoderone/code/locksmith/.venv/bin/python` — it is the only venv with `keri` + its binary deps installed AND `keri-serverless-mailbox` editable-installed (pointing at `/Users/seriouscoderone/code/keri-serverless-mailbox`). Each repo's own `pyproject.toml` `[tool.pytest.ini_options] pythonpath` layers in its source dirs.
- **Locksmith tests only:** always pass `--import-mode=importlib` (dodges the `tests/packaging` shadow bug). The library and concierge do NOT need it.
- **Because the library is editable-installed**, Task 1's new export is importable in Locksmith's venv immediately after its source is written — no reinstall needed for Tasks 2 and 3.
- **Branches** (commit per repo; do NOT push — the library push to usuranceai and any live run are separately user-gated):
  - Library `keri-serverless-mailbox`: `feat/promote-cursor-store` off `main`.
  - Locksmith: `feat/cursor-store-from-lib` off `development` (ALREADY EXISTS at `246f03d`, carries the spec — do not recreate).
  - concierge-api: `feat/mailbox-shared-client` off `main`.
- **Runtime prerequisite (not code in this plan):** the DOI AID must have a `mailbox` end-role designated (e.g. `mailbox.keri.host`) and its KEL published to the mailbox (the already-shipped KEL-registration fix) so `agenting.mailbox(hab, hab.pre)` resolves. This plan's exit-guard errors clearly when it is absent.
- **Preserve behavior exactly.** `DbTopsCursorStore` moves byte-for-byte; the hermetic `tests/integration/test_grant_license_e2e.py` must stay green (it bypasses this seam).

---

### Task 1: Promote `DbTopsCursorStore` into the library

**Repo:** `/Users/seriouscoderone/code/keri-serverless-mailbox` — branch `feat/promote-cursor-store` off `main`.

**Files:**
- Create: `src/keri_serverless_mailbox/cursor_store.py`
- Modify: `src/keri_serverless_mailbox/__init__.py`
- Test: `tests/test_cursor_store.py`

**Interfaces:**
- Consumes: stock keripy only — `keri.db.basing` (`db.tops`, a `TopicsRecord` subdb keyed by `(pre, eid)`), `keri.app.habbing.openHby` (test only).
- Produces: `keri_serverless_mailbox.DbTopsCursorStore(db, pre)` implementing the `CursorStore` protocol — `get(eid, topic) -> int | None`, `set(eid, topic, idx) -> None`. Later tasks import it as `from keri_serverless_mailbox import DbTopsCursorStore`.

- [ ] **Step 0: Create the branch**

```bash
cd /Users/seriouscoderone/code/keri-serverless-mailbox
git checkout main && git checkout -b feat/promote-cursor-store
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_cursor_store.py`:

```python
"""Unit tests for the promoted DbTopsCursorStore (durable per-(pre, eid, topic) cursor)."""
from keri.app import habbing

from keri_serverless_mailbox import DbTopsCursorStore


def test_roundtrip_per_eid_topic():
    with habbing.openHby(name="cst", temp=True) as hby:
        store = DbTopsCursorStore(hby.db, "Epre1")
        assert store.get("Eeid1", "/credential") is None      # unseen -> None
        store.set("Eeid1", "/credential", 5)
        assert store.get("Eeid1", "/credential") == 5          # round-trips


def test_eids_and_topics_are_isolated():
    with habbing.openHby(name="cst2", temp=True) as hby:
        store = DbTopsCursorStore(hby.db, "Epre1")
        store.set("Eeid1", "/credential", 5)
        store.set("Eeid1", "/receipt", 9)
        store.set("Eeid2", "/credential", 2)
        assert store.get("Eeid1", "/credential") == 5
        assert store.get("Eeid1", "/receipt") == 9             # sibling topic unaffected
        assert store.get("Eeid2", "/credential") == 2          # sibling eid unaffected
        assert store.get("Eeid1", "/reply") is None            # untouched topic -> None


def test_set_overwrites_same_key():
    with habbing.openHby(name="cst3", temp=True) as hby:
        store = DbTopsCursorStore(hby.db, "Epre1")
        store.set("Eeid1", "/credential", 5)
        store.set("Eeid1", "/credential", 12)
        assert store.get("Eeid1", "/credential") == 12
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/seriouscoderone/code/keri-serverless-mailbox
/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_cursor_store.py -q
```
Expected: FAIL — `ImportError: cannot import name 'DbTopsCursorStore' from 'keri_serverless_mailbox'`.

- [ ] **Step 3: Create the implementation**

Create `src/keri_serverless_mailbox/cursor_store.py` (byte-for-byte the behavior of Locksmith's current class; only `keri.db.basing` imported):

```python
"""Durable CursorStore over a keripy Baser's `tops` subdb (TopicsRecord keyed by (pre, eid)).

Persists the last-seen mailbox index per (pre, eid, topic). Depends only on stock
keripy (keri.db.basing) so the concierge-api CLI host and the Locksmith wallet share
one implementation. Implements the CursorStore protocol: get/set by (eid, topic).
"""
from __future__ import annotations

from keri.db import basing


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

- [ ] **Step 4: Export it from the package**

Modify `src/keri_serverless_mailbox/__init__.py`. Add the import line and the `__all__` entry:

```python
from .cursor import CursorStore
from .cursor_store import DbTopsCursorStore
from .strategy import Strategy, ServerlessStrategy, StandardStrategy, discover_strategy
from .client import MailboxClient, MailboxClientDoer
from . import serverless, fetch, standard

__all__ = ["CursorStore", "DbTopsCursorStore", "Strategy", "ServerlessStrategy",
           "StandardStrategy", "discover_strategy", "MailboxClient",
           "MailboxClientDoer", "serverless", "fetch", "standard"]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /Users/seriouscoderone/code/keri-serverless-mailbox
/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_cursor_store.py -q
```
Expected: PASS (3 passed).

- [ ] **Step 6: Run the full library suite (no regressions)**

```bash
cd /Users/seriouscoderone/code/keri-serverless-mailbox
/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests -q
```
Expected: all previously-passing tests still pass (the 20 serverless/fetch/client tests + the new 3).

- [ ] **Step 7: Commit**

```bash
cd /Users/seriouscoderone/code/keri-serverless-mailbox
git add src/keri_serverless_mailbox/cursor_store.py src/keri_serverless_mailbox/__init__.py tests/test_cursor_store.py
git commit -m "feat(cursor): promote DbTopsCursorStore into the library for CLI+wallet sharing"
```

---

### Task 2: Locksmith re-exports `DbTopsCursorStore` from the library

**Repo:** `/Users/seriouscoderone/code/locksmith` — branch `feat/cursor-store-from-lib` (already exists at `246f03d`).

**Files:**
- Modify: `src/locksmith/core/mailbox_cursor.py` (replace the local class with a re-export)
- Test: `tests/test_mailbox_cursor_reexport.py` (create)

**Interfaces:**
- Consumes: `keri_serverless_mailbox.DbTopsCursorStore` (Task 1). Importable now because the library is editable-installed in Locksmith's `.venv`.
- Produces: the historical import path `locksmith.core.mailbox_cursor.DbTopsCursorStore` stays valid and resolves to the *same object* as the library class. Existing importers unchanged: `src/locksmith/core/indirecting.py:173` and `tests/test_mailbox_client_integration.py:7`.

- [ ] **Step 0: Confirm the branch**

```bash
cd /Users/seriouscoderone/code/locksmith
git checkout feat/cursor-store-from-lib
git log --oneline -1   # expect 246f03d docs(mailbox): design spec ...
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_mailbox_cursor_reexport.py`:

```python
"""The Locksmith mailbox_cursor path must re-export the library's DbTopsCursorStore
(same object), so existing importers keep working after the promotion."""


def test_reexports_the_library_class():
    from locksmith.core.mailbox_cursor import DbTopsCursorStore as Local
    from keri_serverless_mailbox import DbTopsCursorStore as Lib
    assert Local is Lib
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/seriouscoderone/code/locksmith
.venv/bin/python -m pytest tests/test_mailbox_cursor_reexport.py -q --import-mode=importlib
```
Expected: FAIL — `assert Local is Lib` fails (the two are currently distinct classes; `Local` is Locksmith's local definition).

- [ ] **Step 3: Replace the local class with a re-export**

Overwrite `src/locksmith/core/mailbox_cursor.py` entirely with:

```python
"""Re-export DbTopsCursorStore from the shared keri-serverless-mailbox library.

The implementation moved to keri_serverless_mailbox.cursor_store so the concierge-api
CLI host and the Locksmith wallet share one class. This module keeps the historical
import path (locksmith.core.mailbox_cursor.DbTopsCursorStore) stable for existing
importers (core/indirecting.py, tests)."""
from keri_serverless_mailbox import DbTopsCursorStore

__all__ = ["DbTopsCursorStore"]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/seriouscoderone/code/locksmith
.venv/bin/python -m pytest tests/test_mailbox_cursor_reexport.py -q --import-mode=importlib
```
Expected: PASS (1 passed).

- [ ] **Step 5: Run the mailbox-client importer suite (re-export doesn't break the runtime mount)**

```bash
cd /Users/seriouscoderone/code/locksmith
.venv/bin/python -m pytest tests/test_mailbox_client_integration.py tests/test_mailbox_cursor_reexport.py -q --import-mode=importlib
```
Expected: PASS — `test_mailbox_client_integration.py` imports `DbTopsCursorStore` from `locksmith.core.mailbox_cursor` (line 7) and must still work through the re-export.

- [ ] **Step 6: Commit**

```bash
cd /Users/seriouscoderone/code/locksmith
git add src/locksmith/core/mailbox_cursor.py tests/test_mailbox_cursor_reexport.py
git commit -m "refactor(mailbox): re-export DbTopsCursorStore from keri-serverless-mailbox"
```

---

### Task 3: concierge-api mounts the shared `MailboxClient`

**Repo:** `/Users/seriouscoderone/code/concierge-api` — branch `feat/mailbox-shared-client` off `main`.

**Files:**
- Modify: `pyproject.toml` (add the library dependency)
- Create: `src/concierge_api_local/mailbox_mount.py` (the mount helper + poller-suppressing director)
- Modify: `src/concierge_api_local/cli/microapp.py:143-148` (replace the standalone `MailboxDirector` block with a call to the helper)
- Test: `tests/test_mailbox_mount.py` (create)

**Interfaces:**
- Consumes: `keri_serverless_mailbox.MailboxClient(hab, *, topics, on_message, cursor_store, retry_ms=1000)`, `keri_serverless_mailbox.MailboxClientDoer(client)`, `keri_serverless_mailbox.DbTopsCursorStore(db, pre)` (Task 1), and stock keripy `keri.app.agenting.mailbox(hab, cid) -> eid | None`, `keri.app.indirecting.MailboxDirector`.
  - The runtime object `rt = ctl.runtime` (a `keri_serviceaid.LocalRuntime`) exposes: `rt.hab` (the bound DOI `Hab`), `rt.hby` (`Habery`), `rt.cred_verifier` (`verifying.Verifier`, has `.reger`), `rt.command_topics` (list of BARE route-derived topic strings, e.g. `["insurance"]`).
- Produces: `concierge_api_local.mailbox_mount.mount_mailbox_client(rt, doers) -> (director, client)` and `concierge_api_local.mailbox_mount.ParserOnlyDirector`.

- [ ] **Step 0: Create the branch**

```bash
cd /Users/seriouscoderone/code/concierge-api
git checkout main && git checkout -b feat/mailbox-shared-client
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_mailbox_mount.py`:

```python
"""Focused tests for the shared-mailbox-client mount (replaces the standalone
MailboxDirector). Covers exactly the delta this migration adds: (a) hard error when
no mailbox end-role is designated, (b) correct topics + cursor store on the mounted
MailboxClient, (c) on_message feeds the director's parser ims, (d) the director
creates NO SSE pollers. The exn->exc parse path is keripy's (reused unchanged) and
is covered by keripy's own MailboxDirector tests, so it is not re-tested here."""
import types

import pytest
from keri.app import habbing
from keri.vdr import credentialing, verifying

from keri_serverless_mailbox import DbTopsCursorStore, MailboxClientDoer
from concierge_api_local import mailbox_mount
from concierge_api_local.mailbox_mount import ParserOnlyDirector, mount_mailbox_client


def _fake_runtime(hby):
    """A LocalRuntime stand-in exposing the attributes the mount reads."""
    hab = hby.makeHab(name="doi")
    rgy = credentialing.Regery(hby=hby, name="doi", temp=True)
    verifier = verifying.Verifier(hby=hby, reger=rgy.reger)
    return types.SimpleNamespace(hab=hab, hby=hby, cred_verifier=verifier,
                                 command_topics=["insurance"])


def test_exits_when_no_mailbox_designated(monkeypatch):
    monkeypatch.setattr(mailbox_mount.agenting, "mailbox", lambda hab, cid: None)
    rt = types.SimpleNamespace(hab=types.SimpleNamespace(pre="Edoi"))
    with pytest.raises(SystemExit) as exc:
        mount_mailbox_client(rt, [])
    assert exc.value.code == 1


def test_mounts_client_with_topics_and_store(monkeypatch):
    monkeypatch.setattr(mailbox_mount.agenting, "mailbox", lambda hab, cid: "Emb1")
    with habbing.openHby(name="mnt", temp=True) as hby:
        rt = _fake_runtime(hby)
        doers = []
        director, client = mount_mailbox_client(rt, doers)

        assert len(doers) == 2
        assert doers[0] is director
        assert isinstance(doers[1], MailboxClientDoer)
        assert doers[1].client is client
        assert client.topics == ["/receipt", "/credential", "/reply", "insurance"]
        assert isinstance(client.cursor_store, DbTopsCursorStore)
        assert client.cursor_store.db is hby.db
        assert client.cursor_store.pre == rt.hab.pre


def test_on_message_feeds_the_directors_parser_ims(monkeypatch):
    monkeypatch.setattr(mailbox_mount.agenting, "mailbox", lambda hab, cid: "Emb1")
    with habbing.openHby(name="mnt2", temp=True) as hby:
        rt = _fake_runtime(hby)
        director, client = mount_mailbox_client(rt, [])
        # the parser reads the SAME buffer on_message writes to
        assert director.parser.ims is director.ims
        client.on_message("/credential", b"abc")
        assert bytes(director.ims) == b"abc"


def test_director_creates_no_sse_pollers(monkeypatch):
    monkeypatch.setattr(mailbox_mount.agenting, "mailbox", lambda hab, cid: "Emb1")
    with habbing.openHby(name="mnt3", temp=True) as hby:
        rt = _fake_runtime(hby)
        director, _ = mount_mailbox_client(rt, [])
        director.addPollers(rt.hab)                 # the method keripy's pollDo calls
        assert director.pollers == []               # no SSE poller spawned
        assert rt.hab.pre in director.prefixes      # but the hab is marked seen
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/seriouscoderone/code/concierge-api
/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_mailbox_mount.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'concierge_api_local.mailbox_mount'`.

- [ ] **Step 3: Create the mount helper**

Create `src/concierge_api_local/mailbox_mount.py`:

```python
"""Mount the shared keri-serverless-mailbox client on a CLI Service-AID host.

Why not keripy's stock MailboxDirector as-is: its addPollers() unconditionally spawns
an SSE `/mbx` Poller for an AID's mailbox end-role. A *serverless* mailbox
(e.g. mailbox.keri.host) speaks WebSocket notify-and-fetch, not SSE long-poll, so that
poller pulls 0 and holds a dead connection (the "frontier bug"). We reuse the director
purely for its Parser/Kevery/Tevery machinery (which routes drained exns to hby.exc via
its msgDo doer) but suppress SSE-poller creation, and drive retrieval with the library
MailboxClient (WS), which feeds the director's .ims via on_message.
"""
from __future__ import annotations

import sys

from keri.app import agenting, indirecting

from keri_serverless_mailbox import DbTopsCursorStore, MailboxClient, MailboxClientDoer

STANDARD_TOPICS = ["/receipt", "/credential", "/reply"]


class ParserOnlyDirector(indirecting.MailboxDirector):
    """A MailboxDirector that builds the full parser/kvy/tvy/exc machinery but creates
    NO internal SSE pollers. Retrieval is done by the injected library MailboxClient
    (WS), which feeds this director's .ims via on_message."""

    def addPollers(self, hab):
        self.prefixes.add(hab.pre)   # mark the hab seen; create no SSE pollers


def mount_mailbox_client(rt, doers):
    """Resolve the runtime AID's mailbox and mount a WS MailboxClient + parser host onto
    `doers`. Exits non-zero with a clear message if the AID has no mailbox end-role.

    rt must expose: .hab (the host Hab), .hby (Habery), .cred_verifier (Verifier),
    .command_topics (bare route-derived topic strings). Returns (director, client).
    """
    eid = agenting.mailbox(rt.hab, rt.hab.pre)
    if eid is None:
        print(f"error: AID {rt.hab.pre} has no mailbox end-role designated; cannot "
              f"retrieve mail. Designate a mailbox (e.g. mailbox.keri.host) first.",
              file=sys.stderr)
        sys.exit(1)

    topics = [*STANDARD_TOPICS, *rt.command_topics]
    director = ParserOnlyDirector(hby=rt.hby, topics=topics,
                                  verifier=rt.cred_verifier, exc=rt.hby.exc)
    client = MailboxClient(rt.hab, topics=topics,
                           on_message=lambda topic, raw: director.ims.extend(raw),
                           cursor_store=DbTopsCursorStore(rt.hby.db, rt.hab.pre))
    doers.append(director)
    doers.append(MailboxClientDoer(client))
    return director, client
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/seriouscoderone/code/concierge-api
/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/test_mailbox_mount.py -q
```
Expected: PASS (4 passed).

- [ ] **Step 5: Rewire `microapp.py` to use the helper**

In `src/concierge_api_local/cli/microapp.py`, replace the standalone-director block. The current block (lines 136-148) is:

```python
        # A Service-AID is not a node — the HOST injects the inbound poller
        # (dependency injection). This standalone dev-host explicitly chooses
        # keripy's generic MailboxDirector; the production host (Locksmith)
        # injects its own wallet poller (vault.mbx) instead. Either feeds
        # hby.exc (where the runtime registered its capture handlers) and polls
        # the runtime's command_topics + the standard receipt/credential/reply
        # topics. The RuntimePumpDoer drains the captured exns into the pipeline.
        from keri.app.indirecting import MailboxDirector  # noqa: PLC0415
        rt = ctl.runtime
        topics = ["/receipt", "/credential", "/reply", *rt.command_topics]
        poller = MailboxDirector(hby=rt.hby, topics=topics,
                                 verifier=rt.cred_verifier, exc=rt.hby.exc)
        vault.doers.append(poller)
```

Replace it with:

```python
        # A Service-AID is not a node — the HOST injects the inbound poller
        # (dependency injection). This dev-host mounts the shared
        # keri-serverless-mailbox client (WebSocket notify-and-fetch), which feeds a
        # parser wired to hby.exc (where the runtime registered its capture handlers)
        # and subscribes to the runtime's command_topics + the standard
        # receipt/credential/reply topics. The RuntimePumpDoer drains the captured
        # exns into the pipeline. (The production host, Locksmith, injects its own
        # wallet poller, vault.mbx, over the same library client.)
        from concierge_api_local.mailbox_mount import mount_mailbox_client  # noqa: PLC0415
        mount_mailbox_client(ctl.runtime, vault.doers)
```

(The `Doist` built at lines ~151-156 from `list(vault.doers)` picks up the appended director + `MailboxClientDoer` unchanged.)

- [ ] **Step 6: Add the library dependency to `pyproject.toml`**

In `/Users/seriouscoderone/code/concierge-api/pyproject.toml`, change the `[project]` dependencies line:

```toml
dependencies = ["keri-serverless-mailbox"]
```

- [ ] **Step 7: Verify the rewired module imports cleanly**

```bash
cd /Users/seriouscoderone/code/concierge-api
/Users/seriouscoderone/code/locksmith/.venv/bin/python -c "import concierge_api_local.cli.microapp; import concierge_api_local.mailbox_mount; print('import OK')"
```
Expected: `import OK` (no ImportError; confirms the microapp edit references the real helper).

- [ ] **Step 8: Confirm the hermetic gate is unaffected**

```bash
cd /Users/seriouscoderone/code/concierge-api
/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests/integration/test_grant_license_e2e.py tests/test_mailbox_mount.py -q
```
Expected: PASS — the e2e gate bypasses the mailbox seam (calls `LocalRuntime` directly with a `FakeDeliverer`) and must stay green; the 4 mount tests pass.

- [ ] **Step 9: Run the full concierge suite (no regressions)**

```bash
cd /Users/seriouscoderone/code/concierge-api
/Users/seriouscoderone/code/locksmith/.venv/bin/python -m pytest tests -q
```
Expected: all previously-passing tests still pass, plus the 4 new mount tests.

- [ ] **Step 10: Commit**

```bash
cd /Users/seriouscoderone/code/concierge-api
git add pyproject.toml src/concierge_api_local/mailbox_mount.py src/concierge_api_local/cli/microapp.py tests/test_mailbox_mount.py
git commit -m "feat(host): mount shared keri-serverless-mailbox client, retire standalone SSE director"
```

---

## Self-Review

**1. Spec coverage** (against `2026-07-01-cli-shared-mailbox-migration-design.md`):
- Component 1 (library `cursor_store.py` + export + unit test) → Task 1. ✓
- Component 2 (Locksmith re-export, stable import path, existing suites green) → Task 2. ✓
- Component 3 (add lib dep, replace lines 143-148, resolve-or-error via `agenting.mailbox`, feed parser routed to `hby.exc`, focused mount test) → Task 3. ✓ Mechanism refined from "hand-roll a Parser" to "subclass the director to no-op SSE pollers" — documented in the "Refinement" section (net behavior identical; less code; keeps concierge Locksmith-free).
- Non-goals honored: no `LocalRuntime` `exc`-injection (mount feeds `rt.hby.exc`, where the standalone host registers handlers); no pipeline/deliverer change; hermetic gate untouched (Task 3 Step 8). ✓
- Global constraints: library imports only `keri.db.basing` (Task 1 Step 3); concierge depends on `keri-serverless-mailbox` only, not `locksmith` (Task 3 Step 6, `mailbox_mount.py` imports only `keri` + the library); `--import-mode=importlib` on Locksmith tests only. ✓

**2. Placeholder scan:** No TBD/TODO/"handle appropriately". Every code step shows complete code; every run step shows the command + expected output. ✓

**3. Type consistency:** `DbTopsCursorStore(db, pre)` with `get(eid, topic)`/`set(eid, topic, idx)` is identical in Task 1 (definition), Task 2 (re-export identity), and Task 3 (`DbTopsCursorStore(rt.hby.db, rt.hab.pre)` + `client.cursor_store.db`/`.pre` assertions). `MailboxClient(hab, *, topics, on_message, cursor_store)` and `MailboxClientDoer(client)` match the library signatures (`client.py:15,33`). `on_message(topic, raw)` matches the library call site (`fetch.py:67`). `agenting.mailbox(hab, cid)` matches `keri/app/agenting.py:967`. `ParserOnlyDirector.addPollers(self, hab)` matches keripy's `indirecting.py:631`. ✓

---

## Execution Handoff

Plan complete. Before executing Task 3, note the **one refinement vs. the approved spec** flagged above (director-subclass instead of hand-rolled parser) — same effect, less code, still Locksmith-free.
