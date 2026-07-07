# schema.keri.host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship schema.keri.host — a trustless `GET /oobi/<said>` schema host (S3+CloudFront) plus a gated `publish_schema` Service-AID whose store-artifact effect persists a schema to a CAS and records each publication as a KEL-anchored TEL-registry ledger, with an optional `publication_receipt` ACDC.

**Architecture:** Extend the `keri_serviceaid` framework with a configurable **store-artifact** effect (a new `Reply.publish` kind + an injectable `ArtifactStore` provider + a `publish` pipeline branch), reusing the existing `IpexGrantIssuer` (TEL registry) to mint the receipt. First-seen is a serializable DynamoDB conditional write. Package the service in `examples/schema_host/` and deploy it via a new `SchemaHostStack` (ServiceAidFunction + S3 CAS + CloudFront path-routed at schema.keri.host).

**Tech Stack:** Python 3.14, keripy fork (`~/code/keripy`), `keri_serviceaid`, `keri_cdk` (aws-cdk-lib), boto3/moto, pytest, DynamoDB (shared keri-core table), S3, CloudFront.

**Spec:** `docs/superpowers/specs/2026-07-07-schema-keri-host-design.md` (in the locksmith repo).

## Global Constraints

- **Repo:** ALL code lands in the **keripy fork** at `/Users/seriouscoderone/code/keripy`. Locksmith is untouched.
- **Branch:** one feature branch off `development` (e.g. `feat/schema-keri-host`). Commit per task; **do not push** without explicit approval. keripy pushes go to the **seriouscoderone fork only**, never WebOfTrust.
- **Test command (framework/service, hermetic):** `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest <path> -v` using the keripy venv interpreter. The hermetic suite MUST stay green and MUST NOT require AWS.
- **Test command (cloud):** cloud tests use `moto`'s `mock_aws` and are marked/named so they can be excluded from the hermetic run (mirror `tests/serviceaid/test_providers_idempotency.py`). Never require live AWS in a unit test.
- **KERI-native (LAW):** attribution/ordering/provenance use KERI primitives only — KEL anchoring, ACDC, TEL registry, IPEX, OOBI. Storage layers expose generic verbs; protocol meaning is composed one layer up (no concept leak into storage).
- **Scope:** ACDC **schemas only** (engine SAD-general; validator asserts a JSON Schema whose `$id == SAID`); **never** private ACDC instances. Wallet client-side resolution is out of scope.
- **No `Date.now()` concerns:** this is real service/Lambda code (not a Workflow script) — `helping.nowIso8601()` is available and correct for server-stamped `dt`.

## File Structure

**keripy framework (`keri_serviceaid/`):**
- `contract.py` (MODIFY) — add `Reply.publish` kind + fields; add `artifact_store` param to `ServiceAid.__init__`.
- `providers/artifact_store.py` (CREATE) — `ArtifactStore` Protocol, `FirstSeenResult`, `LocalArtifactStore`, `S3ArtifactStore`.
- `pipeline.py` (MODIFY) — add the `reply.kind == "publish"` branch.
- `runtime.py` (MODIFY) — wire `S3ArtifactStore` default (cloud).
- `local_runtime.py` (MODIFY) — wire `LocalArtifactStore` default (in-wallet/tests).
- `config.py` (MODIFY) — add `cas_bucket` + `pub_namespace`.

**keripy core (`src/keri/db/`):**
- `dynamodbing.py` (MODIFY) — add a public `claimFirstSeen(...)` conditional write.

**keripy CDK (`keri_cdk/`):**
- `schema_host_stack.py` (CREATE) — S3 CAS bucket + CloudFront (S3 origin `/oobi/*` + APIGW origin for the write route) + OAC + ACM + Route53.

**keripy ecosystem app (`examples/schema_host/`):**
- `schema_host_handler.py` (CREATE) — `svc = ServiceAid(...)` + `validate_public_schema` + the `/schema/cmd/publish` command.
- `schema/publication_receipt.json` (CREATE) — the receipt ACDC schema.
- `app.py` (CREATE) — CDK app: KeriCoreStack + ServiceAidFunction + SchemaHostStack, grant S3 write, pass CAS bucket env.
- `DEPLOY_RUNBOOK.md` (CREATE) — live-deploy gate validation.

**Tests (`tests/serviceaid/`, `tests/cdk/`):**
- `test_reply_publish.py`, `test_artifact_store.py`, `test_pipeline_publish_e2e.py`, `test_s3_artifact_store.py` (moto), `test_schema_host_handler.py`, `tests/cdk/test_schema_host_stack.py`.

---

### Task 1: `Reply.publish` kind + fields

**Files:**
- Modify: `keri_serviceaid/contract.py` (the `Reply` dataclass, ~lines 28–57)
- Test: `tests/serviceaid/test_reply_publish.py`

**Interfaces:**
- Consumes: nothing (leaf).
- Produces: `Reply.publish(*, recipient: str, artifact_said: str, artifact_bytes: bytes, attributes: dict, want_receipt: bool = False, edges: dict | None = None, rules: dict | None = None) -> Reply` with `kind == "publish"`; new `Reply` fields `artifact_said: Optional[str]`, `artifact_bytes: Optional[bytes]`, `want_receipt: bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/serviceaid/test_reply_publish.py
from keri_serviceaid import Reply


def test_publish_reply_carries_artifact_and_receipt_flag():
    r = Reply.publish(recipient="ERecip", artifact_said="ESchemaSaid",
                      artifact_bytes=b'{"$id":"ESchemaSaid"}',
                      attributes={"schemaSaid": "ESchemaSaid"}, want_receipt=True)
    assert r.kind == "publish"
    assert r.recipient == "ERecip"
    assert r.artifact_said == "ESchemaSaid"
    assert r.artifact_bytes == b'{"$id":"ESchemaSaid"}'
    assert r.attributes == {"schemaSaid": "ESchemaSaid"}
    assert r.want_receipt is True


def test_publish_reply_defaults_want_receipt_false():
    r = Reply.publish(recipient="ERecip", artifact_said="EX",
                      artifact_bytes=b"{}", attributes={})
    assert r.want_receipt is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_reply_publish.py -v`
Expected: FAIL — `AttributeError: type object 'Reply' has no attribute 'publish'`.

- [ ] **Step 3: Add the fields + classmethod to `Reply`**

In `keri_serviceaid/contract.py`, add three fields to the `Reply` dataclass (after `schema_said`):

```python
    schema_said: Optional[str] = None
    artifact_said: Optional[str] = None
    artifact_bytes: Optional[bytes] = None
    want_receipt: bool = False
```

And add this classmethod to `Reply` (after `revoke`):

```python
    @classmethod
    def publish(cls, *, recipient: str, artifact_said: str, artifact_bytes: bytes,
                attributes: dict, want_receipt: bool = False,
                edges: dict | None = None, rules: dict | None = None) -> "Reply":
        """Store a public SAD artifact (by SAID) and record its publication.
        The framework runs the ArtifactStore effect, then issues an optional
        `publication_receipt` ACDC (delivered iff `want_receipt`)."""
        return cls(kind="publish", recipient=recipient, attributes=attributes,
                   edges=edges, rules=rules, artifact_said=artifact_said,
                   artifact_bytes=artifact_bytes, want_receipt=want_receipt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_reply_publish.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add keri_serviceaid/contract.py tests/serviceaid/test_reply_publish.py
git commit -m "feat(serviceaid): add Reply.publish kind for store-artifact effect"
```

---

### Task 2: `ArtifactStore` provider — Protocol, `FirstSeenResult`, `LocalArtifactStore`

**Files:**
- Create: `keri_serviceaid/providers/artifact_store.py`
- Test: `tests/serviceaid/test_artifact_store.py`

**Interfaces:**
- Consumes: nothing (leaf, in-memory).
- Produces:
  - `@dataclass FirstSeenResult(created: bool, first_seen: bool, first_publisher: str, first_at: str)`
  - `ArtifactStore` Protocol: `store(self, said: str, raw: bytes, by: str) -> FirstSeenResult`
  - `LocalArtifactStore()` — in-memory, thread-safe; idempotent by SAID; serializable first-seen.

- [ ] **Step 1: Write the failing test**

```python
# tests/serviceaid/test_artifact_store.py
import threading

from keri_serviceaid.providers.artifact_store import LocalArtifactStore, FirstSeenResult


def test_first_publisher_is_first_seen():
    store = LocalArtifactStore()
    r = store.store("ESaid", b'{"$id":"ESaid"}', by="EAlice")
    assert isinstance(r, FirstSeenResult)
    assert r.first_seen is True
    assert r.first_publisher == "EAlice"
    assert store.get("ESaid") == b'{"$id":"ESaid"}'


def test_second_publisher_is_not_first_and_reports_prior():
    store = LocalArtifactStore()
    store.store("ESaid", b'{"$id":"ESaid"}', by="EAlice")
    r = store.store("ESaid", b'{"$id":"ESaid"}', by="EBob")
    assert r.first_seen is False
    assert r.first_publisher == "EAlice"   # the prior contributor


def test_concurrent_claims_yield_exactly_one_first_seen():
    store = LocalArtifactStore()
    results = []
    barrier = threading.Barrier(8)

    def claim(aid):
        barrier.wait()
        results.append(store.store("ESaid", b"{}", by=aid))

    threads = [threading.Thread(target=claim, args=(f"E{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(1 for r in results if r.first_seen) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_artifact_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keri_serviceaid.providers.artifact_store'`.

- [ ] **Step 3: Write the provider**

```python
# keri_serviceaid/providers/artifact_store.py
"""ArtifactStore: the store-artifact effect for a publish command.

A configurable capability that persists a public SAD (keyed by SAID) to a
content-addressed store AND claims serializable first-seen (which AID published
this SAID here first). Two impls: LocalArtifactStore (in-memory, tests) and
S3ArtifactStore (S3 CAS + DynamoDB conditional first-seen). The store is a
generic verb; the "first publisher" meaning is composed by the pipeline."""
import threading
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from keri.help import helping


@dataclass
class FirstSeenResult:
    created: bool           # True if this call wrote the bytes for the first time
    first_seen: bool        # True if `by` is the first publisher of this SAID here
    first_publisher: str    # the AID that first published this SAID (== by if first_seen)
    first_at: str           # ISO-8601 timestamp of the first publication


@runtime_checkable
class ArtifactStore(Protocol):
    def store(self, said: str, raw: bytes, by: str) -> FirstSeenResult:
        """Persist `raw` under `said` (idempotent) and claim first-seen for `by`."""
        ...


class LocalArtifactStore:
    """In-memory, thread-safe ArtifactStore for the local runtime + tests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._blobs: dict[str, bytes] = {}
        self._first: dict[str, tuple[str, str]] = {}   # said -> (publisher, dt)

    def store(self, said: str, raw: bytes, by: str) -> FirstSeenResult:
        with self._lock:
            created = said not in self._blobs
            self._blobs[said] = bytes(raw)
            if said not in self._first:
                dt = helping.nowIso8601()
                self._first[said] = (by, dt)
                return FirstSeenResult(created=created, first_seen=True,
                                       first_publisher=by, first_at=dt)
            publisher, dt = self._first[said]
            return FirstSeenResult(created=created, first_seen=False,
                                   first_publisher=publisher, first_at=dt)

    def get(self, said: str) -> bytes | None:
        return self._blobs.get(said)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_artifact_store.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add keri_serviceaid/providers/artifact_store.py tests/serviceaid/test_artifact_store.py
git commit -m "feat(serviceaid): ArtifactStore provider + LocalArtifactStore (in-memory first-seen)"
```

---

### Task 3: `DynamoDBer.claimFirstSeen` — public conditional write

**Files:**
- Modify: `src/keri/db/dynamodbing.py` (add a public method near `_put_item`)
- Test: `tests/serviceaid/test_dynamo_claim_first_seen.py` (moto/cloud)

**Interfaces:**
- Consumes: the existing private `_put_item(db, key, sk, val, *, condition=None, gsi_sk=None) -> bool` (returns False on `ConditionalCheckFailedException`), and `_get_val`/`getVal`-style reads.
- Produces: `DynamoDBer.claimFirstSeen(self, name: str, key: bytes, val: bytes) -> tuple[bool, bytes | None]` — attempts a conditional put into sub-db `name`; returns `(True, None)` if claimed, `(False, existing_bytes)` if a prior claim exists.

- [ ] **Step 1: Write the failing test**

```python
# tests/serviceaid/test_dynamo_claim_first_seen.py
import boto3
import pytest
from moto import mock_aws

from keri.db.dynamodbing import DynamoDBer

PUB_STORE = "pub."


@pytest.fixture
def db():
    with mock_aws():
        boto3.client("dynamodb", region_name="us-east-1")
        d = DynamoDBer.open(name="pub", stores=[PUB_STORE],
                            table_name="keri-core", namespace="schema-publisher:pub",
                            region="us-east-1")
        yield d
        d.close()


def test_first_claim_wins_second_reads_existing(db):
    ok, existing = db.claimFirstSeen(PUB_STORE, b"ESaid", b"EAlice")
    assert ok is True and existing is None
    ok2, existing2 = db.claimFirstSeen(PUB_STORE, b"ESaid", b"EBob")
    assert ok2 is False
    assert existing2 == b"EAlice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_dynamo_claim_first_seen.py -v`
Expected: FAIL — `AttributeError: 'DynamoDBer' object has no attribute 'claimFirstSeen'`.

- [ ] **Step 3: Add the method**

In `src/keri/db/dynamodbing.py`, add to the `DynamoDBer` class (the sub-db handle is obtained the same way other public methods obtain it — mirror an existing `setVal`/`getVal` method for how `name` maps to a `DynamoSubDb`; reuse `_put_item`'s `condition` path and the existing point-read):

```python
    def claimFirstSeen(self, name, key, val):
        """Serializable first-seen claim in sub-db `name`.

        Conditional put (attribute_not_exists) of `val` under `key`. Returns
        (True, None) if this call claimed it; (False, existing_bytes) if a prior
        claim exists. `val` is the claimant identity (e.g. the publisher AID as
        bytes); a generic verb — the caller composes the "first publisher" meaning."""
        subdb = self._subdbs[name]                      # same lookup setVal uses
        sk = self._sk(subdb, key)                       # same sort-key derivation as setVal
        claimed = self._put_item(subdb, key, sk, bytes(val),
                                 condition="attribute_not_exists(PK)")
        if claimed:
            return True, None
        existing = self.getVal(name, key)               # point read (strongly consistent)
        return False, (bytes(existing) if existing is not None else None)
```

> Implementer note: confirm the exact sub-db lookup (`self._subdbs[name]`), sort-key helper (`self._sk(...)`), and point-read (`self.getVal(name, key)`) against the real `DynamoDBer` — mirror whatever `setVal`/`getVal` use. The `_put_item(..., condition="attribute_not_exists(PK)")` returning `False` on `ConditionalCheckFailedException` is the verbatim behavior surveyed at `dynamodbing.py:404-424`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_dynamo_claim_first_seen.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add src/keri/db/dynamodbing.py tests/serviceaid/test_dynamo_claim_first_seen.py
git commit -m "feat(db): DynamoDBer.claimFirstSeen conditional-write primitive"
```

---

### Task 4: `S3ArtifactStore` — S3 CAS + DynamoDB first-seen

**Files:**
- Modify: `keri_serviceaid/providers/artifact_store.py` (add `S3ArtifactStore`)
- Test: `tests/serviceaid/test_s3_artifact_store.py` (moto/cloud)

**Interfaces:**
- Consumes: `FirstSeenResult` (Task 2), `DynamoDBer.claimFirstSeen` (Task 3), boto3 S3 client.
- Produces: `S3ArtifactStore(bucket: str, db, *, store_name: str = "pub.", key_prefix: str = "oobi/", s3=None)` implementing `ArtifactStore`. Writes S3 object `f"{key_prefix}{said}"` with `ContentType="application/schema+json"`; claims first-seen via `db.claimFirstSeen`.

- [ ] **Step 1: Write the failing test**

```python
# tests/serviceaid/test_s3_artifact_store.py
import boto3
import pytest
from moto import mock_aws

from keri.db.dynamodbing import DynamoDBer
from keri_serviceaid.providers.artifact_store import S3ArtifactStore

PUB_STORE = "pub."


@pytest.fixture
def env():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="schema-cas")
        boto3.client("dynamodb", region_name="us-east-1")
        db = DynamoDBer.open(name="pub", stores=[PUB_STORE], table_name="keri-core",
                             namespace="schema-publisher:pub", region="us-east-1")
        yield s3, db
        db.close()


def test_store_writes_cas_object_and_claims_first_seen(env):
    s3, db = env
    store = S3ArtifactStore(bucket="schema-cas", db=db)
    r = store.store("ESaid", b'{"$id":"ESaid"}', by="EAlice")
    assert r.first_seen is True and r.first_publisher == "EAlice"
    obj = s3.get_object(Bucket="schema-cas", Key="oobi/ESaid")
    assert obj["Body"].read() == b'{"$id":"ESaid"}'
    assert obj["ContentType"] == "application/schema+json"


def test_second_publisher_not_first(env):
    s3, db = env
    store = S3ArtifactStore(bucket="schema-cas", db=db)
    store.store("ESaid", b'{"$id":"ESaid"}', by="EAlice")
    r = store.store("ESaid", b'{"$id":"ESaid"}', by="EBob")
    assert r.first_seen is False and r.first_publisher == "EAlice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_s3_artifact_store.py -v`
Expected: FAIL — `ImportError: cannot import name 'S3ArtifactStore'`.

- [ ] **Step 3: Add `S3ArtifactStore`**

Append to `keri_serviceaid/providers/artifact_store.py`:

```python
import boto3


class S3ArtifactStore:
    """Prod ArtifactStore: S3 CAS (object key `<key_prefix><said>`,
    Content-Type application/schema+json) + serializable first-seen via a
    DynamoDBer conditional write in the service's `pub` namespace."""

    def __init__(self, bucket: str, db, *, store_name: str = "pub.",
                 key_prefix: str = "oobi/", s3=None):
        self.bucket = bucket
        self.db = db
        self.store_name = store_name
        self.key_prefix = key_prefix
        self._s3 = s3 or boto3.client("s3")

    def store(self, said: str, raw: bytes, by: str) -> FirstSeenResult:
        # Idempotent by SAID: same content = same bytes; overwriting is a no-op.
        self._s3.put_object(Bucket=self.bucket, Key=f"{self.key_prefix}{said}",
                            Body=bytes(raw), ContentType="application/schema+json")
        claimed, existing = self.db.claimFirstSeen(
            self.store_name, said.encode("utf-8"), by.encode("utf-8"))
        if claimed:
            return FirstSeenResult(created=True, first_seen=True,
                                   first_publisher=by, first_at=helping.nowIso8601())
        prior = existing.decode("utf-8") if existing else ""
        return FirstSeenResult(created=False, first_seen=False,
                               first_publisher=prior, first_at="")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_s3_artifact_store.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add keri_serviceaid/providers/artifact_store.py tests/serviceaid/test_s3_artifact_store.py
git commit -m "feat(serviceaid): S3ArtifactStore (S3 CAS + DynamoDB first-seen)"
```

---

### Task 5: `config.py` — CAS bucket + pub namespace

**Files:**
- Modify: `keri_serviceaid/config.py` (add env-derived `cas_bucket` + `pub_namespace` property)
- Test: `tests/serviceaid/test_config_cas.py`

**Interfaces:**
- Consumes: existing `Config` (has `alias`, `core_table`, env-parsing pattern like `keeper_secret`).
- Produces: `Config.cas_bucket` (from `SERVICEAID_CAS_BUCKET`, default `""`) and `Config.pub_namespace` property → `f"{alias}:pub"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/serviceaid/test_config_cas.py
from keri_serviceaid.config import Config


def test_pub_namespace_derived_from_alias():
    cfg = Config(alias="schema-publisher", core_table="keri-core",
                 keeper_secret="keri/schema-publisher/keeper", region="us-east-1")
    assert cfg.pub_namespace == "schema-publisher:pub"


def test_cas_bucket_from_env(monkeypatch):
    monkeypatch.setenv("SERVICEAID_CAS_BUCKET", "my-schema-cas")
    monkeypatch.setenv("SERVICEAID_ALIAS", "schema-publisher")
    monkeypatch.setenv("SERVICEAID_CORE_TABLE", "keri-core")
    monkeypatch.setenv("SERVICEAID_KEEPER_SECRET", "keri/schema-publisher/keeper")
    monkeypatch.setenv("SERVICEAID_REGION", "us-east-1")
    cfg = Config.from_env()
    assert cfg.cas_bucket == "my-schema-cas"
```

> Implementer note: match `Config`'s real construction (it may be a dataclass with `from_env()`); read `config.py` and mirror the existing field pattern. If `Config` requires other fields, provide them in the test with the same defaults `from_env` uses.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_config_cas.py -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'pub_namespace'` (and no `cas_bucket`).

- [ ] **Step 3: Add the field + property**

In `keri_serviceaid/config.py`, add a `cas_bucket: str = ""` field, populate it in `from_env()` (`os.environ.get("SERVICEAID_CAS_BUCKET", "")`), and add:

```python
    @property
    def pub_namespace(self) -> str:
        return f"{self.alias}:pub"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_config_cas.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add keri_serviceaid/config.py tests/serviceaid/test_config_cas.py
git commit -m "feat(serviceaid): config cas_bucket + pub_namespace"
```

---

### Task 6: `ServiceAid.artifact_store` param + default wiring

**Files:**
- Modify: `keri_serviceaid/contract.py` (`ServiceAid.__init__`)
- Modify: `keri_serviceaid/runtime.py` (`_wire_default_providers` + `init` — cloud default `S3ArtifactStore`)
- Modify: `keri_serviceaid/local_runtime.py` (`LocalRuntime.__init__` — local default `LocalArtifactStore`)
- Test: `tests/serviceaid/test_artifact_store_wiring.py`

**Interfaces:**
- Consumes: `LocalArtifactStore`/`S3ArtifactStore` (Tasks 2/4), `Config.cas_bucket`/`pub_namespace` (Task 5).
- Produces: `ServiceAid.artifact_store` attribute (default `None`); `LocalRuntime` sets `svc.artifact_store = LocalArtifactStore()` when `None`; cloud `init()` sets `svc.artifact_store = S3ArtifactStore(bucket=cfg.cas_bucket, db=<pub-ns DynamoDBer>)` when `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/serviceaid/test_artifact_store_wiring.py
from keri.app import habbing
from keri.core.signing import Salter
from keri.vdr import credentialing

from keri_serviceaid import ServiceAid
from keri_serviceaid.local_runtime import LocalRuntime
from keri_serviceaid.providers.artifact_store import LocalArtifactStore


def test_service_aid_accepts_artifact_store():
    svc = ServiceAid(alias="schema-publisher", artifact_store=LocalArtifactStore())
    assert isinstance(svc.artifact_store, LocalArtifactStore)


def test_local_runtime_wires_default_local_artifact_store():
    hby = habbing.Habery(name="svc", temp=True, salt=Salter(raw=b'0123456789abcdef').qb64)
    hab = hby.makeHab(name="schema-publisher")
    rgy = credentialing.Regery(hby=hby, name="schema-publisher", temp=True)
    svc = ServiceAid(alias="schema-publisher")
    LocalRuntime(svc, hby=hby, hab=hab, rgy=rgy)
    assert isinstance(svc.artifact_store, LocalArtifactStore)
    hby.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_artifact_store_wiring.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'artifact_store'`.

- [ ] **Step 3: Add the param + wiring**

In `contract.py` `ServiceAid.__init__` signature, add `artifact_store=None` (after `idempotency=None`) and `self.artifact_store = artifact_store`.

In `local_runtime.py` `LocalRuntime.__init__`, after the `idempotency` wiring block, add:

```python
        if svc.artifact_store is None:
            from keri_serviceaid.providers.artifact_store import LocalArtifactStore
            svc.artifact_store = LocalArtifactStore()
```

In `runtime.py` `_wire_default_providers`, leave provider defaults as-is (they don't have `db`-namespace context for the pub store); wire the cloud `S3ArtifactStore` in `init()` after `_wire_default_providers(svc, db=db)`:

```python
    if svc.artifact_store is None and cfg.cas_bucket:
        from keri_serviceaid.providers.artifact_store import S3ArtifactStore
        pubdb = DynamoDBer.open(name=cfg.alias, stores=["pub."],
                                table_name=cfg.core_table,
                                namespace=cfg.pub_namespace, **kwa)
        svc.artifact_store = S3ArtifactStore(bucket=cfg.cas_bucket, db=pubdb)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_artifact_store_wiring.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add keri_serviceaid/contract.py keri_serviceaid/runtime.py keri_serviceaid/local_runtime.py tests/serviceaid/test_artifact_store_wiring.py
git commit -m "feat(serviceaid): wire artifact_store (Local default local, S3 default cloud)"
```

---

### Task 7: pipeline `publish` branch + LocalRuntime hermetic e2e

**Files:**
- Modify: `keri_serviceaid/pipeline.py` (add the `reply.kind == "publish"` branch)
- Test: `tests/serviceaid/test_pipeline_publish_e2e.py`

**Interfaces:**
- Consumes: `Reply.publish` (Task 1), `svc.artifact_store` (Task 6), `Context` + `svc.issuer.issue` (existing), `svc.idempotency.record` + `svc.deliverer.deliver` + `svc.resolver.resolve` (existing).
- Produces: pipeline behavior — on `kind == "publish"`: store artifact → merge `firstSeen`/`priorContributor` into `reply.attributes` → `reply.schema_said = cmd.issues` → `issue` receipt (always) → `record` → `deliver` iff `reply.want_receipt`.

- [ ] **Step 1: Write the failing test**

This test drives the full pipeline through `LocalRuntime` with a fake deliverer, mirroring `tests/serviceaid/test_local_runtime.py`. It uses the existing `make_exn` test helper and `conftest.py` fixtures (`issuer_hby`, `recipient_pre`).

```python
# tests/serviceaid/test_pipeline_publish_e2e.py
import json

from keri.vdr import credentialing

from keri_serviceaid import ServiceAid, Reply
from keri_serviceaid.local_runtime import LocalRuntime
from keri_serviceaid.providers.artifact_store import LocalArtifactStore

# make_exn + FakeDeliverer/FakeResolver are the existing serviceaid test helpers.
from test_local_runtime import make_exn, FakeDeliverer, FakeResolver  # noqa: E402

RECEIPT_SCHEMA = {
    "$id": "", "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "PublicationReceipt", "type": "object",
    "properties": {"v": {"type": "string"}, "d": {"type": "string"},
                   "i": {"type": "string"}, "ri": {"type": "string"},
                   "s": {"type": "string"},
                   "a": {"type": "object"}},
    "additionalProperties": False, "required": ["v", "d", "i", "ri", "s", "a"]}

PUBLISHED_SCHEMA = {"$id": "", "$schema": "http://json-schema.org/draft-07/schema#",
                    "title": "Widget", "type": "object", "properties": {}}


def _build(issuer_hby):
    hab = issuer_hby.makeHab(name="schema-publisher")
    rgy = credentialing.Regery(hby=issuer_hby, name="schema-publisher", temp=True)
    svc = ServiceAid(alias="schema-publisher")
    receipt_said = svc.register_schema(dict(RECEIPT_SCHEMA))

    @svc.command(route="/schema/cmd/publish", issues=receipt_said)
    def publish(req):
        from keri.core import scheming
        from keri.kering import Kinds
        schemer = scheming.Schemer(sed=dict(req.payload["schema"]), kind=Kinds.json)
        return Reply.publish(recipient=req.sender, artifact_said=schemer.said,
                             artifact_bytes=schemer.raw,
                             attributes={"schemaSaid": schemer.said,
                                         "schemaKind": "ACDC-schema",
                                         "publisher": req.sender},
                             want_receipt=req.payload.get("want_receipt", False))

    store = LocalArtifactStore()
    svc.artifact_store = store
    fake = FakeDeliverer()
    svc.deliverer = fake
    svc.resolver = FakeResolver()
    rt = LocalRuntime(svc, hby=issuer_hby, hab=hab, rgy=rgy)
    return hab, rgy, rt, store, fake


def test_publish_stores_artifact_and_issues_receipt_first_seen(issuer_hby, recipient_pre):
    hab, rgy, rt, store, fake = _build(issuer_hby)
    exn = make_exn("/schema/cmd/publish", recipient_pre, hab.pre,
                   {"schema": PUBLISHED_SCHEMA, "want_receipt": True})
    rt._captures["/schema/cmd/publish"].handle(exn, attachments=[])
    rt.process_captured()

    # artifact stored under its SAID
    from keri.core import scheming
    from keri.kering import Kinds
    said = scheming.Schemer(sed=dict(PUBLISHED_SCHEMA), kind=Kinds.json).said
    assert store.get(said) is not None
    # a publication_receipt was issued into the registry (one credential saved)
    assert len(list(rgy.reger.saved.getItemIter())) == 1
    # and delivered (want_receipt=True)
    assert len(fake.delivered) == 1


def test_publish_without_receipt_issues_but_does_not_deliver(issuer_hby, recipient_pre):
    hab, rgy, rt, store, fake = _build(issuer_hby)
    exn = make_exn("/schema/cmd/publish", recipient_pre, hab.pre,
                   {"schema": PUBLISHED_SCHEMA, "want_receipt": False})
    rt._captures["/schema/cmd/publish"].handle(exn, attachments=[])
    rt.process_captured()
    assert len(list(rgy.reger.saved.getItemIter())) == 1   # ledger entry issued
    assert len(fake.delivered) == 0                        # not delivered
```

> Implementer note: verify the exact enumeration API for "credentials saved" against `reger` (`saved.getItemIter()` / `cloneCreds()`); if the surveyed `.saved` iteration differs, use whatever the existing e2e test (`tests/serviceaid/test_local_runtime_e2e.py`) uses to assert an issuance. `FakeDeliverer`/`FakeResolver`/`make_exn` are defined in `tests/serviceaid/test_local_runtime.py` — import them from there (the suite already does).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_pipeline_publish_e2e.py -v`
Expected: FAIL — the pipeline has no `publish` branch, so `reply.kind == "publish"` falls through to the "no reply" log; nothing is issued/delivered (`assert len(...) == 1` fails with 0).

- [ ] **Step 3: Add the `publish` branch to `pipeline.py`**

In `keri_serviceaid/pipeline.py`, insert this block after the `if reply.kind == "revoke":` block and before the final `reject / none` log:

```python
    if reply.kind == "publish":
        ctx = Context(hby=state.hby, hab=state.hab, rgy=state.rgy,
                      registry_name=state.cfg.alias)
        fs = svc.artifact_store.store(reply.artifact_said, reply.artifact_bytes,
                                      by=sender)
        # Merge first-seen provenance into the receipt attributes (dt is stamped
        # server-side by the issuer). priorContributor is null when first.
        reply.attributes = {**(reply.attributes or {}),
                            "firstSeen": fs.first_seen,
                            "priorContributor": (None if fs.first_seen
                                                 else {"aid": fs.first_publisher})}
        reply.schema_said = cmd.issues           # the publication_receipt schema
        grant = svc.issuer.issue(reply, ctx)     # mint + iss receipt into registry (ledger)
        svc.idempotency.record(said, grant)      # BEFORE delivery (exactly-once)
        if reply.want_receipt:
            endpoint = svc.resolver.resolve(sender, state.hby)
            svc.deliverer.deliver(grant, endpoint, ctx)
            logger.info("published %s + delivered receipt to %s",
                        reply.artifact_said, endpoint.eid)
        else:
            logger.info("published %s + recorded receipt (delivery not requested)",
                        reply.artifact_said)
        return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_pipeline_publish_e2e.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole hermetic serviceaid suite (regression)**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid -v --deselect tests/serviceaid/test_providers_idempotency.py --deselect tests/serviceaid/test_dynamo_claim_first_seen.py --deselect tests/serviceaid/test_s3_artifact_store.py`
Expected: PASS (all hermetic tests green; the three moto files are deselected — run those separately, they need moto).

- [ ] **Step 6: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add keri_serviceaid/pipeline.py tests/serviceaid/test_pipeline_publish_e2e.py
git commit -m "feat(serviceaid): pipeline publish branch (store -> issue receipt -> deliver-on-request)"
```

---

### Task 8: `publication_receipt` ACDC schema

**Files:**
- Create: `examples/schema_host/schema/publication_receipt.json`
- Test: `tests/serviceaid/test_publication_receipt_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a JSON-Schema document (ACDC schema) with an `a` block carrying `schemaSaid`, `schemaKind`, `publisher`, `firstSeen`, `priorContributor` (nullable object), `origin` (nullable object), `dt`. `$id` is `""` at rest (saidified by `register_schema` at load).

- [ ] **Step 1: Write the failing test**

```python
# tests/serviceaid/test_publication_receipt_schema.py
import json
import pathlib

from keri.core import scheming
from keri.kering import Kinds

SCHEMA = pathlib.Path(__file__).parents[1] / "examples/schema_host/schema/publication_receipt.json"


def test_publication_receipt_schema_saidifies_and_has_attributes():
    sad = json.loads(SCHEMA.read_text())
    schemer = scheming.Schemer(sed=sad, kind=Kinds.json)   # saidifies $id
    assert schemer.said                                     # non-empty SAID
    a = sad["properties"]["a"]
    # attribute object (second oneOf branch) declares the receipt fields
    props = a["oneOf"][1]["properties"]
    for field in ("schemaSaid", "schemaKind", "publisher", "firstSeen",
                  "priorContributor", "origin", "dt"):
        assert field in props
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_publication_receipt_schema.py -v`
Expected: FAIL — `FileNotFoundError` (schema not created yet).

- [ ] **Step 3: Create the schema**

```json
{
  "$id": "",
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PublicationReceipt",
  "description": "Issued by the schema.keri.host publisher AID to a requester who published a public SAD (an ACDC schema). Attests the schema SAID, the publisher, first-seen ordering in this publish log, optional origin lineage, and the server-asserted recorded-at time.",
  "type": "object",
  "properties": {
    "v": {"type": "string"},
    "d": {"type": "string"},
    "i": {"type": "string"},
    "ri": {"type": "string"},
    "s": {"type": "string"},
    "a": {
      "oneOf": [
        {"type": "string"},
        {
          "type": "object",
          "properties": {
            "d": {"type": "string"},
            "i": {"type": "string"},
            "dt": {"type": "string", "format": "date-time", "description": "server-asserted recorded-at time (not a trusted timestamp)"},
            "schemaSaid": {"type": "string", "description": "SAID of the published SAD"},
            "schemaKind": {"type": "string", "description": "SAD kind, e.g. ACDC-schema"},
            "publisher": {"type": "string", "description": "requester AID that published this SAID"},
            "firstSeen": {"type": "boolean", "description": "true if publisher is the first to publish this SAID here"},
            "priorContributor": {
              "oneOf": [
                {"type": "null"},
                {"type": "object", "properties": {"aid": {"type": "string"}, "oobi": {"type": "string"}}, "required": ["aid"], "additionalProperties": false}
              ],
              "description": "the first publisher (and where to resolve them) when firstSeen is false"
            },
            "origin": {
              "oneOf": [
                {"type": "null"},
                {"type": "object", "properties": {"origin_ecosystem": {"type": "string"}, "origin_oobi": {"type": "string"}}, "additionalProperties": false}
              ],
              "description": "optional lineage supplied by the publisher"
            }
          },
          "additionalProperties": false,
          "required": ["d", "i", "dt", "schemaSaid", "publisher", "firstSeen"]
        }
      ]
    }
  },
  "additionalProperties": false,
  "required": ["v", "d", "i", "ri", "s", "a"]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_publication_receipt_schema.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add examples/schema_host/schema/publication_receipt.json tests/serviceaid/test_publication_receipt_schema.py
git commit -m "feat(schema-host): publication_receipt ACDC schema"
```

---

### Task 9: `schema_host_handler.py` — the ServiceAid + publish command

**Files:**
- Create: `examples/schema_host/schema_host_handler.py`
- Test: `tests/serviceaid/test_schema_host_handler.py`

**Interfaces:**
- Consumes: `ServiceAid`, `Reply`, `Request`, `Allowlist` (public `keri_serviceaid` exports); `svc.register_schema`; `scheming.Schemer`; the receipt schema (Task 8).
- Produces: module attribute `svc` (a `ServiceAid`, `handler_ref="schema_host_handler:svc"`), `validate_public_schema(sad: dict) -> None` (raises `ValueError` on a non-schema / SAID mismatch / instance-shaped SAD), and the `/schema/cmd/publish` command returning `Reply.publish(...)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/serviceaid/test_schema_host_handler.py
import pytest

from keri_serviceaid import TestRuntime

import importlib.util, pathlib
_spec = importlib.util.spec_from_file_location(
    "schema_host_handler",
    pathlib.Path(__file__).parents[1] / "examples/schema_host/schema_host_handler.py")
schema_host_handler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schema_host_handler)

VALID_SCHEMA = {"$id": "", "$schema": "http://json-schema.org/draft-07/schema#",
                "title": "Widget", "type": "object", "properties": {}}


def _saidify(sad):
    from keri.core import scheming
    from keri.kering import Kinds
    return scheming.Schemer(sed=dict(sad), kind=Kinds.json)


def test_publish_returns_publish_reply_for_valid_schema():
    schemer = _saidify(VALID_SCHEMA)
    sad = dict(schemer.sed)   # $id now populated
    reply = TestRuntime(schema_host_handler.svc).send(
        route="/schema/cmd/publish", sender="EAlice",
        payload={"schema": sad, "want_receipt": True})
    assert reply.kind == "publish"
    assert reply.artifact_said == schemer.said
    assert reply.want_receipt is True
    assert reply.attributes["schemaSaid"] == schemer.said
    assert reply.attributes["publisher"] == "EAlice"


def test_publish_rejects_non_schema_sad():
    # An ACDC-instance-shaped SAD (no $id / $schema) must be rejected.
    with pytest.raises(ValueError):
        schema_host_handler.validate_public_schema({"d": "Ex", "i": "Ey", "a": {}})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_schema_host_handler.py -v`
Expected: FAIL — `FileNotFoundError` / import error (handler not created).

- [ ] **Step 3: Create the handler**

```python
# examples/schema_host/schema_host_handler.py
"""schema.keri.host — the publish_schema Service-AID (compute_code module).

`svc` is the declared entity; the framework finds it via handler_ref
"schema_host_handler:svc". One command: /schema/cmd/publish stores a public ACDC
schema in the CAS and records the publication (issuing an optional
publication_receipt ACDC). v1 gate = an Allowlist of publisher AIDs (override at
deploy). Accepts ACDC schemas ONLY; never private ACDC instances."""
import json
import pathlib

from keri.core import scheming
from keri.kering import Kinds

from keri_serviceaid import ServiceAid, Reply, Request, Allowlist

# v1 allowlist is injected at deploy (empty here = any verified sender; the cdk
# app sets the real publisher AIDs via a gitignored config / context).
svc = ServiceAid(alias="schema-publisher", witnesses=[], toad=0, authz=Allowlist([]))

_SCHEMA_PATH = pathlib.Path(__file__).parent / "schema" / "publication_receipt.json"
RECEIPT_SCHEMA_SAID = svc.register_schema(json.loads(_SCHEMA_PATH.read_text()))


def validate_public_schema(sad: dict) -> None:
    """Guardrail: accept only a well-formed ACDC/JSON schema whose $id == its SAID.

    Rejects anything lacking the JSON-Schema markers ($id/$schema) — which
    includes ACDC *instances* (they carry `d`/`i`/`a`, not `$id`), keeping
    private subject data out of the public CAS. Raises ValueError on rejection."""
    if not isinstance(sad, dict) or "$id" not in sad or "$schema" not in sad:
        raise ValueError("not a JSON Schema SAD (missing $id/$schema) — "
                         "instances and non-schema SADs are refused")
    # Schemer(verify=True) recomputes the SAID and checks it equals $id.
    scheming.Schemer(sed=dict(sad), kind=Kinds.json)


@svc.command(route="/schema/cmd/publish", issues=RECEIPT_SCHEMA_SAID)
def publish_schema(req: Request) -> Reply:
    """Validate + publish an ACDC schema. The framework stores it in the CAS,
    issues a publication_receipt ACDC (the KEL-anchored ledger entry), and
    delivers the receipt iff the caller asked (`want_receipt`)."""
    sad = req.payload["schema"]
    validate_public_schema(sad)
    schemer = scheming.Schemer(sed=dict(sad), kind=Kinds.json)
    return Reply.publish(
        recipient=req.sender,
        artifact_said=schemer.said,
        artifact_bytes=schemer.raw,
        attributes={"schemaSaid": schemer.said, "schemaKind": "ACDC-schema",
                    "publisher": req.sender, "origin": req.payload.get("origin")},
        want_receipt=bool(req.payload.get("want_receipt", False)),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid/test_schema_host_handler.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add examples/schema_host/schema_host_handler.py tests/serviceaid/test_schema_host_handler.py
git commit -m "feat(schema-host): publish_schema ServiceAid + schema validation guardrail"
```

---

### Task 10: `SchemaHostStack` — S3 CAS + CloudFront (read plane) at schema.keri.host

**Files:**
- Create: `keri_cdk/schema_host_stack.py`
- Test: `tests/cdk/test_schema_host_stack.py`

**Interfaces:**
- Consumes: aws-cdk-lib (`aws_s3`, `aws_cloudfront`, `aws_cloudfront_origins`, `aws_certificatemanager`, `aws_route53`, `aws_route53_targets`), an API Gateway `RestApi` (the ServiceAidFunction's `.api`) passed in for the write-route origin.
- Produces: `class SchemaHostStack(Stack)` with `__init__(self, scope, cid, *, domain_name: str, hosted_zone_id: str, write_api, **kw)` exposing `self.bucket` (the CAS bucket, `ITable`-like grantable) and wiring CloudFront: default/`/oobi/*` behavior → S3 origin (via OAC); `/schema/*` (write) behavior → the API Gateway origin (POST allowed, CESR + `CESR-ATTACHMENT` header forwarded, caching disabled); ACM cert (us-east-1 for CloudFront) + Route53 alias for `domain_name`.

- [ ] **Step 1: Write the failing test (CDK synth assertion)**

```python
# tests/cdk/test_schema_host_stack.py
import aws_cdk as cdk
from aws_cdk import aws_apigateway as apigw
from aws_cdk.assertions import Template

from keri_cdk.schema_host_stack import SchemaHostStack


def _stack():
    app = cdk.App()
    host = cdk.Stack(app, "Host", env=cdk.Environment(account="111111111111", region="us-east-1"))
    api = apigw.RestApi(host, "WriteApi")
    api.root.add_method("ANY")
    stack = SchemaHostStack(app, "SchemaHost", domain_name="schema.keri.host",
                            hosted_zone_id="Z123", write_api=api,
                            env=cdk.Environment(account="111111111111", region="us-east-1"))
    return Template.from_stack(stack)


def test_creates_cas_bucket_and_distribution():
    t = _stack()
    t.resource_count_is("AWS::S3::Bucket", 1)
    t.resource_count_is("AWS::CloudFront::Distribution", 1)


def test_distribution_has_oobi_and_write_behaviors():
    t = _stack()
    t.has_resource_properties("AWS::CloudFront::Distribution", {
        "DistributionConfig": {
            "Aliases": ["schema.keri.host"],
        }
    })
```

> Implementer note: assertion granularity depends on the CDK version's synth output — keep assertions to resource counts + the alias (stable). If `has_resource_properties` on nested `CacheBehaviors` is brittle across CDK versions, assert only the bucket/distribution counts + `Aliases`, and verify behaviors by reading the synth template once during implementation. CloudFront ACM certs MUST be in `us-east-1`; the test env pins that.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/cdk/test_schema_host_stack.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keri_cdk.schema_host_stack'`.

- [ ] **Step 3: Write the stack**

```python
# keri_cdk/schema_host_stack.py
"""Read-plane for schema.keri.host: an S3 content-addressed store fronted by
CloudFront. GET /oobi/<said> -> S3 object oobi/<said> (application/schema+json,
long-cached, trustless). /schema/* -> the write API (the publish Service-AID),
POST allowed, CESR forwarded, uncached. One hostname, path-routed."""
from aws_cdk import (Stack, RemovalPolicy, Duration)
from aws_cdk import (aws_s3 as s3, aws_cloudfront as cf,
                     aws_cloudfront_origins as origins,
                     aws_certificatemanager as acm, aws_route53 as r53,
                     aws_route53_targets as targets)
from constructs import Construct


class SchemaHostStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, domain_name: str,
                 hosted_zone_id: str, write_api, **kw):
        super().__init__(scope, cid, **kw)

        self.bucket = s3.Bucket(
            self, "SchemaCas",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )

        hosted_zone = r53.HostedZone.from_hosted_zone_attributes(
            self, "HostedZone", hosted_zone_id=hosted_zone_id,
            zone_name=".".join(domain_name.split(".")[-2:]))

        # CloudFront needs its cert in us-east-1 (this stack is deployed there).
        cert = acm.Certificate(
            self, "SchemaCert", domain_name=domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone))

        s3_origin = origins.S3BucketOrigin.with_origin_access_control(self.bucket)
        api_origin = origins.RestApiOrigin(write_api)

        distribution = cf.Distribution(
            self, "SchemaDist",
            domain_names=[domain_name],
            certificate=cert,
            default_behavior=cf.BehaviorOptions(
                origin=s3_origin,
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                "/schema/*": cf.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cf.AllowedMethods.ALLOW_ALL,       # POST for CESR writes
                    cache_policy=cf.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                ),
            },
        )
        self.distribution = distribution

        r53.ARecord(
            self, "SchemaDnsRecord", zone=hosted_zone, record_name=domain_name,
            target=r53.RecordTarget.from_alias(targets.CloudFrontTarget(distribution)))
```

> Implementer note: confirm the exact `aws_cloudfront_origins` API names against the installed aws-cdk-lib (`S3BucketOrigin.with_origin_access_control` vs `S3Origin`; `RestApiOrigin`). If the version predates `S3BucketOrigin`, use `origins.S3Origin(bucket)` + an explicit OAI. Adjust to whatever the pinned CDK exposes; the test's count+alias assertions are version-stable.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/cdk/test_schema_host_stack.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add keri_cdk/schema_host_stack.py tests/cdk/test_schema_host_stack.py
git commit -m "feat(cdk): SchemaHostStack (S3 CAS + CloudFront path-routed read plane)"
```

---

### Task 11: `examples/schema_host/app.py` — deploy wiring

**Files:**
- Create: `examples/schema_host/app.py`
- Test: `tests/cdk/test_schema_host_app.py`

**Interfaces:**
- Consumes: `KeriCoreStack`, `ServiceAidFunction` (both in `keri_cdk`), `SchemaHostStack` (Task 10), `inject_handler_shim` (from `keri_cdk.service_aid`), `Code.from_asset`.
- Produces: a synthesizable CDK app wiring `KeriCoreStack` + a service `Stack` holding `ServiceAidFunction(alias="schema-publisher", handler_ref="schema_host_handler:svc", compute_code=<this dir>)` + `SchemaHostStack`, granting the Function `s3:PutObject` on the CAS bucket and passing `SERVICEAID_CAS_BUCKET` as an environment variable.

- [ ] **Step 1: Write the failing test**

```python
# tests/cdk/test_schema_host_app.py
import subprocess, sys, pathlib


def test_app_synthesizes():
    app = pathlib.Path(__file__).parents[1] / "examples/schema_host/app.py"
    # cdk synth via the python app entrypoint: importing + app.synth() must not raise.
    result = subprocess.run(
        [sys.executable, str(app)],
        cwd=str(pathlib.Path(__file__).parents[1]),
        env={"PYTHONPATH": str(pathlib.Path(__file__).parents[1]),
             "CDK_DEFAULT_ACCOUNT": "111111111111", "CDK_DEFAULT_REGION": "us-east-1",
             "PATH": __import__("os").environ["PATH"]},
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/cdk/test_schema_host_app.py -v`
Expected: FAIL — app file missing / import error.

- [ ] **Step 3: Write the app**

```python
# examples/schema_host/app.py
"""CDK app for schema.keri.host: pooled core table + the publish Service-AID +
the S3/CloudFront read plane. Deploy: cdk deploy KeriCore SchemaPublisher SchemaHost
  --context account=<acct> --context region=<region>
  --context domain=schema.keri.host --context hosted_zone_id=<zid>
  --context cas_bucket=<name> --context allowlist='["EPub1",...]'"""
import json
import pathlib

import aws_cdk as cdk
from aws_cdk import aws_lambda as _lambda

from keri_cdk.core_stack import KeriCoreStack
from keri_cdk.service_aid import ServiceAidFunction, inject_handler_shim
from keri_cdk.schema_host_stack import SchemaHostStack

app = cdk.App()
env = cdk.Environment(account=app.node.try_get_context("account"),
                      region=app.node.try_get_context("region") or "us-east-1")
domain = app.node.try_get_context("domain") or "schema.keri.host"
zone_id = app.node.try_get_context("hosted_zone_id") or "ZPLACEHOLDER"
cas_bucket_name = app.node.try_get_context("cas_bucket") or "schema-keri-host-cas"
allowlist = app.node.try_get_context("allowlist") or "[]"

core = KeriCoreStack(app, "KeriCore", table_name="keri-core", env=env)

svc_stack = cdk.Stack(app, "SchemaPublisher", env=env)
_asset_dir = str(pathlib.Path(__file__).parent)
inject_handler_shim(_asset_dir)
svc = ServiceAidFunction(
    svc_stack, "SchemaPublisher",
    alias="schema-publisher",
    core_table=core.table,
    compute_code=_lambda.Code.from_asset(_asset_dir),
    handler_ref="schema_host_handler:svc",
    witnesses=app.node.try_get_context("witnesses") or [],
    toad=int(app.node.try_get_context("toad") or 0),
    environment={"SERVICEAID_CAS_BUCKET": cas_bucket_name,
                 "SERVICEAID_ALLOWLIST": allowlist if isinstance(allowlist, str)
                 else json.dumps(allowlist)},
)

host = SchemaHostStack(app, "SchemaHost", domain_name=domain,
                       hosted_zone_id=zone_id, write_api=svc.api, env=env)
host.bucket.grant_put(svc.fn)          # the publish Lambda writes CAS objects

svc_stack.add_dependency(core)
host.add_dependency(svc_stack)
app.synth()
```

> Implementer notes: (1) confirm the `ServiceAidFunction` exposes `.api` (the API Gateway) and `.fn` (the Function) — the survey shows both are built; if the attribute names differ, adjust. (2) The handler must read `SERVICEAID_ALLOWLIST` to populate `Allowlist` — add that to `schema_host_handler.py` (`Allowlist(json.loads(os.environ.get("SERVICEAID_ALLOWLIST", "[]")))`) if you want deploy-time allowlist injection; the hermetic tests use `Allowlist([])`. (3) `hosted_zone_id`/`cas_bucket` come from a gitignored deploy config in reality (no personal values committed).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/cdk/test_schema_host_app.py -v`
Expected: PASS (1 passed). (Requires aws-cdk-lib importable; no AWS calls — pure synth.)

- [ ] **Step 5: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add examples/schema_host/app.py tests/cdk/test_schema_host_app.py
git commit -m "feat(schema-host): CDK app wiring (core + publisher + read plane, S3 grant)"
```

---

### Task 12: `DEPLOY_RUNBOOK.md` — live-deploy gate

**Files:**
- Create: `examples/schema_host/DEPLOY_RUNBOOK.md`

**Interfaces:**
- Consumes: nothing (documentation). Mirrors `examples/gated_retrieval/DEPLOY_RUNBOOK.md`.
- Produces: the ordered live-deploy validation steps a human runs once against real AWS.

- [ ] **Step 1: Write the runbook**

Create `examples/schema_host/DEPLOY_RUNBOOK.md` covering, in order (mirror the gated runbook's structure and CLAUDE.md deploy gotchas):

1. **Prereqs** — AWS creds (`AWS_PROFILE=personal`), Docker (arm64 layers), a test publisher keystore (kli) whose AID is on the allowlist, `hosted_zone_id` + `cas_bucket` from the gitignored deploy config.
2. **Build both layers** — `keri_cdk/layers/build_layer.sh` (KeriRuntimeLayer; **includes the new `DynamoDBer.claimFirstSeen`**, so rebuild) + `build_framework_layer.sh` (ServiceAidFrameworkLayer; **includes `artifact_store.py` + the pipeline publish branch**). Confirm each prints `OK`.
3. **Deploy** — `cd examples/schema_host && cdk deploy KeriCore SchemaPublisher SchemaHost --context account=<a> --context region=us-east-1 --context domain=schema.keri.host --context hosted_zone_id=<z> --context cas_bucket=<b> --context allowlist='["<publisher-aid>"]'`. The inception CR mints keeper `keri/schema-publisher/keeper`, incepts the AID + registry. Confirm no `WitnessReceiptor` hang if witnessed.
4. **Resolve the service OOBI** into the publisher keystore.
5. **Publish (route 1)** — build a signed `/schema/cmd/publish` exn carrying `{schema: <a test ACDC schema SAD>, want_receipt: true}`, POST as `application/cesr` + `CESR-ATTACHMENT` to `https://schema.keri.host/schema/...`. Expect **204**.
6. **Verify the read plane** — `curl -i https://schema.keri.host/oobi/<schema-said>` → **200**, `Content-Type: application/schema+json`, body `$id == <schema-said>`; verify `Schemer(raw=body).said == <schema-said>`.
7. **Verify the ledger** — the publisher's mailbox received an `/ipex/grant` for a `publication_receipt` ACDC; admit it; confirm `firstSeen: true`.
8. **First-seen dedup** — from a SECOND publisher keystore, publish the SAME schema; its receipt reads `firstSeen: false` + `priorContributor.aid == <publisher-1>`. Confirm the CAS object is unchanged (idempotent).
9. **Replay (idempotency)** — re-POST the exact step-5 exn → **204** + the SAME receipt re-delivered (one TEL `iss`, no duplicate).
10. **Tear down** — `cdk destroy SchemaHost SchemaPublisher` (AID/keeper persist by design); leave `KeriCore` if other services use it.

Include a **Validation checklist** (all must hold): both layers built; inception via Receiptor (no hang); read plane serves `application/schema+json` with matching `$id`; publish issued a receipt into the registry; first-seen dedup honest; replay re-delivered the same receipt.

- [ ] **Step 2: Commit**

```bash
cd /Users/seriouscoderone/code/keripy
git add examples/schema_host/DEPLOY_RUNBOOK.md
git commit -m "docs(schema-host): live-deploy gate runbook"
```

---

## Verification (whole plan)

- **Hermetic suite green:** `cd /Users/seriouscoderone/code/keripy && PYTHONPATH=. python -m pytest tests/serviceaid tests/cdk -v` with the three moto files deselected (Tasks 3, 4, and the existing idempotency test) — all pass, no AWS required.
- **Cloud (moto) suite green:** run the three moto files (`test_dynamo_claim_first_seen.py`, `test_s3_artifact_store.py`, `test_providers_idempotency.py`) — all pass under `mock_aws`.
- **CDK synth:** `tests/cdk/test_schema_host_stack.py` + `test_schema_host_app.py` pass (pure synth, no AWS).
- **Existing regression:** the pre-existing `keri_serviceaid` + `cdk` suites stay green (the `Reply`/`pipeline`/`ServiceAid` changes are additive — new `kind`, new optional param, new branch).
- **Live gate:** `examples/schema_host/DEPLOY_RUNBOOK.md` executed once against real AWS (human-run, out of CI) proves the end-to-end publish → CAS read → receipt → first-seen → replay chain.

## Self-review notes (spec coverage)

- Read plane (S3+CloudFront, `GET /oobi/<said>`, `application/schema+json`) → Tasks 10, 11, 12 (+ read contract validated in the runbook step 6).
- Write plane (`publish_schema` Service-AID, allowlist gate, schemas-only) → Tasks 6, 7, 9.
- Store-artifact effect (CAS, idempotent by SAID) → Tasks 2, 4, 7.
- TEL-registry receipt (always issue; deliver on request) → Task 7 (reuses existing `IpexGrantIssuer`).
- Serializable first-seen + prior-contributor → Tasks 2, 3, 4, 7.
- `publication_receipt` ACDC (attributes incl. server-stamped `dt`, lineage) → Tasks 7 (dt via issuer), 8, 9.
- Framework config surface (Service-AID as configurable compute) → the additive `Reply.publish` + injectable `ArtifactStore` (Tasks 1, 2, 6) make the effect a configured capability, not a fork.
- Deferred (NOT in this plan, per spec): publisher-credential ("b") gate, external trusted-time anchor, broader public SAD kinds, wallet client-side resolution, publish-failure nack `exn`.
