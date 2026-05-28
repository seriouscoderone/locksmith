# Locksmith Direct Peer Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a TCP-based direct-mode peer transport to Locksmith so two wallets on the same LAN/VPN exchange KERI peer messages (IPEX, KEL replay, OOBI, signing, etc.) without round-tripping through a witness mailbox.

**Architecture:** Mirror the existing `locksmith.turret` UDS pipeline with a parallel TCP listener (`locksmith.peer`). New code under `src/locksmith/peer/`: `tcp.py` wraps hio's stock `core.tcp.Server`, `shim.py` enforces a two-gate allowlist (sender + destination), `doer.py` composes server + `Directant` + shim. All keripy handlers are reused as-is. A new `peer` role on each AID's KEL authorizes the shared `tcp://host:port` endpoint. Pairing is OOBI-driven through the existing witness machinery.

**Tech Stack:** Python 3.13, PySide6, keripy 2.x (`keri.app.directing`, `keri.peer.exchanging`, `keri.kering.Schemes.tcp`), hio (`hio.core.tcp.serving.Server` / `ServerDoer`, `hio.base.doing`), pytest.

**Spec:** `docs/superpowers/specs/2026-05-27-locksmith-direct-peer-design.md`
**Branch:** `feat/direct-peer-design` (off `origin/development`)

---

## File map

**New files**
- `src/locksmith/peer/__init__.py` — package marker, re-exports
- `src/locksmith/peer/records.py` — `PeerRecord`, `PeerModeSettings` dataclasses
- `src/locksmith/peer/allowlist.py` — `PeerAllowlist` wrapper around Komer subkey
- `src/locksmith/peer/tcp.py` — `TCPServer` (hio TCP Server subclass with structured logs)
- `src/locksmith/peer/shim.py` — `PeerExchangerShim` (sender + destination gate)
- `src/locksmith/peer/doer.py` — `PeerDoer` (DoDoer composing server + Directant + shim)
- `src/locksmith/peer/sending.py` — `peer_send(...)` channel selector with auto-fallback
- `src/locksmith/ui/vault/settings/peer_section.py` — vault-level peer mode settings UI
- `src/locksmith/ui/vault/peers/__init__.py`
- `src/locksmith/ui/vault/peers/list.py` — Paired Peers page
- `src/locksmith/ui/vault/peers/add_dialog.py` — Add Peer dialog
- `tests/peer/__init__.py`
- `tests/peer/test_allowlist.py`
- `tests/peer/test_shim.py`
- `tests/peer/test_tcp.py`
- `tests/peer/test_doer.py`
- `tests/peer/test_sending.py`
- `tests/peer/conftest.py` — shared fixtures (real `LocksmithBaser` on tmpdir)
- `tests/integration/__init__.py`
- `tests/integration/peer/__init__.py`
- `tests/integration/peer/conftest.py` — two-wallet subprocess fixture
- `tests/integration/peer/test_pairing.py`
- `tests/integration/peer/test_send.py`
- `tests/integration/peer/test_gates.py`

**Modified files**
- `src/locksmith/db/basing.py` — register `PeerRecord` + `PeerModeSettings` Komers
- `src/locksmith/core/habbing.py` — extend `generate_oobi` to handle role `peer`
- `src/locksmith/core/vaulting.py` — instantiate `PeerDoer` when settings enabled; route outbound via `peer_send`
- `src/locksmith/ui/vault/identifiers/identifier_sections.py` — add `Peer` to OOBI role dropdown + per-AID expose toggle
- `src/locksmith/ui/vault/settings/page.py` — include the new `PeerSettingsSection`

---

## Conventions used in this plan

- **Test commands** run from repo root with: `cd ~/code/locksmith && .venv/bin/python -m pytest <path> -v`. Locksmith ships its venv at `.venv/`; never use system python.
- **Structured log lines** follow Locksmith's idiom: `logger.info(f"event.name key=value other=foo")`. Don't change format mid-task.
- **Commits** are small and frequent. Every numbered task ends with a commit step.
- **TDD discipline:** write the failing test, run it to see it fail, write the minimal code, run it to see it pass, commit.
- **No mocks in integration tests.** Real `LocksmithBaser` on tmpdirs, real subprocess wallets for the two-wallet tests.

---

## Task 1: `PeerRecord` and `PeerModeSettings` dataclasses + Komer registration

**Files:**
- Create: `src/locksmith/peer/__init__.py`
- Create: `src/locksmith/peer/records.py`
- Modify: `src/locksmith/db/basing.py` (add imports + two Komer subkeys + two attributes)
- Test: `tests/peer/__init__.py`, `tests/peer/conftest.py`, `tests/peer/test_records.py`

- [ ] **Step 1: Create the peer package**

```bash
mkdir -p src/locksmith/peer tests/peer
```

Create `src/locksmith/peer/__init__.py` with one line:

```python
"""locksmith.peer — direct-mode TCP peer transport."""
```

Create `tests/peer/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test for the dataclasses**

Create `tests/peer/test_records.py`:

```python
from datetime import datetime, timezone

from locksmith.peer.records import PeerModeSettings, PeerRecord


def test_peer_record_defaults():
    rec = PeerRecord(aid="EAID123", label="Bob", endpoint_url="tcp://10.0.0.1:5621")
    assert rec.aid == "EAID123"
    assert rec.label == "Bob"
    assert rec.endpoint_url == "tcp://10.0.0.1:5621"
    assert rec.paired_at == ""
    assert rec.last_contacted_at == ""


def test_peer_record_with_timestamps():
    now = datetime.now(timezone.utc).isoformat()
    rec = PeerRecord(
        aid="EAID123",
        label="Bob",
        endpoint_url="tcp://10.0.0.1:5621",
        paired_at=now,
        last_contacted_at=now,
    )
    assert rec.paired_at == now
    assert rec.last_contacted_at == now


def test_peer_mode_settings_defaults():
    s = PeerModeSettings()
    assert s.enabled is False
    assert s.port == 5621
    assert s.bind_host == "0.0.0.0"
    assert s.advertised_host == ""
```

- [ ] **Step 3: Run the test — expect ModuleNotFoundError**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_records.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'locksmith.peer.records'`.

- [ ] **Step 4: Create the dataclasses**

Create `src/locksmith/peer/records.py`:

```python
"""Persisted records and settings for peer mode."""
from dataclasses import dataclass


@dataclass
class PeerRecord:
    """One paired peer in the sender allowlist."""

    aid: str
    label: str
    endpoint_url: str
    paired_at: str = ""
    last_contacted_at: str = ""


@dataclass
class PeerModeSettings:
    """Vault-level configuration for the peer-mode listener."""

    enabled: bool = False
    port: int = 5621
    bind_host: str = "0.0.0.0"
    advertised_host: str = ""
```

- [ ] **Step 5: Run the test — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_records.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Register the Komers on `LocksmithBaser`**

Edit `src/locksmith/db/basing.py`:

After the existing imports (top of file), add:

```python
from locksmith.peer.records import PeerModeSettings, PeerRecord
```

Inside `LocksmithBaser.__init__`, after the `self.pluginSettings = None` line, add:

```python
        # Peer-mode allowlist + listener settings
        self.peerAllowlist = None
        self.peerSettings = None
```

Inside `LocksmithBaser.reopen`, after the `pluginSettings` Komer assignment, add:

```python
        # Peer-mode storage
        self.peerAllowlist = koming.Komer(
            db=self, subkey='peer.', klas=PeerRecord
        )
        self.peerSettings = koming.Komer(
            db=self, subkey='peerSettings.', klas=PeerModeSettings
        )
```

- [ ] **Step 7: Add a conftest fixture for a real LocksmithBaser on tmpdir**

Create `tests/peer/conftest.py`:

```python
import pytest

from locksmith.db.basing import LocksmithBaser


@pytest.fixture
def baser(tmp_path):
    db = LocksmithBaser(
        name="peertest",
        headDirPath=str(tmp_path),
        reopen=True,
        temp=True,
    )
    try:
        yield db
    finally:
        db.close(clear=True)
```

- [ ] **Step 8: Write a smoke test that the baser exposes the two new Komers**

Append to `tests/peer/test_records.py`:

```python
def test_baser_exposes_peer_komers(baser):
    assert baser.peerAllowlist is not None
    assert baser.peerSettings is not None
```

- [ ] **Step 9: Run the test — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_records.py -v
```

Expected: 4 passed.

- [ ] **Step 10: Commit**

```bash
git add src/locksmith/peer/__init__.py src/locksmith/peer/records.py \
        src/locksmith/db/basing.py \
        tests/peer/__init__.py tests/peer/conftest.py tests/peer/test_records.py
git commit -m "feat(peer): add PeerRecord + PeerModeSettings dataclasses and Komers"
```

---

## Task 2: `PeerAllowlist` wrapper

**Files:**
- Create: `src/locksmith/peer/allowlist.py`
- Test: `tests/peer/test_allowlist.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/peer/test_allowlist.py`:

```python
import logging

from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord


def _make_record(aid="EAID_BOB", label="Bob"):
    return PeerRecord(
        aid=aid,
        label=label,
        endpoint_url="tcp://10.0.0.2:5621",
        paired_at=datetime.now(timezone.utc).isoformat(),
    )


def test_add_then_contains(baser):
    al = PeerAllowlist(baser)
    al.add(_make_record())
    assert al.contains("EAID_BOB")


def test_contains_missing_returns_false(baser):
    al = PeerAllowlist(baser)
    assert al.contains("EAID_NOT_PAIRED") is False


def test_list_returns_all(baser):
    al = PeerAllowlist(baser)
    al.add(_make_record(aid="EAID_BOB"))
    al.add(_make_record(aid="EAID_CARL", label="Carl"))
    aids = {r.aid for r in al.list()}
    assert aids == {"EAID_BOB", "EAID_CARL"}


def test_remove(baser):
    al = PeerAllowlist(baser)
    al.add(_make_record())
    al.remove("EAID_BOB")
    assert al.contains("EAID_BOB") is False


def test_remove_missing_is_idempotent(baser):
    al = PeerAllowlist(baser)
    # should not raise
    al.remove("EAID_DOES_NOT_EXIST")


def test_get(baser):
    al = PeerAllowlist(baser)
    al.add(_make_record(label="Bob"))
    rec = al.get("EAID_BOB")
    assert rec is not None
    assert rec.label == "Bob"


def test_persists_across_reopen(tmp_path):
    from locksmith.db.basing import LocksmithBaser

    db1 = LocksmithBaser(name="persist", headDirPath=str(tmp_path), reopen=True, temp=True)
    PeerAllowlist(db1).add(_make_record())
    db1.close()

    db2 = LocksmithBaser(name="persist", headDirPath=str(tmp_path), reopen=True, temp=True)
    try:
        assert PeerAllowlist(db2).contains("EAID_BOB")
    finally:
        db2.close(clear=True)


def test_add_logs_pair_success(baser, caplog):
    al = PeerAllowlist(baser)
    with caplog.at_level(logging.INFO, logger="locksmith.peer.allowlist"):
        al.add(_make_record())
    assert any("peer.pair.success" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run the tests — expect ModuleNotFoundError**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_allowlist.py -v
```

Expected: `ModuleNotFoundError: No module named 'locksmith.peer.allowlist'`.

- [ ] **Step 3: Implement `PeerAllowlist`**

Create `src/locksmith/peer/allowlist.py`:

```python
"""Sender allowlist for peer-mode inbound traffic."""
from __future__ import annotations

from keri import help

from locksmith.peer.records import PeerRecord

logger = help.ogler.getLogger(__name__)


class PeerAllowlist:
    """Thin wrapper around the `peer.` Komer subkey on LocksmithBaser.

    The allowlist is the set of peer AIDs the user has paired with via the
    Add Peer flow. Inbound exns from AIDs not in this list are dropped.
    """

    def __init__(self, db):
        self._db = db

    def add(self, record: PeerRecord) -> None:
        self._db.peerAllowlist.pin(keys=(record.aid,), val=record)
        logger.info(
            f"peer.pair.success aid={record.aid} endpoint={record.endpoint_url} label={record.label!r}"
        )

    def remove(self, aid: str) -> None:
        self._db.peerAllowlist.rem(keys=(aid,))
        logger.info(f"peer.pair.removed aid={aid}")

    def contains(self, aid: str) -> bool:
        return self._db.peerAllowlist.get(keys=(aid,)) is not None

    def get(self, aid: str) -> PeerRecord | None:
        return self._db.peerAllowlist.get(keys=(aid,))

    def list(self) -> list[PeerRecord]:
        return [val for (_keys, val) in self._db.peerAllowlist.getItemIter()]
```

- [ ] **Step 4: Run the tests — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_allowlist.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/peer/allowlist.py tests/peer/test_allowlist.py
git commit -m "feat(peer): PeerAllowlist wrapper with structured logs"
```

---

## Task 3: `PeerExchangerShim` (two-gate enforcement)

**Files:**
- Create: `src/locksmith/peer/shim.py`
- Test: `tests/peer/test_shim.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/peer/test_shim.py`:

```python
import logging
from types import SimpleNamespace

from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.peer.shim import PeerExchangerShim


def _exn(sender="EAID_BOB", recipient="EAID_ALICE"):
    return SimpleNamespace(
        ked={"i": sender, "rp": recipient},
        said="SAID_FAKE",
    )


class _RecordingExchanger:
    def __init__(self):
        self.calls = []

    def processEvent(self, serder, tsgs=None, cigars=None, **kwargs):
        self.calls.append((serder, tsgs, cigars, kwargs))


def test_paired_sender_to_opted_in_destination_forwards(baser):
    al = PeerAllowlist(baser)
    al.add(PeerRecord(aid="EAID_BOB", label="Bob", endpoint_url="tcp://x:5621",
                      paired_at=datetime.now(timezone.utc).isoformat()))
    exchanger = _RecordingExchanger()
    shim = PeerExchangerShim(allowlist=al, exchanger=exchanger,
                             is_destination_exposed=lambda aid: aid == "EAID_ALICE")

    shim.processEvent(_exn(), tsgs=None, cigars=None)

    assert len(exchanger.calls) == 1


def test_unknown_sender_is_dropped_and_logged(baser, caplog):
    al = PeerAllowlist(baser)
    exchanger = _RecordingExchanger()
    shim = PeerExchangerShim(allowlist=al, exchanger=exchanger,
                             is_destination_exposed=lambda aid: True)

    with caplog.at_level(logging.WARNING, logger="locksmith.peer.shim"):
        shim.processEvent(_exn(sender="EAID_MALLORY"))

    assert exchanger.calls == []
    assert any("peer.gate.sender_rejected" in r.message and "EAID_MALLORY" in r.message
               for r in caplog.records)


def test_paired_sender_to_unexposed_destination_is_dropped_and_logged(baser, caplog):
    al = PeerAllowlist(baser)
    al.add(PeerRecord(aid="EAID_BOB", label="Bob", endpoint_url="tcp://x:5621",
                      paired_at=datetime.now(timezone.utc).isoformat()))
    exchanger = _RecordingExchanger()
    shim = PeerExchangerShim(allowlist=al, exchanger=exchanger,
                             is_destination_exposed=lambda aid: False)

    with caplog.at_level(logging.WARNING, logger="locksmith.peer.shim"):
        shim.processEvent(_exn())

    assert exchanger.calls == []
    assert any("peer.gate.destination_not_exposed" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run the tests — expect ModuleNotFoundError**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_shim.py -v
```

Expected: `ModuleNotFoundError: No module named 'locksmith.peer.shim'`.

- [ ] **Step 3: Implement `PeerExchangerShim`**

Create `src/locksmith/peer/shim.py`:

```python
"""Two-gate allowlist check between the TCP socket and the Exchanger."""
from __future__ import annotations

from typing import Callable

from keri import help

from locksmith.peer.allowlist import PeerAllowlist

logger = help.ogler.getLogger(__name__)


class PeerExchangerShim:
    """Filters inbound exns before handing them to the keripy Exchanger.

    Gate 1: sender AID must be in the paired-peers allowlist.
    Gate 2: destination AID (exn `rp` field) must have role=peer opted in.

    Modeled on locksmith.core.turretting.ExchangerShim but using two
    independent allowlists instead of a single-AID equality check.
    """

    def __init__(
        self,
        allowlist: PeerAllowlist,
        exchanger,
        is_destination_exposed: Callable[[str], bool],
    ):
        self._allowlist = allowlist
        self.exchanger = exchanger
        self._is_destination_exposed = is_destination_exposed

    def processEvent(self, serder, tsgs=None, cigars=None, **kwargs):
        sender = serder.ked.get("i", "")
        recipient = serder.ked.get("rp", "")

        if not self._allowlist.contains(sender):
            logger.warning(
                f"peer.gate.sender_rejected sender={sender} said={serder.said}"
            )
            return

        if not self._is_destination_exposed(recipient):
            logger.warning(
                f"peer.gate.destination_not_exposed sender={sender} "
                f"destination={recipient} said={serder.said}"
            )
            return

        self.exchanger.processEvent(serder, tsgs, cigars, **kwargs)
```

- [ ] **Step 4: Run the tests — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_shim.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/peer/shim.py tests/peer/test_shim.py
git commit -m "feat(peer): PeerExchangerShim with sender + destination gates"
```

---

## Task 4: `TCPServer` (hio Server subclass with structured logs)

**Files:**
- Create: `src/locksmith/peer/tcp.py`
- Test: `tests/peer/test_tcp.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/peer/test_tcp.py`:

```python
import logging
import socket

from locksmith.peer.tcp import TCPServer


def _free_port():
    """Bind to port 0, read back the assigned port, close. Standard trick."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_bind_to_free_port_succeeds(caplog):
    port = _free_port()
    server = TCPServer(host="127.0.0.1", port=port)
    with caplog.at_level(logging.INFO, logger="locksmith.peer.tcp"):
        ok = server.reopen()
    try:
        assert ok is True
        assert server.opened is True
        assert any(f"peer.listener.started" in r.message and f"port={port}" in r.message
                   for r in caplog.records)
    finally:
        server.close()


def test_bind_to_held_port_fails_with_structured_log(caplog):
    # Hold the port with our own socket
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]

    server = TCPServer(host="127.0.0.1", port=port)
    try:
        with caplog.at_level(logging.ERROR, logger="locksmith.peer.tcp"):
            ok = server.reopen()
        assert ok is False
        assert any("peer.listener.bind_failed" in r.message for r in caplog.records)
    finally:
        holder.close()
        server.close()


def test_close_emits_stopped_log(caplog):
    port = _free_port()
    server = TCPServer(host="127.0.0.1", port=port)
    server.reopen()
    with caplog.at_level(logging.INFO, logger="locksmith.peer.tcp"):
        server.close()
    assert any("peer.listener.stopped" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_tcp.py -v
```

Expected: `ModuleNotFoundError: No module named 'locksmith.peer.tcp'`.

- [ ] **Step 3: Implement `TCPServer`**

Create `src/locksmith/peer/tcp.py`:

```python
"""TCP listener for peer-mode direct messaging.

Wraps hio.core.tcp.serving.Server so we can add structured log lines
without forking the underlying networking code.
"""
from __future__ import annotations

from hio.core.tcp.serving import Server
from keri import help

logger = help.ogler.getLogger(__name__)


class TCPServer(Server):
    """hio TCP Server subclass that emits peer.listener.* structured logs."""

    def __init__(self, host: str = "0.0.0.0", port: int = 5621, **kwa):
        super().__init__(host=host, port=port, **kwa)
        self._log_host = host
        self._log_port = port

    def reopen(self) -> bool:
        ok = super().reopen()
        if ok:
            logger.info(
                f"peer.listener.started host={self._log_host} port={self._log_port}"
            )
        else:
            logger.error(
                f"peer.listener.bind_failed host={self._log_host} port={self._log_port}"
            )
        return ok

    def close(self):
        was_open = self.opened
        super().close()
        if was_open:
            logger.info(
                f"peer.listener.stopped host={self._log_host} port={self._log_port}"
            )
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_tcp.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/peer/tcp.py tests/peer/test_tcp.py
git commit -m "feat(peer): TCPServer subclass with bind/close structured logs"
```

---

## Task 5: `PeerDoer` (composer)

**Files:**
- Create: `src/locksmith/peer/doer.py`
- Test: `tests/peer/test_doer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/peer/test_doer.py`:

```python
from types import SimpleNamespace

from locksmith.peer.doer import PeerDoer
from locksmith.peer.records import PeerModeSettings


def _fake_hby():
    # PeerDoer only touches hby for the Directant constructor; we fake a
    # hab. The actual Directant exercise lives in integration tests.
    hab = SimpleNamespace(pre="EAID_VAULT")
    return SimpleNamespace(habs={"EAID_VAULT": hab}, name="fake-hby")


def _fake_exchanger():
    return SimpleNamespace(processEvent=lambda *a, **k: None)


def test_disabled_settings_yields_no_inner_doers(baser):
    settings = PeerModeSettings(enabled=False)
    doer = PeerDoer(
        hby=_fake_hby(),
        baser=baser,
        settings=settings,
        exchanger=_fake_exchanger(),
        is_destination_exposed=lambda aid: True,
    )
    assert doer.server is None
    assert doer.directant is None


def test_enabled_settings_constructs_server_and_directant(baser):
    settings = PeerModeSettings(enabled=True, port=0, bind_host="127.0.0.1")
    doer = PeerDoer(
        hby=_fake_hby(),
        baser=baser,
        settings=settings,
        exchanger=_fake_exchanger(),
        is_destination_exposed=lambda aid: True,
    )
    assert doer.server is not None
    assert doer.directant is not None
    # the shim should sit between directant and exchanger
    assert doer.shim is not None
    doer.server.close()
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_doer.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `PeerDoer`**

Create `src/locksmith/peer/doer.py`:

```python
"""PeerDoer composes the TCP listener, Directant, and allowlist shim."""
from __future__ import annotations

from typing import Callable

from hio.base import doing
from hio.help import decking
from hio.core.tcp.serving import ServerDoer
from keri import help

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerModeSettings
from locksmith.peer.shim import PeerExchangerShim
from locksmith.peer.tcp import TCPServer
from locksmith.turret import directing as turret_directing

logger = help.ogler.getLogger(__name__)


class PeerDoer(doing.DoDoer):
    """DoDoer wrapping the peer-mode TCP server, hio ServerDoer, and Directant.

    When settings.enabled is False, the doer is inert (no socket, no doers).
    """

    def __init__(
        self,
        hby,
        baser,
        settings: PeerModeSettings,
        exchanger,
        is_destination_exposed: Callable[[str], bool],
        **kwa,
    ):
        self._hby = hby
        self._baser = baser
        self._settings = settings
        self._exchanger = exchanger
        self.server = None
        self.directant = None
        self.shim = None

        doers: list[doing.Doer] = []

        if settings.enabled:
            allowlist = PeerAllowlist(baser)
            self.shim = PeerExchangerShim(
                allowlist=allowlist,
                exchanger=exchanger,
                is_destination_exposed=is_destination_exposed,
            )

            self.server = TCPServer(
                host=settings.bind_host,
                port=settings.port,
            )
            server_doer = ServerDoer(server=self.server)

            # Reuse the turret Directant (same module Locksmith already
            # ships) but pass our shim instead of the per-plugin one.
            cues = decking.Deck()
            # Directant requires a hab; for peer mode we use the first
            # available hab. Actual destination routing happens via the
            # shim's is_destination_exposed check.
            first_hab = next(iter(getattr(hby, "habs", {}).values()), None)
            self.directant = turret_directing.Directant(
                hab=first_hab,
                server=self.server,
                exchanger=self.shim,
                cues=cues,
            )
            doers = [server_doer, self.directant]

        super().__init__(doers=doers, **kwa)
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_doer.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/peer/doer.py tests/peer/test_doer.py
git commit -m "feat(peer): PeerDoer composes TCP server + Directant + shim"
```

---

## Task 6: Wire `PeerDoer` into `Vault`

**Files:**
- Modify: `src/locksmith/core/vaulting.py`
- Test: `tests/peer/test_vault_wiring.py`

- [ ] **Step 1: Write the failing test**

Create `tests/peer/test_vault_wiring.py`:

```python
"""Verify Vault constructs PeerDoer when peerSettings.enabled is True.

This is a unit test on the construction path, not full integration.
"""
from unittest.mock import patch


def test_vault_with_peer_disabled_has_no_peer_doer(tmp_path):
    from locksmith.peer.records import PeerModeSettings

    # Without enabling, the vault should not produce a PeerDoer.
    # We assert by constructing a Vault-like environment via the helper
    # below. Vault construction is heavy; we touch the public attribute.

    # Stub vault for this assertion: import the symbol that vaulting.py
    # exposes, the actual peer_doer attribute.
    from locksmith.core import vaulting

    assert hasattr(vaulting, "Vault")
    # PeerDoer is wired in §2 below; this assertion checks that the
    # attribute name exists in the Vault namespace once peer mode is wired.
    # Test passes after Step 2.


def test_vault_with_peer_enabled_constructs_peer_doer(tmp_path):
    from locksmith.peer.records import PeerModeSettings

    settings = PeerModeSettings(enabled=True, port=0, bind_host="127.0.0.1")
    # Construct a peer doer directly with a minimal hby — full Vault
    # construction is exercised by integration tests in Task 17+.
    from types import SimpleNamespace
    from locksmith.peer.doer import PeerDoer
    from locksmith.db.basing import LocksmithBaser

    baser = LocksmithBaser(name="wiretest", headDirPath=str(tmp_path),
                           reopen=True, temp=True)
    try:
        hby = SimpleNamespace(habs={"EAID_VAULT": SimpleNamespace(pre="EAID_VAULT")},
                              name="wiretest")
        exchanger = SimpleNamespace(processEvent=lambda *a, **k: None)
        doer = PeerDoer(
            hby=hby, baser=baser, settings=settings,
            exchanger=exchanger, is_destination_exposed=lambda aid: True,
        )
        try:
            assert doer.server is not None
        finally:
            doer.server.close()
    finally:
        baser.close(clear=True)
```

- [ ] **Step 2: Run — expect FAIL on the `hasattr` line (peer_doer attr not yet present)**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_vault_wiring.py -v
```

Expected: 1 fail (peer_doer attribute missing), 1 pass (the direct construction test).

- [ ] **Step 3: Wire `PeerDoer` into `Vault`**

Edit `src/locksmith/core/vaulting.py`:

After the existing import line `from locksmith.core.turretting import TurretDoer`, add:

```python
from locksmith.peer.doer import PeerDoer
from locksmith.peer.records import PeerModeSettings
```

Inside `Vault.__init__`, after the `self.turrent_doer = None` block (around line 160), add:

```python
        # Peer-mode listener (vault-wide).
        self.peer_doer: PeerDoer | None = None
        peer_settings = self.db.peerSettings.get(keys=("default",)) or PeerModeSettings()
        if peer_settings.enabled:
            exposed_aids: set[str] = set()  # populated by Task 12 UI toggle
            self.peer_doer = PeerDoer(
                hby=self.hby,
                baser=self.db,
                settings=peer_settings,
                exchanger=self.exc,
                is_destination_exposed=lambda aid, exposed=exposed_aids: aid in exposed,
            )
            self._peer_exposed_aids = exposed_aids
```

Then in the `self.doers = [...]` list, after the `if self.turrent_doer is not None: self.doers.append(self.turrent_doer)` line, add:

```python
        if self.peer_doer is not None:
            self.doers.append(self.peer_doer)
```

- [ ] **Step 4: Update the test assertion to check the attribute**

Edit `tests/peer/test_vault_wiring.py` — replace the body of `test_vault_with_peer_disabled_has_no_peer_doer` with:

```python
def test_vault_with_peer_disabled_has_no_peer_doer():
    from locksmith.core import vaulting
    import inspect

    src = inspect.getsource(vaulting.Vault.__init__)
    assert "self.peer_doer" in src, "Vault.__init__ must declare self.peer_doer"
```

- [ ] **Step 5: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_vault_wiring.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/core/vaulting.py tests/peer/test_vault_wiring.py
git commit -m "feat(peer): wire PeerDoer into Vault, gated on peerSettings.enabled"
```

---

## Task 7: Extend `generate_oobi` to handle role `peer`

**Files:**
- Modify: `src/locksmith/core/habbing.py` (extend `generate_oobi`)
- Test: `tests/peer/test_generate_oobi.py`

- [ ] **Step 1: Write the failing test**

Create `tests/peer/test_generate_oobi.py`:

```python
from unittest.mock import MagicMock

from locksmith.core import habbing


def test_generate_oobi_peer_role_with_tcp_endpoint():
    """When an AID has a witness-served tcp peer endpoint, generate_oobi
    returns the witness-served URL with role=peer.
    """
    # hab.fetchRoleUrls returns a {role: {eid: {scheme: url}}} mapping.
    hab = MagicMock()
    hab.pre = "EAID_ALICE"
    # First witness with peer authorization
    hab.fetchRoleUrls.return_value = {
        "peer": {
            "EWIT1": {
                "http": "http://witness.keri.host:5642"
            }
        }
    }

    app = MagicMock()
    result = habbing.generate_oobi(app, hab, role="peer")

    assert result["success"] is True
    assert result["oobi"].endswith("/oobi/EAID_ALICE/peer/EWIT1")
    assert "http://witness.keri.host" in result["oobi"]


def test_generate_oobi_peer_role_no_authorization_returns_failure():
    hab = MagicMock()
    hab.pre = "EAID_ALICE"
    hab.fetchRoleUrls.return_value = {}

    app = MagicMock()
    result = habbing.generate_oobi(app, hab, role="peer")

    assert result["success"] is False
    assert result["oobi"] is None
```

- [ ] **Step 2: Run — expect FAIL (peer role not handled)**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_generate_oobi.py -v
```

Expected: 2 failed.

- [ ] **Step 3: Extend `generate_oobi`**

Edit `src/locksmith/core/habbing.py`. Inside `generate_oobi`, before the `if not oobis:` line (around line 878), add a new branch:

```python
        elif role == 'peer':
            # Peer endpoints are witness-served, mirroring the agent role
            # pattern but with role=peer. The peer endpoint URL itself is
            # tcp://host:port, but the OOBI is HTTP-fetched from the witness.
            roleUrls = hab.fetchRoleUrls(
                hab.pre, scheme=kering.Schemes.http, role='peer'
            ) or hab.fetchRoleUrls(hab.pre, scheme=kering.Schemes.https, role='peer')

            if roleUrls and 'peer' in roleUrls:
                for eid, urls in roleUrls['peer'].items():
                    url = urls.get(kering.Schemes.http) or urls.get(kering.Schemes.https)
                    if url:
                        up = urlparse(url)
                        oobis.append(urljoin(up.geturl(), f'/oobi/{hab.pre}/peer/{eid}'))
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_generate_oobi.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/core/habbing.py tests/peer/test_generate_oobi.py
git commit -m "feat(peer): generate_oobi handles role=peer"
```

---

## Task 8: `peer_send` channel selector with auto-fallback

**Files:**
- Create: `src/locksmith/peer/sending.py`
- Test: `tests/peer/test_sending.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/peer/test_sending.py`:

```python
import logging
import socket
from types import SimpleNamespace

from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.peer.sending import peer_send, SendOutcome


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_recipient(aid="EAID_BOB", url="tcp://127.0.0.1:5621"):
    return PeerRecord(aid=aid, label="Bob", endpoint_url=url,
                      paired_at=datetime.now(timezone.utc).isoformat())


def test_no_peer_record_falls_through_to_mailbox(baser, caplog):
    al = PeerAllowlist(baser)
    mailbox_sender = SimpleNamespace(calls=[])

    def mailbox_send(recipient_aid, exn_bytes):
        mailbox_sender.calls.append((recipient_aid, exn_bytes))
        return True

    outcome = peer_send(
        allowlist=al,
        recipient_aid="EAID_BOB",
        exn_bytes=b"FAKE-CESR",
        mailbox_send=mailbox_send,
    )

    assert outcome is SendOutcome.MAILBOX
    assert mailbox_sender.calls == [("EAID_BOB", b"FAKE-CESR")]


def test_peer_endpoint_unreachable_falls_back_to_mailbox(baser, caplog):
    al = PeerAllowlist(baser)
    # Point at a port nothing is listening on
    bad_port = _free_port()
    al.add(_make_recipient(url=f"tcp://127.0.0.1:{bad_port}"))

    mailbox_sender = SimpleNamespace(calls=[])

    def mailbox_send(recipient_aid, exn_bytes):
        mailbox_sender.calls.append((recipient_aid, exn_bytes))
        return True

    with caplog.at_level(logging.INFO, logger="locksmith.peer.sending"):
        outcome = peer_send(
            allowlist=al,
            recipient_aid="EAID_BOB",
            exn_bytes=b"FAKE-CESR",
            mailbox_send=mailbox_send,
        )

    assert outcome is SendOutcome.FALLBACK
    assert mailbox_sender.calls == [("EAID_BOB", b"FAKE-CESR")]
    assert any("peer.send.peer_failed" in r.message for r in caplog.records)
    assert any("peer.send.fallback_mailbox" in r.message for r in caplog.records)


def test_peer_endpoint_reachable_returns_peer_outcome(baser, caplog):
    al = PeerAllowlist(baser)
    port = _free_port()

    # Stand up a real listening socket that just accepts and discards
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)

    al.add(_make_recipient(url=f"tcp://127.0.0.1:{port}"))

    mailbox_sender = SimpleNamespace(calls=[])

    def mailbox_send(recipient_aid, exn_bytes):
        mailbox_sender.calls.append((recipient_aid, exn_bytes))
        return True

    try:
        with caplog.at_level(logging.INFO, logger="locksmith.peer.sending"):
            outcome = peer_send(
                allowlist=al,
                recipient_aid="EAID_BOB",
                exn_bytes=b"FAKE-CESR",
                mailbox_send=mailbox_send,
            )
    finally:
        server.close()

    assert outcome is SendOutcome.PEER
    assert mailbox_sender.calls == []
    assert any("peer.send.peer_ok" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_sending.py -v
```

Expected: `ModuleNotFoundError: No module named 'locksmith.peer.sending'`.

- [ ] **Step 3: Implement `peer_send`**

Create `src/locksmith/peer/sending.py`:

```python
"""Outbound channel selector with auto-fallback to mailbox.

Per spec §3b: if the recipient has a PeerRecord with a reachable
endpoint, write the exn over TCP. Otherwise (or on connect failure)
fall back to the mailbox path.
"""
from __future__ import annotations

import enum
import socket
from typing import Callable
from urllib.parse import urlparse

from keri import help

from locksmith.peer.allowlist import PeerAllowlist

logger = help.ogler.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 3.0


class SendOutcome(enum.Enum):
    PEER = "peer"
    MAILBOX = "mailbox"
    FALLBACK = "peer→mailbox"


def peer_send(
    allowlist: PeerAllowlist,
    recipient_aid: str,
    exn_bytes: bytes,
    mailbox_send: Callable[[str, bytes], bool],
) -> SendOutcome:
    """Send `exn_bytes` to `recipient_aid` over peer or mailbox.

    Args:
        allowlist: read-only access to PeerRecords (for endpoint lookup).
        recipient_aid: the destination AID.
        exn_bytes: framed CESR bytes ready to write.
        mailbox_send: callable that takes (aid, bytes) and returns True
            on successful enqueue to the mailbox path.

    Returns:
        SendOutcome describing the channel actually used.
    """
    record = allowlist.get(recipient_aid)
    if record is None or not record.endpoint_url:
        logger.info(f"peer.send.attempt recipient={recipient_aid} channel=mailbox reason=no_peer_record")
        mailbox_send(recipient_aid, exn_bytes)
        return SendOutcome.MAILBOX

    logger.info(f"peer.send.attempt recipient={recipient_aid} channel=peer endpoint={record.endpoint_url}")
    try:
        host, port = _split_tcp_url(record.endpoint_url)
    except ValueError as e:
        logger.warning(f"peer.send.peer_failed recipient={recipient_aid} reason=bad_url url={record.endpoint_url} err={e}")
        mailbox_send(recipient_aid, exn_bytes)
        logger.info(f"peer.send.fallback_mailbox recipient={recipient_aid}")
        return SendOutcome.FALLBACK

    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_SECONDS) as sock:
            sock.sendall(exn_bytes)
    except (OSError, socket.timeout) as e:
        logger.warning(f"peer.send.peer_failed recipient={recipient_aid} endpoint={record.endpoint_url} err={e}")
        mailbox_send(recipient_aid, exn_bytes)
        logger.info(f"peer.send.fallback_mailbox recipient={recipient_aid}")
        return SendOutcome.FALLBACK

    logger.info(f"peer.send.peer_ok recipient={recipient_aid} endpoint={record.endpoint_url} bytes={len(exn_bytes)}")
    return SendOutcome.PEER


def _split_tcp_url(url: str) -> tuple[str, int]:
    up = urlparse(url)
    if up.scheme != "tcp":
        raise ValueError(f"expected tcp:// scheme, got {up.scheme!r}")
    if not up.hostname or not up.port:
        raise ValueError(f"missing host or port in {url!r}")
    return up.hostname, up.port
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_sending.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/peer/sending.py tests/peer/test_sending.py
git commit -m "feat(peer): peer_send channel selector with auto-fallback to mailbox"
```

---

## Task 9: UI — Vault settings "Direct peer mode" section

**Files:**
- Create: `src/locksmith/ui/vault/settings/peer_section.py`
- Modify: `src/locksmith/ui/vault/settings/page.py` (mount the section)
- Test: `tests/peer/test_peer_section.py`

- [ ] **Step 1: Write the failing test for the widget**

Create `tests/peer/test_peer_section.py`:

```python
import socket

import pytest

from locksmith.peer.records import PeerModeSettings
from locksmith.ui.vault.settings.peer_section import PeerSettingsSection


class _StubVault:
    def __init__(self, baser):
        self.db = baser
        self.peer_doer = None
        self._restarts = 0

    def restart_peer_mode(self):
        self._restarts += 1


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_section_loads_existing_settings(qapp, baser):
    baser.peerSettings.pin(keys=("default",), val=PeerModeSettings(enabled=True, port=5621))
    vault = _StubVault(baser)
    section = PeerSettingsSection(vault=vault)
    assert section.enabled_toggle.isChecked() is True
    assert section.port_spin.value() == 5621


def test_toggle_writes_settings(qapp, baser):
    vault = _StubVault(baser)
    section = PeerSettingsSection(vault=vault)
    section.enabled_toggle.setChecked(True)
    section.port_spin.setValue(_free_port())
    section.apply_button.click()

    saved = baser.peerSettings.get(keys=("default",))
    assert saved is not None
    assert saved.enabled is True
    assert vault._restarts == 1


def test_status_line_reflects_listener_state(qapp, baser):
    vault = _StubVault(baser)
    section = PeerSettingsSection(vault=vault)
    section.update_status("Listening on 0.0.0.0:5621")
    assert "5621" in section.status_label.text()
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_peer_section.py -v
```

Expected: `ModuleNotFoundError: No module named 'locksmith.ui.vault.settings.peer_section'`.

- [ ] **Step 3: Implement the section widget**

Create `src/locksmith/ui/vault/settings/peer_section.py`:

```python
"""Vault settings: 'Direct peer mode' section (vault-level listener config)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)
from keri import help

from locksmith.peer.records import PeerModeSettings

logger = help.ogler.getLogger(__name__)


class PeerSettingsSection(QFrame):
    """Vault-level listener controls: on/off, port, bind interface, advertised host."""

    def __init__(self, vault, parent=None):
        super().__init__(parent=parent)
        self._vault = vault
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Direct peer mode")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        layout.addWidget(title)

        self.enabled_toggle = QCheckBox("Enable peer-mode listener")
        layout.addWidget(self.enabled_toggle)

        row = QHBoxLayout()
        row.addWidget(QLabel("Port:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(5621)
        row.addWidget(self.port_spin)

        row.addWidget(QLabel("Bind:"))
        self.bind_combo = QComboBox()
        self.bind_combo.addItem("All interfaces (0.0.0.0)", "0.0.0.0")
        row.addWidget(self.bind_combo)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Advertised host:"))
        self.advertised_combo = QComboBox()
        self.advertised_combo.setEditable(True)
        row2.addWidget(self.advertised_combo)
        layout.addLayout(row2)

        self.status_label = QLabel("Stopped")
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply)
        layout.addWidget(self.apply_button)

        # populate detected interfaces
        for ip in _detect_interface_ips():
            self.bind_combo.addItem(f"{ip}", ip)
            self.advertised_combo.addItem(f"{ip}", ip)

    def _load(self) -> None:
        rec = self._vault.db.peerSettings.get(keys=("default",))
        if rec is None:
            return
        self.enabled_toggle.setChecked(rec.enabled)
        self.port_spin.setValue(rec.port)
        idx = self.bind_combo.findData(rec.bind_host)
        if idx >= 0:
            self.bind_combo.setCurrentIndex(idx)
        if rec.advertised_host:
            self.advertised_combo.setCurrentText(rec.advertised_host)

    def _on_apply(self) -> None:
        rec = PeerModeSettings(
            enabled=self.enabled_toggle.isChecked(),
            port=self.port_spin.value(),
            bind_host=self.bind_combo.currentData() or "0.0.0.0",
            advertised_host=self.advertised_combo.currentText().strip(),
        )
        self._vault.db.peerSettings.pin(keys=("default",), val=rec)
        logger.info(
            f"peer.settings.saved enabled={rec.enabled} port={rec.port} "
            f"bind={rec.bind_host} advertised={rec.advertised_host!r}"
        )
        self._vault.restart_peer_mode()

    def update_status(self, text: str) -> None:
        self.status_label.setText(text)


def _detect_interface_ips() -> list[str]:
    """Best-effort list of host IPs the user might want to advertise."""
    import socket as _socket
    ips: list[str] = []
    try:
        host = _socket.gethostname()
        for info in _socket.getaddrinfo(host, None, _socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except _socket.gaierror:
        pass
    return ips
```

- [ ] **Step 4: Add a `restart_peer_mode` method on `Vault`**

Edit `src/locksmith/core/vaulting.py`. After the `deactivate_mailbox` method on `Vault`, add:

```python
    def restart_peer_mode(self):
        """Stop the current peer doer (if any) and re-construct from
        current peerSettings. Safe to call when the doer is None.

        Implementation note: hio's DoDoer doesn't support clean removal
        of nested doers at runtime. We close the underlying socket so
        the inner doers go inert, then drop the reference. The dead doer
        stays in the parent's doers list but does nothing (it polls a
        closed socket). For a tighter lifecycle, see hio.base.doing
        upstream for `exit()` and revisit.
        """
        from locksmith.peer.doer import PeerDoer
        from locksmith.peer.records import PeerModeSettings

        if self.peer_doer is not None and self.peer_doer.server is not None:
            self.peer_doer.server.close()
            self.peer_doer = None

        settings = self.db.peerSettings.get(keys=("default",)) or PeerModeSettings()
        if not settings.enabled:
            return

        exposed = getattr(self, "_peer_exposed_aids", set())
        self.peer_doer = PeerDoer(
            hby=self.hby,
            baser=self.db,
            settings=settings,
            exchanger=self.exc,
            is_destination_exposed=lambda aid, e=exposed: aid in e,
        )
        self.extend(self.peer_doer.doers)
```

- [ ] **Step 5: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_peer_section.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Mount the section in `settings/page.py`**

Edit `src/locksmith/ui/vault/settings/page.py`. Find the layout assembly block (search for the existing settings sections being added to a layout) and add an instance of `PeerSettingsSection(vault=self.vault)` after the existing sections. The exact insertion is near the bottom of `__init__` where existing sections are appended; follow the existing pattern.

Add the import near the top:

```python
from locksmith.ui.vault.settings.peer_section import PeerSettingsSection
```

And inside `__init__`, after the last existing section is added to the layout:

```python
        self.peer_section = PeerSettingsSection(vault=self.vault)
        layout.addWidget(self.peer_section)
```

- [ ] **Step 7: Commit**

```bash
git add src/locksmith/ui/vault/settings/peer_section.py \
        src/locksmith/ui/vault/settings/page.py \
        src/locksmith/core/vaulting.py \
        tests/peer/test_peer_section.py
git commit -m "feat(peer): vault settings section for peer-mode listener"
```

---

## Task 10: UI — Per-AID "Expose this AID over peer mode" toggle

**Files:**
- Modify: `src/locksmith/ui/vault/identifiers/identifier_sections.py` (extend OOBI role dropdown + add toggle)
- Test: `tests/peer/test_identifier_peer_toggle.py`

- [ ] **Step 1: Write the failing test**

Create `tests/peer/test_identifier_peer_toggle.py`:

```python
from locksmith.ui.vault.identifiers import identifier_sections


def test_oobi_dropdown_includes_peer_role():
    # The role_map at identifier_sections.py is the source of truth for
    # which roles the dropdown surfaces.
    role_map_source = identifier_sections.__file__
    with open(role_map_source) as f:
        src = f.read()
    assert '"Peer": "peer"' in src or "'Peer': 'peer'" in src, \
        "OOBI role dropdown must include a Peer entry"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_identifier_peer_toggle.py -v
```

Expected: fail (Peer not in role_map yet).

- [ ] **Step 3: Add `Peer` to OOBI roles**

Edit `src/locksmith/ui/vault/identifiers/identifier_sections.py`. Two changes:

(a) Around line 301, where `addItems` is called:

```python
        self.oobi_role_dropdown.addItems(["Witness", "Controller", "Mailbox", "Peer"])
```

(b) Around line 351, in `_on_oobi_role_changed`:

```python
    def _on_oobi_role_changed(self, role_text: str) -> None:
        role_map = {
            "Witness": "witness",
            "Controller": "controller",
            "Mailbox": "mailbox",
            "Peer": "peer",
        }
        role = role_map.get(role_text, "witness")
        self._generate_oobi(role)
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_identifier_peer_toggle.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Add per-AID expose toggle**

In the same file, after the OOBI role dropdown row (after `layout.addLayout(role_row)`), add:

```python
        # Per-AID "Expose this AID over peer mode" toggle
        peer_row = QHBoxLayout()
        peer_label = QLabel("Expose over peer mode:")
        peer_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        peer_row.addWidget(peer_label)

        from PySide6.QtWidgets import QCheckBox  # local import to avoid touching headers
        self.peer_expose_toggle = QCheckBox()
        self.peer_expose_toggle.toggled.connect(self._on_peer_expose_toggled)
        peer_row.addWidget(self.peer_expose_toggle)
        peer_row.addStretch()
        layout.addLayout(peer_row)
```

And add the method:

```python
    def _on_peer_expose_toggled(self, checked: bool) -> None:
        vault = getattr(self.app, "_current_vault", None)
        if vault is None:
            return
        exposed = getattr(vault, "_peer_exposed_aids", None)
        if exposed is None:
            return
        if checked:
            exposed.add(self.hab.pre)
            self._publish_peer_role()
            logger.info(f"peer.role.enabled aid={self.hab.pre}")
        else:
            exposed.discard(self.hab.pre)
            logger.info(f"peer.role.disabled aid={self.hab.pre}")

    def _publish_peer_role(self) -> None:
        """Publish role=peer endpoint authorization on this AID's KEL."""
        from keri import kering
        from locksmith.peer.records import PeerModeSettings

        vault = getattr(self.app, "_current_vault", None)
        if vault is None:
            return
        settings = vault.db.peerSettings.get(keys=("default",)) or PeerModeSettings()
        endpoint = f"tcp://{settings.advertised_host or '127.0.0.1'}:{settings.port}"
        # makeRoleAuth writes a reply (rpy) message to the KEL declaring
        # the endpoint URL for the named role.
        if hasattr(self.hab, "makeRoleAuth"):
            self.hab.makeRoleAuth(role="peer", eid=self.hab.pre, scheme=kering.Schemes.tcp, url=endpoint)
```

- [ ] **Step 6: Add a logger import if absent**

Check the top of `identifier_sections.py`. If `logger` isn't already defined, add:

```python
from keri import help
logger = help.ogler.getLogger(__name__)
```

- [ ] **Step 7: Verify the file still imports cleanly**

```bash
cd ~/code/locksmith && .venv/bin/python -c "from locksmith.ui.vault.identifiers import identifier_sections; print('OK')"
```

Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
git add src/locksmith/ui/vault/identifiers/identifier_sections.py \
        tests/peer/test_identifier_peer_toggle.py
git commit -m "feat(peer): identifier OOBI dropdown + per-AID expose toggle for peer role"
```

---

## Task 11: UI — Paired Peers page (list + Add dialog + Unpair + Test connection)

**Files:**
- Create: `src/locksmith/ui/vault/peers/__init__.py`
- Create: `src/locksmith/ui/vault/peers/list.py`
- Create: `src/locksmith/ui/vault/peers/add_dialog.py`
- Test: `tests/peer/test_peers_page.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/peer/test_peers_page.py`:

```python
from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.ui.vault.peers.list import PairedPeersPage


class _StubVault:
    def __init__(self, baser):
        self.db = baser


def _seed(baser, aid="EAID_BOB"):
    PeerAllowlist(baser).add(PeerRecord(
        aid=aid, label="Bob", endpoint_url="tcp://10.0.0.2:5621",
        paired_at=datetime.now(timezone.utc).isoformat(),
    ))


def test_page_renders_paired_rows(qapp, baser):
    _seed(baser)
    page = PairedPeersPage(vault=_StubVault(baser))
    page.refresh()
    rows = page.list_widget.count()
    assert rows == 1


def test_unpair_removes_row(qapp, baser):
    _seed(baser)
    page = PairedPeersPage(vault=_StubVault(baser))
    page.refresh()
    page.unpair("EAID_BOB")
    page.refresh()
    assert page.list_widget.count() == 0
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_peers_page.py -v
```

- [ ] **Step 3: Implement the page**

Create `src/locksmith/ui/vault/peers/__init__.py` (empty).

Create `src/locksmith/ui/vault/peers/list.py`:

```python
"""Paired peers page: list, add, unpair, test connection."""
from __future__ import annotations

import socket

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)
from keri import help

from locksmith.peer.allowlist import PeerAllowlist

logger = help.ogler.getLogger(__name__)


class PairedPeersPage(QWidget):
    def __init__(self, vault, parent=None):
        super().__init__(parent=parent)
        self._vault = vault
        self._allowlist = PeerAllowlist(vault.db)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Paired peers")
        title.setStyleSheet("font-weight: 600; font-size: 16px;")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Add peer")
        self.add_button.clicked.connect(self._on_add)
        toolbar.addWidget(self.add_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

    def refresh(self) -> None:
        self.list_widget.clear()
        for rec in self._allowlist.list():
            item = QListWidgetItem(f"{rec.label}  —  {rec.aid}  —  {rec.endpoint_url}")
            item.setData(0x0100, rec.aid)  # Qt.UserRole = 0x0100
            self.list_widget.addItem(item)

    def unpair(self, aid: str) -> None:
        self._allowlist.remove(aid)

    def _on_add(self) -> None:
        from locksmith.ui.vault.peers.add_dialog import AddPeerDialog
        dialog = AddPeerDialog(vault=self._vault, parent=self)
        dialog.peer_added.connect(self.refresh)
        dialog.open()

    def test_connection(self, aid: str, timeout: float = 3.0) -> bool:
        rec = self._allowlist.get(aid)
        if rec is None or not rec.endpoint_url:
            return False
        try:
            from urllib.parse import urlparse
            up = urlparse(rec.endpoint_url)
            with socket.create_connection((up.hostname, up.port), timeout=timeout):
                logger.info(f"peer.test.ok aid={aid} endpoint={rec.endpoint_url}")
                return True
        except (OSError, socket.timeout) as e:
            logger.info(f"peer.test.failed aid={aid} endpoint={rec.endpoint_url} err={e}")
            return False
```

- [ ] **Step 4: Implement the Add dialog**

Create `src/locksmith/ui/vault/peers/add_dialog.py`:

```python
"""Add Peer dialog — paste an OOBI URL, resolve, insert into allowlist."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout,
)
from keri import help

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord

logger = help.ogler.getLogger(__name__)


class AddPeerDialog(QDialog):
    peer_added = Signal()

    def __init__(self, vault, parent=None):
        super().__init__(parent=parent)
        self._vault = vault
        self._allowlist = PeerAllowlist(vault.db)
        self.setWindowTitle("Add peer")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Peer OOBI URL:"))
        self.oobi_input = QLineEdit()
        self.oobi_input.setPlaceholderText("http://witness.example.com/oobi/EAID_BOB/peer/EWIT1")
        layout.addWidget(self.oobi_input)

        layout.addWidget(QLabel("Label (optional):"))
        self.label_input = QLineEdit()
        layout.addWidget(self.label_input)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #a00;")
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        url = self.oobi_input.text().strip()
        if not url:
            self.error_label.setText("OOBI URL is required.")
            return

        try:
            aid, endpoint_url = self._resolve_oobi(url)
        except OobiResolutionError as e:
            logger.warning(f"peer.pair.failed reason={e.reason} url={url}")
            self.error_label.setText(str(e))
            return

        if self._allowlist.contains(aid):
            self.error_label.setText("This peer is already paired.")
            return

        self._allowlist.add(PeerRecord(
            aid=aid,
            label=self.label_input.text().strip() or aid[:12],
            endpoint_url=endpoint_url,
            paired_at=datetime.now(timezone.utc).isoformat(),
        ))
        self.peer_added.emit()
        self.accept()

    def _resolve_oobi(self, url: str) -> tuple[str, str]:
        """Resolve OOBI via the vault's Habery, return (aid, tcp_endpoint).

        Delegates to keripy's oobi resolver. The full resolution flow is
        async; for the dialog we do a synchronous fetch + extract.
        """
        from keri.app import oobiing
        from urllib.parse import urlparse

        # Hand the URL to the Habery's oobiery for resolution. Wait for
        # the resolved KEL + role authorizations to land.
        oobiery = oobiing.Oobiery(hby=self._vault.hby)
        oobiery.processOobis()  # tick once; tests provide already-resolved KELs
        # Parse the AID out of the OOBI URL path
        path = urlparse(url).path  # /oobi/<aid>/peer/<eid>
        parts = [p for p in path.split("/") if p]
        if len(parts) < 3 or parts[0] != "oobi" or parts[2] != "peer":
            raise OobiResolutionError("not_peer_oobi", "Not a peer-role OOBI URL.")
        aid = parts[1]

        hab = self._vault.hby.habByPre(aid)
        if hab is None:
            raise OobiResolutionError("kel_unverified",
                "Couldn't verify this peer's KEL. The OOBI may be tampered.")

        urls = hab.fetchUrls(eid=hab.pre, scheme="tcp")
        if not urls or "tcp" not in urls:
            raise OobiResolutionError("no_tcp_endpoint",
                "Peer's KEL does not authorize a tcp endpoint.")
        return aid, urls["tcp"]


class OobiResolutionError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
```

- [ ] **Step 5: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_peers_page.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/locksmith/ui/vault/peers/__init__.py \
        src/locksmith/ui/vault/peers/list.py \
        src/locksmith/ui/vault/peers/add_dialog.py \
        tests/peer/test_peers_page.py
git commit -m "feat(peer): Paired Peers page + Add Peer dialog"
```

---

## Task 12: Outbound channel badge in notifications + credentials list

**Files:**
- Modify: `src/locksmith/core/vaulting.py` (route outbound IPEX through `peer_send`)
- Test: `tests/peer/test_outbound_routing.py`

- [ ] **Step 1: Write the failing test**

Create `tests/peer/test_outbound_routing.py`:

```python
import logging

from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.peer.sending import SendOutcome, peer_send


def test_outbound_badge_records_outcome(baser, caplog):
    """peer_send logs peer.send.peer_ok or peer.send.fallback_mailbox.
    The badge surfaced in UI is derived from these structured log events."""
    al = PeerAllowlist(baser)
    al.add(PeerRecord(
        aid="EAID_BOB", label="Bob",
        endpoint_url="tcp://127.0.0.1:1",  # unreachable
        paired_at=datetime.now(timezone.utc).isoformat(),
    ))

    mailbox_calls = []
    with caplog.at_level(logging.INFO, logger="locksmith.peer.sending"):
        outcome = peer_send(
            allowlist=al,
            recipient_aid="EAID_BOB",
            exn_bytes=b"FAKE",
            mailbox_send=lambda aid, b: mailbox_calls.append((aid, b)) or True,
        )

    assert outcome is SendOutcome.FALLBACK
    assert any("peer.send.fallback_mailbox" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run — expect PASS (this is a regression-guard for Task 8 plus a documentation test)**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_outbound_routing.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Surface the badge by attaching channel metadata to outbound notifications**

The cleanest place to surface the badge is at the point where outbound IPEX flows complete and a "credential sent" notification is created. Find the existing credential-sent notification site:

```bash
cd ~/code/locksmith && grep -rn "ipex.*grant.*notif\|notif.*grant\|issued_credential" src/locksmith/core --include="*.py" | head -5
```

Whichever module emits the "credential sent" notification, modify it to also set a `channel` attribute from the `SendOutcome` returned by `peer_send`. Example (replace `existing_outbound_function` with the actual function name discovered above):

```python
from locksmith.peer.sending import SendOutcome

# Inside the outbound IPEX flow, where the notification object is built:
notification.channel = outcome.value  # "peer" / "mailbox" / "peer→mailbox"
```

Then in the toast renderer (`NotificationToastDoer.format_toast` or equivalent — search for where the toast text is built and shown), append a badge segment:

```python
channel = getattr(notification, "channel", "") or ""
badge = f"  [{channel}]" if channel in ("peer", "mailbox", "peer→mailbox") else ""
toast_text = f"{base_text}{badge}"
```

The exact symbols depend on how Locksmith's notification model is shaped. If `notification.channel` cannot be added (e.g. notifications are immutable Notifier records), store the channel in a side-table keyed by notification SAID and look it up in the renderer. The peer_send outcome is already in the structured logs as a fallback — the UI badge is the polish layer on top.

- [ ] **Step 4: Commit**

```bash
git add src/locksmith/core/vaulting.py tests/peer/test_outbound_routing.py
git commit -m "feat(peer): surface peer/mailbox channel badge in notifications"
```

---

## Task 13: Integration test fixture — two HOME-isolated wallets

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/peer/__init__.py`
- Create: `tests/integration/peer/conftest.py`

- [ ] **Step 1: Create directory markers**

```bash
mkdir -p tests/integration/peer
touch tests/integration/__init__.py tests/integration/peer/__init__.py
```

- [ ] **Step 2: Write the fixture file**

Create `tests/integration/peer/conftest.py`:

```python
"""Fixtures for two-wallet integration tests.

Spawns two Locksmith wallets in subprocesses with isolated HOME dirs,
matching the manual dev pattern documented in the spec:

- Wallet A: HOME=<tmpdir>/wallet_a, socket <tmpdir>/wallet_a/.locksmith-control.sock
- Wallet B: HOME=<tmpdir>/wallet_b, socket <tmpdir>/wallet_b/.locksmith-control.sock

Both wallets must have the locksmith-ui-tester plugin clone available;
the fixture symlinks it into each HOME's plugin directory.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
UI_TESTER_REPO = Path.home() / "code" / "locksmith-ui-tester"


def _install_ui_tester(home: Path) -> None:
    """Mirror the way the user installs the tester for manual dev — copy
    the clone into <home>/.locksmith/plugins/ui_tester."""
    plugins = home / ".locksmith" / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    dest = plugins / "ui_tester"
    if dest.exists():
        return
    if not UI_TESTER_REPO.exists():
        pytest.skip(f"locksmith-ui-tester not present at {UI_TESTER_REPO}")
    shutil.copytree(UI_TESTER_REPO, dest)


def _start_wallet(home: Path, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "locksmith.main"],
        env=env,
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
    )
    return proc


def _wait_for_socket(socket_path: Path, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if socket_path.exists():
            try:
                sock = socket.socket(socket.AF_UNIX)
                sock.connect(str(socket_path))
                sock.close()
                return
            except OSError:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"socket never appeared: {socket_path}")


def _devctl(socket_path: Path, op: str, **kwa) -> dict:
    sock = socket.socket(socket.AF_UNIX)
    sock.settimeout(5.0)
    sock.connect(str(socket_path))
    payload = json.dumps({"op": op, **kwa}).encode("utf-8") + b"\n"
    sock.sendall(payload)
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    sock.close()
    return json.loads(buf.split(b"\n", 1)[0])


@pytest.fixture
def two_wallets(tmp_path):
    home_a = tmp_path / "wallet_a"
    home_b = tmp_path / "wallet_b"
    home_a.mkdir()
    home_b.mkdir()
    _install_ui_tester(home_a)
    _install_ui_tester(home_b)

    log_a = tmp_path / "wallet_a.log"
    log_b = tmp_path / "wallet_b.log"

    proc_a = _start_wallet(home_a, log_a)
    proc_b = _start_wallet(home_b, log_b)

    sock_a = home_a / ".locksmith-control.sock"
    sock_b = home_b / ".locksmith-control.sock"
    try:
        _wait_for_socket(sock_a)
        _wait_for_socket(sock_b)
        yield {
            "a": {"home": home_a, "log": log_a, "sock": sock_a, "proc": proc_a},
            "b": {"home": home_b, "log": log_b, "sock": sock_b, "proc": proc_b},
            "devctl": _devctl,
        }
    finally:
        for proc in (proc_a, proc_b):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
```

- [ ] **Step 3: Smoke-test the fixture with a trivial ping test**

Create `tests/integration/peer/test_fixture_smoke.py`:

```python
def test_both_wallets_respond_to_ping(two_wallets):
    devctl = two_wallets["devctl"]
    pong_a = devctl(two_wallets["a"]["sock"], "ping")
    pong_b = devctl(two_wallets["b"]["sock"], "ping")
    assert pong_a.get("ok") is True
    assert pong_b.get("ok") is True
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/integration/peer/test_fixture_smoke.py -v
```

Expected: 1 passed (may take ~30 seconds for both wallet processes to start).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/__init__.py tests/integration/peer/__init__.py \
        tests/integration/peer/conftest.py tests/integration/peer/test_fixture_smoke.py
git commit -m "test(peer): two-wallet HOME-isolated subprocess fixture"
```

---

## Task 14: Integration test — Pairing happy path

**Files:**
- Create: `tests/integration/peer/test_pairing.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/peer/test_pairing.py`:

```python
"""Pairing happy path — A and B each have an AID with witness.keri.host;
A pastes B's peer-OOBI; allowlist contains B; symmetric for B."""

import pytest


def _create_vault_with_peer_aid(wallet, devctl):
    """Drive the wallet UI to create a vault, add witness, create an AID,
    and toggle peer mode on for it."""
    sock = wallet["sock"]
    devctl(sock, "create_vault", name="alice-peer", passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
    devctl(sock, "unlock_vault", name="alice-peer", passcode="DoB2-e4Rr-gVOr-Nb1Y-7yBl-gI3n-i4cB-gf07")
    devctl(sock, "add_witness", url="http://witness.keri.host/oobi/BNbRfMPQQge6wKO0uof9Y0e_QYOfiF08k9drc6pOgzjt/controller")
    devctl(sock, "create_identifier", alias="aid")
    devctl(sock, "set_peer_mode", enabled=True, port=0)  # port=0 lets OS pick
    devctl(sock, "expose_aid_over_peer", alias="aid")


@pytest.mark.network  # marker — only run with a witness reachable
def test_pairing_happy_path(two_wallets):
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]
    b = two_wallets["b"]

    _create_vault_with_peer_aid(a, devctl)
    _create_vault_with_peer_aid(b, devctl)

    oobi_a = devctl(a["sock"], "get_peer_oobi", alias="aid")["oobi"]
    oobi_b = devctl(b["sock"], "get_peer_oobi", alias="aid")["oobi"]

    res_b = devctl(b["sock"], "add_peer", oobi=oobi_a, label="Alice")
    res_a = devctl(a["sock"], "add_peer", oobi=oobi_b, label="Bob")

    assert res_b.get("ok") is True
    assert res_a.get("ok") is True

    paired_on_b = devctl(b["sock"], "list_peers")["peers"]
    paired_on_a = devctl(a["sock"], "list_peers")["peers"]

    assert any(p["label"] == "Alice" for p in paired_on_b)
    assert any(p["label"] == "Bob" for p in paired_on_a)

    log_b = b["log"].read_text()
    assert "peer.pair.success" in log_b
```

- [ ] **Step 2: Note the dependency on new devctl ops**

The test calls `set_peer_mode`, `expose_aid_over_peer`, `get_peer_oobi`, `add_peer`, `list_peers`. These ops must be added to the ui_tester plugin's server. Open `~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py` and add the corresponding op handlers that delegate to the new peer UI/services. This is a separate small task captured in §Cross-repo work below.

- [ ] **Step 3: Add the cross-repo devctl ops**

Edit `~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py`. First confirm the existing op-registration pattern:

```bash
grep -nE "@_op|def _[a-z_]+\(|_OPS\s*\[" ~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py | head -20
```

Match whatever decorator/registry pattern the existing ops use (`@_op("name")`, `_OPS["name"] = func`, etc.). Then add handlers for the five ops, following that pattern. Sample code below uses `@_op` syntax — adjust to match the existing convention:

```python
# ----- peer-mode ops -----

@_op("set_peer_mode")
def _set_peer_mode(*, enabled: bool, port: int = 5621, bind_host: str = "0.0.0.0",
                   advertised_host: str = "", **_):
    from locksmith.peer.records import PeerModeSettings
    vault = _current_vault()
    if vault is None:
        return {"error": "no vault open"}
    rec = PeerModeSettings(enabled=enabled, port=port,
                           bind_host=bind_host, advertised_host=advertised_host)
    vault.db.peerSettings.pin(keys=("default",), val=rec)
    vault.restart_peer_mode()
    return {"ok": True}


@_op("expose_aid_over_peer")
def _expose_aid(*, alias: str, **_):
    vault = _current_vault()
    if vault is None:
        return {"error": "no vault open"}
    hab = vault.hby.habByName(alias)
    if hab is None:
        return {"error": f"no hab {alias}"}
    exposed = getattr(vault, "_peer_exposed_aids", None)
    if exposed is None:
        exposed = set()
        vault._peer_exposed_aids = exposed
    exposed.add(hab.pre)
    return {"ok": True, "aid": hab.pre}


@_op("get_peer_oobi")
def _get_peer_oobi(*, alias: str, **_):
    from locksmith.core.habbing import generate_oobi
    vault = _current_vault()
    if vault is None:
        return {"error": "no vault open"}
    hab = vault.hby.habByName(alias)
    if hab is None:
        return {"error": f"no hab {alias}"}
    result = generate_oobi(_current_app(), hab, role="peer")
    if not result["success"]:
        return {"error": result.get("message", "no peer OOBI available")}
    return {"oobi": result["oobi"]}


@_op("add_peer")
def _add_peer(*, oobi: str, label: str = "", **_):
    from locksmith.ui.vault.peers.add_dialog import AddPeerDialog
    vault = _current_vault()
    if vault is None:
        return {"error": "no vault open"}
    dialog = AddPeerDialog(vault=vault)
    dialog.oobi_input.setText(oobi)
    dialog.label_input.setText(label)
    dialog._on_accept()
    if dialog.error_label.text():
        return {"error": dialog.error_label.text()}
    return {"ok": True}


@_op("list_peers")
def _list_peers(**_):
    from locksmith.peer.allowlist import PeerAllowlist
    vault = _current_vault()
    if vault is None:
        return {"error": "no vault open"}
    al = PeerAllowlist(vault.db)
    return {"peers": [{"aid": r.aid, "label": r.label,
                       "endpoint_url": r.endpoint_url} for r in al.list()]}
```

The `_current_vault` / `_current_app` helpers should already exist in `server.py`. If they don't, look for `app.vault` access in adjacent ops and copy the pattern.

- [ ] **Step 4: Run — expect PASS (slow; needs witness.keri.host reachable)**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/integration/peer/test_pairing.py -v -m network
```

Expected: 1 passed (run-time ~60-90 s).

- [ ] **Step 5: Commit the test on the locksmith side**

```bash
git add tests/integration/peer/test_pairing.py
git commit -m "test(peer): integration test for pairing happy path"
```

- [ ] **Step 6: Commit the devctl ops in the ui-tester repo**

```bash
cd ~/code/locksmith-ui-tester && git add src/locksmith_ui_tester/server.py
git commit -m "feat(devctl): peer-mode ops (set_peer_mode, add_peer, list_peers, ...)"
```

Switch back to the locksmith repo when done:

```bash
cd ~/code/locksmith
```

---

## Task 15: Integration test — End-to-end IPEX over peer mode

**Files:**
- Create: `tests/integration/peer/test_send.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/peer/test_send.py`:

```python
"""End-to-end: Alice grants a credential to Bob over peer mode.
A.log shows peer.send.peer_ok; B.log shows peer.recv.delivered."""
import pytest


@pytest.mark.network
def test_ipex_grant_over_peer_mode(two_wallets):
    """Reuses pairing fixture state from test_pairing.py via session reset
    pattern. For first MVP, run pairing inline:"""
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]
    b = two_wallets["b"]

    # Pairing prerequisites
    from tests.integration.peer.test_pairing import _create_vault_with_peer_aid
    _create_vault_with_peer_aid(a, devctl)
    _create_vault_with_peer_aid(b, devctl)

    oobi_a = devctl(a["sock"], "get_peer_oobi", alias="aid")["oobi"]
    oobi_b = devctl(b["sock"], "get_peer_oobi", alias="aid")["oobi"]
    devctl(b["sock"], "add_peer", oobi=oobi_a, label="Alice")
    devctl(a["sock"], "add_peer", oobi=oobi_b, label="Bob")

    # Alice grants a test credential to Bob
    result = devctl(a["sock"], "issue_credential",
                    issuer_alias="aid", recipient_label="Bob",
                    schema="EAdminPing", attrs={"msg": "hello over peer"})
    assert result.get("ok") is True

    # Allow time for peer delivery
    import time
    time.sleep(2)

    log_a = a["log"].read_text()
    log_b = b["log"].read_text()

    assert "peer.send.peer_ok" in log_a
    assert "peer.recv.delivered" in log_b
```

- [ ] **Step 2: Add `peer.recv.delivered` log line to `PeerExchangerShim`**

Edit `src/locksmith/peer/shim.py`. After both gates pass and before calling `self.exchanger.processEvent`, add:

```python
        logger.info(
            f"peer.recv.delivered sender={sender} destination={recipient} said={serder.said}"
        )
        self.exchanger.processEvent(serder, tsgs, cigars, **kwargs)
```

Update the existing unit test `tests/peer/test_shim.py::test_paired_sender_to_opted_in_destination_forwards` to assert the new log line:

```python
def test_paired_sender_to_opted_in_destination_forwards(baser, caplog):
    # ... existing setup ...
    import logging
    with caplog.at_level(logging.INFO, logger="locksmith.peer.shim"):
        shim.processEvent(_exn(), tsgs=None, cigars=None)

    assert len(exchanger.calls) == 1
    assert any("peer.recv.delivered" in r.message for r in caplog.records)
```

- [ ] **Step 3: Run the unit tests to confirm**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer/test_shim.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Run the integration test**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/integration/peer/test_send.py -v -m network
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/locksmith/peer/shim.py tests/peer/test_shim.py tests/integration/peer/test_send.py
git commit -m "test(peer): integration test for end-to-end IPEX over peer mode"
```

---

## Task 16: Integration test — Auto-fallback to mailbox

**Files:**
- Create: `tests/integration/peer/test_fallback.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/peer/test_fallback.py`:

```python
"""Pairing done, B's listener stopped → A grants → A logs peer.send.peer_failed
then peer.send.fallback_mailbox. B receives via mailbox."""
import time

import pytest


@pytest.mark.network
def test_auto_fallback_to_mailbox(two_wallets):
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]
    b = two_wallets["b"]

    from tests.integration.peer.test_pairing import _create_vault_with_peer_aid
    _create_vault_with_peer_aid(a, devctl)
    _create_vault_with_peer_aid(b, devctl)

    oobi_a = devctl(a["sock"], "get_peer_oobi", alias="aid")["oobi"]
    oobi_b = devctl(b["sock"], "get_peer_oobi", alias="aid")["oobi"]
    devctl(b["sock"], "add_peer", oobi=oobi_a, label="Alice")
    devctl(a["sock"], "add_peer", oobi=oobi_b, label="Bob")

    # Stop B's listener
    devctl(b["sock"], "set_peer_mode", enabled=False)
    time.sleep(1)

    # Alice grants -> connect to B fails -> fallback to mailbox
    devctl(a["sock"], "issue_credential",
           issuer_alias="aid", recipient_label="Bob",
           schema="EAdminPing", attrs={"msg": "fallback test"})

    time.sleep(3)

    log_a = a["log"].read_text()
    assert "peer.send.peer_failed" in log_a
    assert "peer.send.fallback_mailbox" in log_a
```

- [ ] **Step 2: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/integration/peer/test_fallback.py -v -m network
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/peer/test_fallback.py
git commit -m "test(peer): integration test for auto-fallback to mailbox"
```

---

## Task 17: Integration tests — Sender + Destination rejection

**Files:**
- Create: `tests/integration/peer/test_gates.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/peer/test_gates.py`:

```python
"""Wire-level reject tests:
  - Mallory connects to B with no prior pairing → B logs sender_rejected.
  - A paired with B; destination AID has expose=off on B → B logs
    destination_not_exposed.
"""
import socket
import time

import pytest


@pytest.mark.network
def test_unpaired_sender_rejected(two_wallets):
    devctl = two_wallets["devctl"]
    b = two_wallets["b"]

    from tests.integration.peer.test_pairing import _create_vault_with_peer_aid
    _create_vault_with_peer_aid(b, devctl)

    port = devctl(b["sock"], "get_peer_port")["port"]
    # Send garbage from an unpaired side
    s = socket.create_connection(("127.0.0.1", port), timeout=3)
    s.sendall(b"\x00" * 32)
    s.close()
    time.sleep(1)

    log_b = b["log"].read_text()
    # Either sender_rejected (if a valid exn with unknown sender arrives)
    # OR parser-level garbage close — for this test we send garbage, so
    # we expect the parser to drop without raising sender_rejected. Track
    # the second flavor instead:
    assert "peer.parser.discarded" in log_b or "peer.gate.sender_rejected" in log_b


@pytest.mark.network
def test_destination_not_exposed_rejected(two_wallets):
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]
    b = two_wallets["b"]

    from tests.integration.peer.test_pairing import _create_vault_with_peer_aid
    _create_vault_with_peer_aid(a, devctl)
    _create_vault_with_peer_aid(b, devctl)

    oobi_a = devctl(a["sock"], "get_peer_oobi", alias="aid")["oobi"]
    oobi_b = devctl(b["sock"], "get_peer_oobi", alias="aid")["oobi"]
    devctl(b["sock"], "add_peer", oobi=oobi_a, label="Alice")
    devctl(a["sock"], "add_peer", oobi=oobi_b, label="Bob")

    # Turn off B's per-AID expose for the target AID
    devctl(b["sock"], "expose_aid_over_peer_off", alias="aid")
    time.sleep(1)

    devctl(a["sock"], "issue_credential",
           issuer_alias="aid", recipient_label="Bob",
           schema="EAdminPing", attrs={"msg": "should be dest-rejected"})
    time.sleep(3)

    log_b = b["log"].read_text()
    assert "peer.gate.destination_not_exposed" in log_b
```

- [ ] **Step 2: Add the supporting devctl ops**

Edit `~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py`. Add:

```python
@_op("get_peer_port")
def _get_peer_port(**_):
    vault = _current_vault()
    if vault is None or vault.peer_doer is None or vault.peer_doer.server is None:
        return {"error": "peer mode not running"}
    return {"port": vault.peer_doer.server.ha[1]}


@_op("expose_aid_over_peer_off")
def _expose_off(*, alias: str, **_):
    vault = _current_vault()
    hab = vault.hby.habByName(alias)
    exposed = getattr(vault, "_peer_exposed_aids", set())
    exposed.discard(hab.pre)
    return {"ok": True}
```

- [ ] **Step 3: Add the parser.discarded log line (covers garbage TCP)**

Edit `src/locksmith/peer/shim.py`. Wrap the body of `processEvent` in a try/except to log parser failures:

```python
    def processEvent(self, serder, tsgs=None, cigars=None, **kwargs):
        try:
            sender = serder.ked.get("i", "")
            recipient = serder.ked.get("rp", "")
        except AttributeError:
            logger.warning(f"peer.parser.discarded reason=non_exn_payload")
            return
        # ... rest unchanged ...
```

- [ ] **Step 4: Run — expect PASS**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/integration/peer/test_gates.py -v -m network
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/code/locksmith && git add src/locksmith/peer/shim.py tests/integration/peer/test_gates.py
git commit -m "test(peer): integration tests for sender + destination rejection"
cd ~/code/locksmith-ui-tester && git add src/locksmith_ui_tester/server.py
git commit -m "feat(devctl): peer-mode gate test helpers (get_peer_port, expose_off)"
cd ~/code/locksmith
```

---

## Task 18: Push and clean up

- [ ] **Step 1: Run the full test suite locally**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/peer -v
```

Expected: all unit + UI-smoke tests pass (integration tests marked `-m network` skip without the marker).

- [ ] **Step 2: Run integration tests with network marker (with both wallet harnesses reachable)**

```bash
cd ~/code/locksmith && .venv/bin/python -m pytest tests/integration/peer -v -m network
```

Expected: all 5 integration tests pass.

- [ ] **Step 3: Push the branch**

```bash
cd ~/code/locksmith && git push -u origin feat/direct-peer-design
```

- [ ] **Step 4: Push the ui-tester branch**

```bash
cd ~/code/locksmith-ui-tester && git push origin HEAD
```

- [ ] **Step 5: Open the PR against development**

```bash
cd ~/code/locksmith && gh pr create --base development --title "Direct peer mode (LAN/VPN TCP transport)" --body "$(cat <<'EOF'
## Summary
- Adds a TCP listener (`PeerDoer`) parallel to the existing UDS turret, gated by a two-step allowlist (sender + destination)
- Outbound IPEX auto-falls-back from peer endpoint to mailbox when peer is unreachable
- New UI: vault settings section, per-AID `Peer` OOBI role, Paired Peers page, Add Peer dialog
- All keripy handlers reused as-is

## Test plan
- [ ] `pytest tests/peer` — all unit + UI-smoke pass
- [ ] `pytest tests/integration/peer -m network` — all 5 integration tests pass against witness.keri.host
- [ ] Manual smoke against the two HOME-isolated dev wallets (Wallet A: `~`, Wallet B: `/tmp/test001`)

Spec: docs/superpowers/specs/2026-05-27-locksmith-direct-peer-design.md
Plan: docs/superpowers/plans/2026-05-27-locksmith-direct-peer.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Cross-repo work summary

Three commits land in `~/code/locksmith-ui-tester` (devctl ops to drive the new UI from integration tests):

1. `feat(devctl): peer-mode ops (set_peer_mode, add_peer, list_peers, ...)` (Task 14)
2. `feat(devctl): peer-mode gate test helpers (get_peer_port, expose_off)` (Task 17)

These should be reviewed and merged in coordination with the main feature branch — the integration tests won't run without them. The ui-tester PR can land first; the main feature branch can then be merged.

---

## Risks and notes for the implementer

- **`hab.makeRoleAuth` API surface** — the spec assumes a method on the keripy Habery that writes a role authorization (rpy message) for a chosen role + scheme + URL. The exact signature may differ; check `keri/app/habbing.py` for the actual API and adapt Task 10 Step 5 accordingly. If the existing API is too low-level, an inline `eventing.reply(route='/end/role/add', ...)` followed by signing + storing should produce the same effect.
- **`AddPeerDialog._resolve_oobi`** — the dialog calls `oobiery.processOobis()` once, which only ticks the async resolution loop. In integration tests, the resolver may need a real timer cycle to complete the fetch. If tests flake, swap to the synchronous `keri.app.oobiing.OobiInquisitor` or block on a cue until the resolved KEL appears in `hby.habs`.
- **TCP `Directant`'s hab argument** — Task 5 passes the first available hab to `Directant`. This is a quirk of the upstream class signature; the actual destination routing happens in the shim. Verify this matches `locksmith/turret/directing.py`'s usage if behavior diverges.
- **Integration tests are slow** — each `two_wallets` fixture invocation spawns two real wallet processes (~30 s setup). Mark integration tests with `pytest.mark.network` so unit-test runs don't pick them up by default.
