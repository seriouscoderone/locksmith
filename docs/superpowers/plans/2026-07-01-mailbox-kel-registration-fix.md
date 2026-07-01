# Mailbox KEL-Registration Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A wallet AID that designates the standalone federation mailbox can subscribe and retrieve its mail, whether or not it is witnessed.

**Architecture:** Two complementary changes on the "check-and-share" principle. **Server** (keripy fork): a shared `ensure_kever(hby, pre)` helper lazy-loads a peer's key-state from the shared DynamoDB oracle on an in-memory `kevers` miss, wired into the one read/serving gate that blocks a client — the WS subscribe gate. **Client** (Locksmith): on mailbox designation, `SetRoleDoer` publishes the AID's KEL to the mailbox's HTTP endpoint via the hio-native `agenting.HTTPStreamMessenger`, introducing witness-less AIDs into the shared oracle.

**Tech Stack:** Python 3.14, keripy (fork), hio doers, AWS Lambda + DynamoDB (server); PySide6/hio (Locksmith client); pytest.

**Spec:** `docs/superpowers/specs/2026-07-01-mailbox-kel-registration-fix-design.md`

## Global Constraints

- **BE KERI NATIVE.** Kever reconstruction mirrors `Baser.reload` (`basing.py:97`); KEL publish uses `agenting.HTTPStreamMessenger` (keripy's own outbound-CESR doer). No `requests`, no threads (consistent with the hio-native WS-client direction).
- **Preserve write-path semantics.** `ensure_kever` is called ONLY at the read/serving gate (WS subscribe). NEVER on the ingest / first-seen / duplicity path — there `pre not in hby.kevers` must keep meaning "not locally first-seen."
- **keripy pushes to the fork `seriouscoderone/keripy` ONLY**, never WebOfTrust/origin.
- **The live 5-stack federation deploy is a separate, explicitly user-gated step** (the closing section), NOT part of any TDD task.
- **Locksmith tests run with `--import-mode=importlib`** against the main-checkout `.venv/bin/python`.
- **Canonical keripy edit is `src/keri/app/lambding.py`**; `keri_cdk/layers/build_layer.sh` (`pip install .`) rebuilds the Lambda layer from it before deploy.
- **Branches:** keripy `feat/mailbox-kel-lazyload` off `development`; Locksmith `feat/mailbox-kel-registration` off `development` (already created; spec committed `efa076f`). Commit per task; do not push (fork push is user-gated).

---

### Task 1: keripy — `ensure_kever` lazy-load helper

**Files:**
- Modify: `~/code/keripy/src/keri/app/lambding.py` (add `ensure_kever` after the `SHARED_KEL_STORES` block)
- Test: `~/code/keripy/tests/handlers/test_ensure_kever.py` (new)

**Interfaces:**
- Produces: `ensure_kever(hby, pre) -> Kever | None` — returns the cached Kever if `pre` is in `hby.kevers`; else rebuilds it from `hby.db.states` (the shared key-state store) and caches it; returns `None` if `pre` is unknown to the federation or its key-state has no backing KEL events on this stack.

- [ ] **Step 1: Create the keripy branch**

```bash
cd ~/code/keripy && git checkout development && git checkout -b feat/mailbox-kel-lazyload
```

- [ ] **Step 2: Write the failing tests**

Create `~/code/keripy/tests/handlers/test_ensure_kever.py`:

```python
"""Unit tests for lambding.ensure_kever — lazy-load a peer's Kever from the shared
key-state store on an in-memory kevers miss (fixes stale per-Lambda-container kevers)."""
from keri.app.habbing import Habery
from keri.app.lambding import ensure_kever
from keri.core.signing import Salter


def test_ensure_kever_returns_cached_when_in_kevers():
    hby = Habery(name="ek-hit", temp=True, salt=Salter().qb64)
    hab = hby.makeHab(name="a", transferable=True)
    assert ensure_kever(hby, hab.pre) is hby.kevers[hab.pre]
    hby.close()


def test_ensure_kever_rebuilds_from_shared_state_on_miss():
    src = Habery(name="ek-src", temp=True, salt=Salter().qb64)
    alice = src.makeHab(name="alice", transferable=True)
    server = Habery(name="ek-srv", temp=True, salt=Salter().qb64)
    server.psr.parse(ims=bytearray(alice.replay()))   # first-see: writes state + events + kever
    server.kvy.processEscrows()
    assert alice.pre in server.kevers
    del server.db.kevers[alice.pre]                    # simulate stale warm container
    assert alice.pre not in server.kevers
    kever = ensure_kever(server, alice.pre)
    assert kever is not None
    assert kever.prefixer.qb64 == alice.pre
    assert alice.pre in server.kevers                  # re-cached
    src.close()
    server.close()


def test_ensure_kever_none_when_unknown_everywhere():
    server = Habery(name="ek-unk", temp=True, salt=Salter().qb64)
    assert ensure_kever(server, "EAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA") is None
    server.close()


def test_ensure_kever_none_when_state_present_but_events_missing():
    src = Habery(name="ek-src2", temp=True, salt=Salter().qb64)
    bob = src.makeHab(name="bob", transferable=True)
    server = Habery(name="ek-srv2", temp=True, salt=Salter().qb64)
    server.db.states.pin(keys=(bob.pre,), val=bob.kever.state())  # state only, no KEL events
    assert bob.pre not in server.kevers
    assert ensure_kever(server, bob.pre) is None                  # MissingEntryError -> None
    src.close()
    server.close()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd ~/code/keripy && .venv/bin/python -m pytest tests/handlers/test_ensure_kever.py -q`
Expected: FAIL — `ImportError: cannot import name 'ensure_kever' from 'keri.app.lambding'`

- [ ] **Step 4: Implement `ensure_kever`**

Add to `~/code/keripy/src/keri/app/lambding.py` (after the `SHARED_KEL_STORES` frozenset definition):

```python
def ensure_kever(hby, pre):
    """Return the Kever for ``pre``, consulting the SHARED key-state store on an
    in-memory ``hby.kevers`` miss.

    Serverless containers load ``hby.kevers`` once at cold start and never
    refresh; the shared key-state oracle (``db.states``) may hold a peer's
    key-state written by ANY federation service. READ/serving path ONLY — never
    call this on the write / first-seen / duplicity path, where
    ``pre not in hby.kevers`` must keep meaning "not locally first-seen."

    Returns the Kever, or None if ``pre`` is unknown to the whole federation (or
    its key-state is present but this stack lacks the backing KEL events).
    """
    if pre in hby.kevers:
        return hby.kevers[pre]
    ksr = hby.db.states.get(keys=(pre,))
    if ksr is None:
        return None
    from keri.core.eventing import Kever
    from keri.kering import MissingEntryError
    try:
        kever = Kever(state=ksr, db=hby.db, local=False)   # peer AID; mirrors Baser.reload
    except MissingEntryError:
        return None            # key-state present but this stack lacks the KEL events
    hby.kevers[pre] = kever    # cache for this container's lifetime
    return kever
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd ~/code/keripy && .venv/bin/python -m pytest tests/handlers/test_ensure_kever.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
cd ~/code/keripy
git add src/keri/app/lambding.py tests/handlers/test_ensure_kever.py
git commit -m "feat(lambding): ensure_kever lazy-loads peer key-state from shared oracle

Serverless KERI services load hby.kevers once at cold start; a warm container
answers 'unknown' for an AID whose key-state IS in the shared store. ensure_kever
rebuilds the Kever from db.states on a miss (mirrors Baser.reload), guarded by
MissingEntryError. Read/serving path only — write/duplicity path untouched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: keripy — wire `ensure_kever` into the WS subscribe gate

**Files:**
- Modify: `~/code/keripy/keri_cdk/handlers/mailbox/ws_handlers.py` (add import; change the gate at line ~146)
- Test: `~/code/keripy/tests/handlers/test_ws_handlers.py` (add one regression test)

**Interfaces:**
- Consumes: `ensure_kever(hby, pre)` from Task 1.

- [ ] **Step 1: Write the failing regression test**

Append to `~/code/keripy/tests/handlers/test_ws_handlers.py` (reuses the file's existing `_make_signed_mbx_qry`, `_make_ws_event`, `WS_CONN_TABLE`, and imports `Habery`, `Salter`, `boto3`, `json`, `patch`, `mock_aws`):

```python
@mock_aws
def test_subscribe_accepts_aid_in_shared_state_but_not_in_kevers(monkeypatch):
    """Regression: a warm Lambda container's in-memory kevers is stale, but the
    AID's key-state IS in the shared store. ensure_kever must rebuild and accept."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    # AID known to the server via shared state, but popped from in-memory kevers.
    src = Habery(name="ws-src", temp=True, salt=Salter().qb64)
    alice = src.makeHab(name="alice", transferable=True)
    server = Habery(name="ws-srv", temp=True, salt=Salter().qb64)
    server.psr.parse(ims=bytearray(alice.replay()))
    server.kvy.processEscrows()
    assert alice.pre in server.kevers
    del server.db.kevers[alice.pre]                 # stale in-memory view; state persists

    recipient_pre = alice.pre
    qry_bytes = _make_signed_mbx_qry(alice, recipient_pre, {"/credential": 5})
    import base64
    qry_qb64 = base64.b64encode(qry_bytes).decode()

    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    table = ddb.create_table(
        TableName=WS_CONN_TABLE,
        KeySchema=[{"AttributeName": "connectionId", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "connectionId", "AttributeType": "S"},
            {"AttributeName": "pre", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[{
            "IndexName": "byPre",
            "KeySchema": [{"AttributeName": "pre", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
        }],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()

    conn_id = "conn-lazyload-001"
    body = json.dumps({"action": "subscribe", "qry": qry_qb64})
    event = _make_ws_event(conn_id, body=body)

    with patch("mailbox_handler._hby", server), \
         patch("mailbox_handler._initialized", True), \
         patch("mailbox_handler.init", lambda: None):
        from ws_handlers import default
        result = default(event, {})

    assert result["statusCode"] == 200, f"Expected 200, got {result}"
    item = table.get_item(Key={"connectionId": conn_id}).get("Item")
    assert item is not None and item["pre"] == recipient_pre
    assert alice.pre in server.kevers               # ensure_kever re-cached it

    src.close()
    server.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/code/keripy && .venv/bin/python -m pytest "tests/handlers/test_ws_handlers.py::test_subscribe_accepts_aid_in_shared_state_but_not_in_kevers" -q`
Expected: FAIL — the current gate `if pre not in hby.kevers:` returns statusCode 403 (AID was popped from kevers), so the `== 200` assert fails.

- [ ] **Step 3: Wire `ensure_kever` into the gate**

In `~/code/keripy/keri_cdk/handlers/mailbox/ws_handlers.py`, add near the top-level imports:

```python
from keri.app.lambding import ensure_kever
```

Then replace the gate (currently at ~line 146):

```python
    if pre not in hby.kevers:
        logger.warning("subscribe rejected: AID %s not in kevers (KEL unknown)", pre)
        return {"statusCode": 403, "error": "AID not known to this mailbox"}
```

with:

```python
    if ensure_kever(hby, pre) is None:
        logger.warning("subscribe rejected: AID %s unknown (not in kevers or shared key-state)", pre)
        return {"statusCode": 403, "error": "AID not known to this mailbox"}
```

- [ ] **Step 4: Run the new test AND the full ws-handler suite**

Run: `cd ~/code/keripy && .venv/bin/python -m pytest tests/handlers/test_ws_handlers.py -q`
Expected: PASS — the new regression passes, and every existing test (including `test_subscribe_unknown_aid_does_not_write_row` and `test_subscribe_known_aid_different_signer_is_accepted`) still passes (a genuinely-unknown AID is absent from both `kevers` and `db.states`, so `ensure_kever` returns `None` → still 403).

- [ ] **Step 5: Commit**

```bash
cd ~/code/keripy
git add keri_cdk/handlers/mailbox/ws_handlers.py tests/handlers/test_ws_handlers.py
git commit -m "fix(mailbox-ws): subscribe gate consults shared key-state via ensure_kever

A warm Lambda container's stale in-memory kevers wrongly rejected an AID whose
key-state is in the shared oracle. The subscribe gate now uses ensure_kever, so
a registered (witnessed or client-published) AID is accepted regardless of which
container serves it. Genuinely-unknown AIDs still 403.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Locksmith — `build_mailbox_kel_publisher` helper

**Files:**
- Modify: `~/code/locksmith/src/locksmith/core/remoting.py` (add `agenting` import; add module-level `build_mailbox_kel_publisher`)
- Test: `~/code/locksmith/tests/test_core_remoting.py` (add tests)

**Interfaces:**
- Produces: `build_mailbox_kel_publisher(hab, mailbox_eid) -> agenting.HTTPStreamMessenger | None` — resolves the mailbox's https (else http) URL via `hab.fetchUrl`; returns a `HTTPStreamMessenger` that PUTs `hab.replay()` to that endpoint, or `None` if no http(s) URL is resolvable.

- [ ] **Step 1: Confirm the Locksmith branch**

```bash
cd ~/code/locksmith && git rev-parse --abbrev-ref HEAD
```
Expected: `feat/mailbox-kel-registration` (created earlier; spec committed `efa076f`).

- [ ] **Step 2: Write the failing tests**

Append to `~/code/locksmith/tests/test_core_remoting.py`:

```python
def test_build_mailbox_kel_publisher_uses_https_and_replay(monkeypatch):
    from locksmith.core import remoting
    from keri import kering

    captured = {}

    class FakeMessenger:
        def __init__(self, *, hab, wit, url, msg):
            captured.update(hab=hab, wit=wit, url=url, msg=bytes(msg))

    class FakeHab:
        def fetchUrl(self, eid, scheme="http"):
            return "https://mailbox.example/" if scheme == kering.Schemes.https else "http://mailbox.example/"
        def replay(self, pre=None, fn=0):
            return b"KELBYTES"

    monkeypatch.setattr(remoting.agenting, "HTTPStreamMessenger", FakeMessenger)
    hab = FakeHab()
    result = remoting.build_mailbox_kel_publisher(hab, "EMBX")
    assert isinstance(result, FakeMessenger)
    assert captured["wit"] == "EMBX"
    assert captured["url"] == "https://mailbox.example/"   # https preferred
    assert captured["msg"] == b"KELBYTES"


def test_build_mailbox_kel_publisher_falls_back_to_http(monkeypatch):
    from locksmith.core import remoting
    from keri import kering

    captured = {}

    class FakeMessenger:
        def __init__(self, *, hab, wit, url, msg):
            captured["url"] = url

    class FakeHab:
        def fetchUrl(self, eid, scheme="http"):
            return "http://mailbox.example/" if scheme == kering.Schemes.http else None
        def replay(self, pre=None, fn=0):
            return b"KEL"

    monkeypatch.setattr(remoting.agenting, "HTTPStreamMessenger", FakeMessenger)
    remoting.build_mailbox_kel_publisher(FakeHab(), "EMBX")
    assert captured["url"] == "http://mailbox.example/"


def test_build_mailbox_kel_publisher_none_when_no_url(monkeypatch):
    from locksmith.core import remoting

    class FakeMessenger:
        def __init__(self, **kw):
            raise AssertionError("must not construct a messenger when no URL")

    class FakeHab:
        def fetchUrl(self, eid, scheme="http"):
            return None
        def replay(self, pre=None, fn=0):
            return b""

    monkeypatch.setattr(remoting.agenting, "HTTPStreamMessenger", FakeMessenger)
    assert remoting.build_mailbox_kel_publisher(FakeHab(), "EMBX") is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd ~/code/locksmith && .venv/bin/python -m pytest tests/test_core_remoting.py -q --import-mode=importlib -k build_mailbox_kel_publisher`
Expected: FAIL — `AttributeError: module 'locksmith.core.remoting' has no attribute 'build_mailbox_kel_publisher'` (and `remoting.agenting` does not exist yet).

- [ ] **Step 4: Implement the helper**

In `~/code/locksmith/src/locksmith/core/remoting.py`, add `agenting` to the keripy-app import (line 19):

```python
from keri.app import organizing, forwarding, agenting
```

Then add the module-level function (near the other module helpers, above `class SetRoleDoer`):

```python
def build_mailbox_kel_publisher(hab, mailbox_eid):
    """Return a hio DoDoer that PUTs ``hab``'s full KEL to ``mailbox_eid``'s HTTP
    endpoint so the mailbox first-sees it into its key-state.

    Standalone federation mailboxes are NOT witnesses, so an AID's KEL never
    reaches them via witnessing; publishing it here lets the mailbox's subscribe
    gate recognize the AID (see the 2026-07-01 mailbox KEL-registration design).

    Returns an ``agenting.HTTPStreamMessenger`` (a DoDoer the caller extends onto
    its own doer set and drives until ``.done``), or ``None`` if the mailbox has
    no resolvable http(s) endpoint.
    """
    url = (hab.fetchUrl(mailbox_eid, scheme=kering.Schemes.https)
           or hab.fetchUrl(mailbox_eid, scheme=kering.Schemes.http))
    if not url:
        return None
    return agenting.HTTPStreamMessenger(
        hab=hab, wit=mailbox_eid, url=url, msg=bytearray(hab.replay()))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd ~/code/locksmith && .venv/bin/python -m pytest tests/test_core_remoting.py -q --import-mode=importlib -k build_mailbox_kel_publisher`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
cd ~/code/locksmith
git add src/locksmith/core/remoting.py tests/test_core_remoting.py
git commit -m "feat(remoting): build_mailbox_kel_publisher (publish KEL to standalone mailbox)

A standalone federation mailbox is not a witness, so an AID's KEL never reaches
it via witnessing. This helper builds a hio-native HTTPStreamMessenger that PUTs
the hab's replay() KEL to the mailbox's http(s) endpoint (https preferred), or
None if unreachable. Wired into SetRoleDoer in the next task.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Locksmith — publish the KEL on mailbox designation in `SetRoleDoer`

**Files:**
- Modify: `~/code/locksmith/src/locksmith/core/remoting.py` (`SetRoleDoer`: add `_maybe_publish_mailbox_kel` generator method; call it from `set_role_do`)
- Test: `~/code/locksmith/tests/test_core_remoting.py` (add tests)

**Interfaces:**
- Consumes: `build_mailbox_kel_publisher(hab, mailbox_eid)` from Task 3.
- Produces: `SetRoleDoer._maybe_publish_mailbox_kel(self, hab)` — a generator; when `self.role == Roles.mailbox`, builds the publisher, extends it onto the doer, yields until done, then removes it; a no-op generator for other roles; non-fatal on error.

- [ ] **Step 1: Write the failing tests**

Append to `~/code/locksmith/tests/test_core_remoting.py`:

```python
def test_maybe_publish_mailbox_kel_extends_publisher_for_mailbox_role(monkeypatch):
    from locksmith.core import remoting

    class FakePub:
        done = True                       # completes on first check → loop body not entered

    calls = {"build": [], "extend": [], "remove": []}
    monkeypatch.setattr(remoting, "build_mailbox_kel_publisher",
                        lambda hab, eid: (calls["build"].append((hab, eid)) or FakePub()))

    class FakeSelf:
        role = remoting.Roles.mailbox
        remote_id_pre = "EMBX"
        tock = 0.0
        def extend(self, doers): calls["extend"].append(doers)
        def remove(self, doers): calls["remove"].append(doers)

    gen = remoting.SetRoleDoer._maybe_publish_mailbox_kel(FakeSelf(), hab="HAB")
    list(gen)                             # drive the generator to completion

    assert calls["build"] == [("HAB", "EMBX")]
    assert len(calls["extend"]) == 1 and isinstance(calls["extend"][0][0], FakePub)
    assert len(calls["remove"]) == 1


def test_maybe_publish_mailbox_kel_noop_for_non_mailbox_role(monkeypatch):
    from locksmith.core import remoting

    called = []
    monkeypatch.setattr(remoting, "build_mailbox_kel_publisher",
                        lambda hab, eid: called.append((hab, eid)))

    class FakeSelf:
        role = remoting.Roles.gateway
        remote_id_pre = "EMBX"
        tock = 0.0
        def extend(self, doers): raise AssertionError("must not extend for non-mailbox role")
        def remove(self, doers): raise AssertionError("must not remove for non-mailbox role")

    gen = remoting.SetRoleDoer._maybe_publish_mailbox_kel(FakeSelf(), hab="HAB")
    list(gen)
    assert called == []                   # builder never invoked for gateway


def test_maybe_publish_mailbox_kel_non_fatal_when_no_publisher(monkeypatch):
    from locksmith.core import remoting
    monkeypatch.setattr(remoting, "build_mailbox_kel_publisher", lambda hab, eid: None)

    class FakeSelf:
        role = remoting.Roles.mailbox
        remote_id_pre = "EMBX"
        tock = 0.0
        def extend(self, doers): raise AssertionError("no publisher → nothing to extend")
        def remove(self, doers): raise AssertionError("no publisher → nothing to remove")

    gen = remoting.SetRoleDoer._maybe_publish_mailbox_kel(FakeSelf(), hab="HAB")
    list(gen)                             # completes without raising
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/code/locksmith && .venv/bin/python -m pytest tests/test_core_remoting.py -q --import-mode=importlib -k maybe_publish_mailbox_kel`
Expected: FAIL — `AttributeError: type object 'SetRoleDoer' has no attribute '_maybe_publish_mailbox_kel'`.

- [ ] **Step 3: Add the generator method + call it from `set_role_do`**

In `~/code/locksmith/src/locksmith/core/remoting.py`, add this method to `SetRoleDoer`:

```python
    def _maybe_publish_mailbox_kel(self, hab):
        """Generator: for a mailbox designation, PUT the hab's KEL to the mailbox
        so it enters the mailbox's key-state (a standalone mailbox is not a
        witness, so the KEL never arrives via witnessing). Non-fatal — the
        end-role is already written; a publish failure is logged and skipped.
        Caller drives with ``yield from``."""
        if self.role != Roles.mailbox:
            return
        try:
            pub = build_mailbox_kel_publisher(hab, self.remote_id_pre)
            if pub is None:
                logger.warning("mailbox %s has no http(s) endpoint; skipping KEL publish",
                               self.remote_id_pre)
                return
            self.extend([pub])
            while not pub.done:
                yield self.tock
            self.remove([pub])
            logger.info("published KEL to mailbox %s", self.remote_id_pre)
        except Exception as ex:  # noqa: BLE001 — publish must never break role-setting
            logger.warning("mailbox KEL publish to %s failed: %s", self.remote_id_pre, ex)
```

Then, in `set_role_do`, after the existing `while not hab.loadEndRole(cid=hab.pre, role=self.role, eid=self.remote_id_pre): yield self.tock` loop and before the `StreamPoster` block, add:

```python
            yield from self._maybe_publish_mailbox_kel(hab)
```

(`Roles` is already imported in `remoting.py`; `logger` already exists.)

- [ ] **Step 4: Run the new tests AND the full remoting suite**

Run: `cd ~/code/locksmith && .venv/bin/python -m pytest tests/test_core_remoting.py -q --import-mode=importlib`
Expected: PASS — the 3 new `_maybe_publish_mailbox_kel` tests and the 3 `build_mailbox_kel_publisher` tests pass; all pre-existing `test_core_remoting.py` tests still pass (the new `yield from` is a no-op for non-mailbox roles).

- [ ] **Step 5: Commit**

```bash
cd ~/code/locksmith
git add src/locksmith/core/remoting.py tests/test_core_remoting.py
git commit -m "feat(remoting): SetRoleDoer publishes AID KEL on mailbox designation

When a mailbox end-role is set, PUT the AID's KEL to the mailbox (via
build_mailbox_kel_publisher) so the mailbox recognizes the AID at subscribe.
Non-fatal on failure; no-op for non-mailbox roles.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Deploy & E2E (user-gated — NOT a TDD task)

Do this only after the four tasks are merged and **only with explicit user approval** — it touches the live 5-stack federation.

- [ ] **Rebuild the layer** so it carries `ensure_kever`:
  `cd ~/code/keripy/keri_cdk/layers && ./build_layer.sh`
- [ ] **Deploy the server change** to the 5 Mailbox stacks BY NAME (never `--all`; witnesses untouched):
  `AWS_PROFILE=personal` · `npx aws-cdk@latest deploy MailboxKeriHost MailboxHonestTown MailboxVerdaderoMe MailboxGooneiCom MailboxLegitimUs --app "$HOME/code/keripy/.venv/bin/python app.py" --require-approval never`
- [ ] **Relaunch the dev-build wallet** (`cd ~/code/locksmith && .venv/bin/python -m locksmith.main`) so the client change is loaded.
- [ ] **E2E:** in the Carrier vault, re-designate the mailbox (Remotes → Set Role → Mailbox) to publish the KEL; reopen the vault so the poller mounts; run the `fullloop_hio.py`-pattern signed `/fwd` deposit to the Carrier's `/credential`; confirm retrieval in the wallet log (`Library/Application Support/Locksmith/logs/locksmith_update.log` — a drained event logs `[hio.help.ogling] INFO AID <pre>: Added to KEL`).

---

## Self-Review

**Spec coverage:**
- Spec Part 2 (server `ensure_kever` + wire into the one real gate) → Tasks 1–2. ✅ (Spec's "3 sites" was corrected to 1 during planning; `/oobi` is own-AID-only, `_ingest` mbx path is ungated.)
- Spec Part 1 (client publish via `HTTPStreamMessenger`, mailbox-role-only, idempotent, non-fatal) → Tasks 3–4. ✅
- Spec testing (server unit hit/miss/none/MissingEntryError; subscribe accepts state-only AID; client builder + wiring + non-mailbox + unreachable) → Task 1 Step 2, Task 2 Step 1, Task 3 Step 2, Task 4 Step 1. ✅
- Spec deploy gating → the closing user-gated section. ✅

**Placeholder scan:** none — every code/test step has complete code and exact run commands.

**Type consistency:** `ensure_kever(hby, pre) -> Kever|None` (Task 1) is consumed by Task 2's gate as `ensure_kever(hby, pre) is None`. `build_mailbox_kel_publisher(hab, mailbox_eid) -> HTTPStreamMessenger|None` (Task 3) is consumed by Task 4 as `build_mailbox_kel_publisher(hab, self.remote_id_pre)`; the returned object exposes `.done` (used in the `while not pub.done` loop) — consistent with `HTTPStreamMessenger` being a `doing.DoDoer` (has `.done`). `hab.fetchUrl(eid, scheme)` and `hab.replay()` signatures match keripy.
