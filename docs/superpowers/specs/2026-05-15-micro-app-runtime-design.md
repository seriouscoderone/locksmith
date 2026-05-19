# Micro-App Runtime — Design Spec

| | |
|---|---|
| Status | Draft for review |
| Date | 2026-05-15 |
| Project | `micro-app-runtime` (new standalone Python library) |

## 1. Goal

Provide a runtime that lets a single Python "handler" package be invoked, with cryptographic verification, by either a local Locksmith wallet or an AWS Lambda — without changing the handler code.

## 2. Context & motivation

KERI provides composable, verifiable building blocks (OOBIs for discovery, SAIDs for content addressing, ACDCs for credentials, IPEX for exchange). Combined, they form a universal API surface where applications are *protocol-compatible services* rather than tenants of a platform.

The infrastructure to deploy KERI-native services is, however, lopsided:

- **keripy's `Exchanger`** dispatches verified `exn` messages to in-process handler classes. Used inside any Habery, including the one Locksmith embeds.
- **`keria-aws`** wraps a KERIA cloud agent in API Gateway + Lambda + DynamoDB + S3. Receives CESR-encoded messages, verifies them, dispatches via the same Exchanger handler protocol. Production-grade.
- **Locksmith's `TurretDoer`** mounts an Exchanger inside the vault's `DoDoer` loop, gated by sender AID.

What's missing is the *shared layer* on top: a developer ergonomics surface (decorators, `Context`, `Decision`, schema validation) and a runtime adapter pattern that makes the same Python handler runnable in **either** runtime. Without it, a dev team building a KERI-native service has to maintain two parallel wirings of every handler — one for the local wallet, one for the cloud — and reinvent state, idempotency, and workflow plumbing each time.

`micro-app-runtime` is that shared layer.

## 3. Vocabulary

| Term | Meaning |
|---|---|
| **Micro-app template** | The declarative description of one role's slice of an exchange (commands, reactions, workflows, rules). Schema at `docs/superpowers/specs/schemas/micro-app-template.schema.json`. |
| **Handler** | A Python function decorated with `@command` / `@reaction` / `@workflow_step` / `@scheduled`. Implements one piece of business logic. |
| **Plugin** | A Python package owned by an organization's dev team, containing handlers for one or more (template, role) bindings. Distributed as one pip-installable artifact. |
| **Role** | The implementer's perspective on an exchange (template defines exactly one). E.g., the "regulator" role of the `grants-carrier-license` template. |
| **Role AID** | The KERI AID that signs replies on behalf of a role. |
| **Runtime** | The host process executing handlers: `LocalRuntime` (Locksmith vault), `LambdaRuntime` (keria-aws Lambda), or `TestRuntime` (unit tests). |
| **Adapter** | The concrete implementation of `Runtime` for one host environment. |

## 4. Non-goals

- **No UI work.** `micro-app-runtime` ships zero user-facing surfaces. Operational visibility is delivered via emitted signals and structured logs; an operational-viewer plugin is a separate project.
- **No cross-runtime state sharing in v1.x.** Roles run in one runtime at a time. Migrating state between runtimes is a manual operator action.
- **No replacement of `keria-aws`'s built-in handlers.** `micro-app-runtime` mounts *alongside* them; standard KERIA flows on default routes keep working.
- **No re-implementation of KERI verification.** Signature, KEL, ACDC, and replay checks are delegated to keripy. The framework only adds schema validation and precondition enforcement at the application layer.

## 5. Key decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | General-purpose KERI trigger framework, plugin-delivered | Org's dev team builds one plugin spanning many micro apps; framework is template-agnostic at the core, template-aware as sugar. |
| 2 | **Layered** template binding: agnostic primitive + aware sugar | Keep `micro-app-runtime` useful without the Designer ecosystem; template binding is a sugar layer. |
| 3 | **Layered** state model: KV primitive + event-sourced aggregate sugar | One storage backend per runtime; aggregates are a key convention on top. |
| 4 | One role-AID across runtimes, via KERI 1-of-N multisig group | External counterparties see one canonical AID per role; either runtime can sign alone. Opt-in for multi-runtime deployments. |
| 5 | **Layered** reply transport: sync return + scheduled callbacks + native workflow state machine | IPEX flows are workflows; the template already declares them. Engine drives the state machine. |

## 6. Repo shape & deployment topology

New standalone repository hosting one Python package: **`micro-app-runtime`**.

```
micro_app_runtime/
  api.py                      # @command, @reaction, @scheduled, @workflow_step,
                              # Context, Decision                          (v0.1)
  state.py                    # KV state interface                          (v0.1)
  adapters/
    local.py                  # Mounts on a keripy Habery + Exchanger       (v0.1)
    aws_lambda.py             # Lambda entrypoint over CachedHabery         (v0.1)
    test.py                   # TestRuntime for unit tests                  (v0.1)
  template/                   # Template-aware sugar                        (v0.2)
    binding.py                # @command(template=..., command_id=...)
    aggregate.py              # ctx.aggregate(...)
    validation.py             # payload_schema + preconditions
  workflow/                   # Workflow engine                             (v0.3)
    engine.py
    scheduler.py
  identity/                   # Cross-runtime role-AID coordination         (v0.4)
    multisig.py
```

Install: `pip install micro-app-runtime[local]` for Locksmith, `pip install micro-app-runtime[aws]` for keria-aws.

### The org plugin

A Python package authored by an organization's internal dev team:

```
acme_runtime_handlers/
  __init__.py
  pyproject.toml              # one entry point under [project.entry-points."micro_app_runtime.plugins"]
  handlers/
    license_application.py    # @command(...) functions
    policy_renewal.py
    inspections.py
```

Both runtimes discover the plugin via `importlib.metadata.entry_points(group="micro_app_runtime.plugins")`.

> **Open question (defer to v0.1 spec):** the exact entry-point declaration shape — single callable returning a manifest, or auto-discovery of decorated functions in the package. Decided when v0.1 is planned.

### Mounting topology

```
┌─── Locksmith (one org employee's machine) ─────────┐
│  Vault → DoDoer                                    │
│    └─ MicroAppRuntimeDoer                          │
│         └─ micro_app_runtime.adapters.local        │
│              ├─ loads acme_runtime_handlers        │
│              ├─ mounts handlers on vault.exchanger │
│              └─ shares vault's Hby/Rgy/Hab         │
└─────────────────────────────────────────────────────┘

┌─── keria-aws (the org's cloud deployment) ────────────┐
│  API Gateway → MessagesFunction (Lambda)              │
│    └─ micro_app_runtime.adapters.aws_lambda           │
│         ├─ loads acme_runtime_handlers (cold start)   │
│         ├─ wraps CachedHabery.exchanger               │
│         └─ writes scheduled work to DynamoDB +        │
│              EventBridge Scheduler (v0.3)             │
└────────────────────────────────────────────────────────┘
```

Locksmith and keria-aws each carry a **thin integration shim** that delegates to `micro-app-runtime`. All real logic lives in the standalone library.

## 7. Handler API

### Decorators

The primitive is one decorator, `@command`, with kwargs that determine the mode:

```python
from micro_app_runtime import command, Context, Decision

# Mode 1 — raw route (v0.1, template-agnostic)
@command(route="/license/apply")
def on_apply(ctx: Context, payload: dict) -> Decision:
    if ctx.state.exists(("application", payload["app_id"])):
        return Decision.spurn(reason="duplicate")
    ctx.state.put(("application", payload["app_id"]), {"status": "received", **payload})
    return Decision.offer(recipient=ctx.sender, ...)

# Mode 2 — template-bound (v0.2 sugar)
@command(template="grants-carrier-license", command_id="apply")
def on_apply(ctx: Context, payload: ApplicationSubmission) -> Decision:
    # Route, payload validation, auth/state/temporal preconditions all
    # derived from the template before this body runs.
    ...

# Mode 3 — workflow step (v0.3 sugar)
@workflow_step(workflow_id="apply_to_grant", step_id="review")
def review(ctx, payload):
    if ctx.aggregate("application", payload["app_id"]).risk_score > 0.7:
        return Decision.advance(to_step="escalate_to_human")
    return Decision.advance(to_step="auto_grant", emit=Decision.grant(...))
```

Adjacent decorators for non-`exn` triggers:

- `@reaction(template=..., reaction_id=...)` — fires on local events from another handler's `Decision.emit_event` (v0.2)
- `@scheduled(name=..., cron=...)` — time-triggered (v0.3)

### Function signature & async

```python
def handler(ctx: Context, payload: dict | PydanticModel) -> Decision: ...
async def handler(ctx: Context, payload: ...) -> Decision: ...
```

Sync handlers run in a worker thread. Async handlers are awaited directly. Framework picks based on `inspect.iscoroutinefunction`.

### `Context`

| Field / method | Description |
|---|---|
| `ctx.sender` | Verified AID of the message sender |
| `ctx.role` | The role-AID this handler is acting as |
| `ctx.message_said` | SAID of the inbound `exn` — natural idempotency key |
| `ctx.payload` | Parsed `serder.ked['a']` |
| `ctx.serder` | Raw verified `Serder` — escape hatch |
| `ctx.attached_credentials` | Verified ACDCs (Tevery has already validated issuer KELs) |
| `ctx.state` | KV store, scoped per `(plugin_id, role)` |
| `ctx.config` | Read-only deployment config |
| `ctx.secrets` | Read-only secrets — env vars locally, Secrets Manager / SSM in AWS |
| `ctx.log` | Structured logger |
| `ctx.now()` | Mockable timestamp |
| `ctx.kel(aid)` | Fetch KEL for an arbitrary AID |
| `ctx.aggregate(name, id)` | Template-aware aggregate view *(v0.2+)* |
| `ctx.workflow` | Current workflow-instance handle *(v0.3+)* |

### `Decision`

Constructed via class methods. The runtime adapter is responsible for converting a `Decision` into concrete actions (signed `exn` messages, state writes, scheduled work).

| Slice | Decisions |
|---|---|
| v0.1 | `Decision.none()`, `Decision.emit(route, payload, recipient)`, IPEX shortcuts (`grant/admit/spurn/offer/agree/apply`), `Decision.parallel([...])` |
| v0.2 | `Decision.emit_event(name, payload)` |
| v0.3 | `Decision.schedule(at, name, payload)`, `Decision.advance(to_step, emit=...)`, `Decision.start_workflow(workflow_id, instance_id)` |

A `Decision` is declarative: handlers describe what should happen; the runtime decides *how* it happens (where to write, when to deliver). This is what makes the same handler runnable in any runtime.

## 8. Runtime adapter contract

```python
class Runtime(Protocol):
    def mount(self, plugin_package: str) -> None: ...
    def dispatch(self, serder: Serder, attachments: list) -> Decision: ...
    def emit(self, decision: Decision, role_aid: str) -> None: ...
    def persist_state(self, key: tuple, value: bytes) -> None: ...
    def load_state(self, key: tuple) -> bytes | None: ...
    def schedule(self, work: ScheduledWork) -> None: ...    # v0.3+
    def shutdown(self) -> None: ...
```

### LocalRuntime (Locksmith)

- Wraps the vault's `Habery` + `Rgy`
- Mounts handlers as keripy `Exchanger` handlers — native to keripy's protocol
- State backend: LMDB sub-DB inside the vault, namespaced `mar_<plugin_id>`
- Reply transport: `hab.exchange()` → `hab.endorse()` → enqueue on vault's `Postman`
- Scheduler (v0.3): a `SchedulerDoer` that polls a `scheduled_work` LMDB sub-DB on the vault's tick

### LambdaRuntime (keria-aws)

- Wraps `keria-aws.CachedHabery` (transparent wrapper around keripy `Habery`)
- Constructs `Context` from the Lambda event payload
- State backend: DynamoDB table, partition key `<plugin_id>#<role>`, sort key joined from the tuple
- Reply transport (v0.1): produced CESR frames returned in Lambda response body; keria-aws's `MessagesFunction` continues to handle Postman delivery
- Scheduler (v0.3): DynamoDB row + one-shot EventBridge Scheduler rule per item; rule invokes a `scheduled_fire` Lambda

### TestRuntime

- No real Habery; minimal in-memory fakes for `Hab` / `Postman` / `Tevery`
- State backend: in-memory `dict[tuple, bytes]`
- Captures all emitted Decisions in `rt.outbox`
- `rt.advance_time(by=...)` fires due scheduled work
- `rt.tick()` advances pending workflow instances
- Default skips the verification pipeline (handlers aren't testing keripy); `rt.strict=True` re-enables it with the fake KEL store

## 9. State model

### v0.1 — KV primitive

Interface:

```python
ctx.state.get(key)                # -> bytes | None
ctx.state.put(key, value)         # value is bytes
ctx.state.delete(key)
ctx.state.exists(key)
ctx.state.list(prefix)            # -> Iterator[(Key, bytes)]
ctx.state.cas(key, expected, new) # atomic compare-and-swap
ctx.state.json                    # sugar wrapper: get_json/put_json
```

`key` is a tuple of strings, flattened by the runtime adapter to a backend-native key.

Scope, enforced by the runtime: `mar/<plugin_id>/<role>/<key...>`. Different role bindings of the same plugin → separate namespaces. Different plugins on the same host → separate namespaces.

Backends: LMDB sub-DB (local), DynamoDB table (Lambda), in-memory dict (test).

### v0.2 — Event-sourced aggregate sugar

Layered on KV using framework-owned key conventions:

```
mar/<plugin_id>/<role>/agg/<aggregate_id>/<instance_id>/events/<seq>   -> event bytes
mar/<plugin_id>/<role>/agg/<aggregate_id>/<instance_id>/state          -> projected state
```

The template's `aggregate.state_schema` defines the projected shape (Pydantic model). The template's reactions (with their `trigger` referencing event types) fire automatically when the framework appends a new event.

```python
app = ctx.aggregate("application", "A1")  # current projected state, typed
if app.status == "new":
    return Decision.emit_event("ApplicationReceived", {"app_id": "A1", ...})
```

### Guarantees

- **At-least-once delivery + exactly-once application of effects** via SAID-keyed dedupe (`processed_messages/<ctx.message_said>`).
- **CAS** for hand-rolled invariants.
- **No cross-runtime state sharing.** Roles run in one runtime at a time.

## 10. Workflow engine & scheduled callbacks *(v0.3)*

### Workflow instances

The template's `workflow` primitive becomes a state machine. Instances live in KV:

```
mar/<plugin_id>/<role>/wf/<workflow_id>/<instance_id>/state    -> {current_step, started_at, ...}
mar/<plugin_id>/<role>/wf/<workflow_id>/<instance_id>/history  -> ordered transitions
mar/<plugin_id>/<role>/wf/<workflow_id>/<instance_id>/timers   -> pending timeouts/delays
```

Instances are started either explicitly (`Decision.start_workflow(...)`) or implicitly when an inbound `exn` matches a workflow's `trigger`.

### Advancing

```python
@workflow_step(workflow_id="apply_to_grant", step_id="review")
def review(ctx, payload):
    if ctx.aggregate("application", payload["app_id"]).risk_score > 0.7:
        return Decision.advance(to_step="escalate_to_human")
    return Decision.advance(
        to_step="auto_grant",
        emit=Decision.grant(credential_said="...", recipient=ctx.sender)
    )
```

In one coordinated write per backend (LMDB transaction locally; DynamoDB `TransactWriteItems` in Lambda — both bound by their respective per-transaction item limits) the engine: records the transition, emits any embedded `Decision`, arms timers per the next step's `expected_inbound` + template `failure_policy.timeout_seconds`.

### Scheduled callbacks

```python
@scheduled(name="renewal_reminder")
def remind(ctx, payload):
    return Decision.emit(route="/license/renewal_due", payload=..., recipient=...)
```

`Decision.schedule(at=..., name=..., payload=...)` writes a scheduled-work record. Backends: LMDB range-scan (local), DynamoDB + one-shot EventBridge Scheduler rule (Lambda), in-memory sorted list (test). Cron-style recurrence supported via `@scheduled(cron=...)`.

### Failure policy & timeouts

From the template's `reaction.failure_policy`:

- `on_validation_failure`: `log_and_continue` / `log_and_spurn` / `abort`
- `timeout_seconds`: when an `expected_inbound` doesn't arrive, the engine fires a synthetic `__timeout__` event, routed to a timeout-handling step if declared, else applies the failure policy.

### Observability

Each instance produces a trace: every step transition (timestamp, decision emitted, inbound message SAID, time spent in step, pending timers). Emitted via `vault.signals.doer_event` (local) and structured CloudWatch logs (Lambda). A future operational-viewer plugin can consume these.

## 11. Cross-runtime identity *(v0.4)*

### Mechanism

The role AID is a **KERI 1-of-N multisig group** with one member AID per runtime:

```
role_aid  =  multisig_group([
                local_member_aid,    # in Locksmith vault's Habery
                lambda_member_aid,   # in keria-aws cloud Habery
             ],
             threshold=1)
```

Counterparties see one canonical AID for the role. Either member can sign alone (threshold=1). Both run the same Python handler; their signatures are operationally equivalent.

### Layering

Single-runtime orgs (the common case in v0.1–v0.3): role AID is a plain non-grouped AID in whichever runtime they chose. v0.4 multisig is **opt-in**.

Multi-runtime orgs: role AID is a multisig group as above.

### Provisioning (sketch — full design in v0.4 spec)

1. Locksmith side: generate `local_member_aid` in a settings-namespaced Hab; export KEL + identifier.
2. AWS side: generate `lambda_member_aid` in the cloud Habery; export.
3. Group inception (orchestrated by a small CLI in `micro-app-runtime`): inception event listing both members and threshold=1; both members sign; framework stores the group AID and member identifiers in each runtime's local config.
4. Both runtimes use the group AID for outbound signing; each invokes `hab.exchange()` on its own member, producing a threshold-satisfying signature.

### Open questions deferred to v0.4 spec

- Rotation handshake mechanics
- Group AID's own witness coordination
- Member loss / compromise recovery flow
- Whether the group AID should itself be a delegate of an org-root AID (kill-switch); current preference: yes
- Honest acknowledgement: a compromised runtime can sign as the role; mitigation is rotation from the org-root via revocation of the compromised member.

### What v0.1–v0.3 must do today so v0.4 lands cleanly

1. Handler API never names a signing AID — handlers act as "the role"; the runtime resolves to a Hab at the call site. *(Already specified in §7.)*
2. Each runtime's config has a `role_bindings` section mapping role name → Hab alias. v0.1: a single alias. v0.4: an alias of a member AID of a group; lookups + signing route through the group transparently.

## 12. Verification pipeline & error handling

### Inbound pipeline

| # | Check | Done by | When |
|---|---|---|---|
| 1 | CESR parse + structural validity | keripy `Parser` | always |
| 2 | Signature verification (KEL lookup + threshold) | keripy `Kevery` / `Exchanger` | always |
| 3 | Replay/duplication by SAID | keripy `Exchanger` | always |
| 4 | ACDC attachment verification (issuer KEL, revocation) | keripy `Tevery` | when ACDCs attached |
| 5 | Payload schema validation | `micro-app-runtime` | template-aware mode (v0.2+) |
| 6 | Preconditions (auth / state / temporal) | `micro-app-runtime` | template-aware mode (v0.2+) |

Only after all six pass does the handler run.

### Failure modes

| Failure | v0.1 behavior | v0.2+ behavior |
|---|---|---|
| Verification (1–4) fails | Reject, no handler call, log | Same; if route is IPEX, emit `spurn` per `failure_policy` |
| Schema / precondition (5–6) fails | n/a | `log_and_continue` / `log_and_spurn` / `abort` per template |
| Handler raises | Caught, structured error log, NOT cached as processed (retry-safe) | Same; `failure_policy` applies |
| Outbound transport fails | LocalRuntime: handed to vault `Postman`; Lambda: returned in response body, keria-aws owns retry | Same |

### Idempotency

Framework checks `processed_messages/<ctx.message_said>` before invocation.

- **Hit (duplicate arrival):** short-circuit. Handler is **not** re-invoked. Outbound effects are **not** re-emitted (they were applied on first arrival). The caller receives an idempotent ack so it stops retrying.
- **Miss (first arrival):** invoke the handler; apply outbound effects via the runtime adapter; write the message-SAID and a Decision summary atomically (so a crash mid-application either leaves no record and the message is retried, or leaves a complete record and the message is treated as done).

Net guarantee: **at-least-once delivery + exactly-once application of effects.**

### Poison messages / DLQ

After N=5 retries (default; configurable per plugin), a message moves to:

- **LocalRuntime:** `mar/<plugin_id>/<role>/dlq/<message_said>` (LMDB sub-DB)
- **LambdaRuntime:** `failed_messages` DynamoDB table + SNS alert

Retention: 30 days default. Future operational-viewer plugin reads/replays/discards.

### Telemetry events

For every inbound message:

`inbound.received` → `inbound.verified` *or* `inbound.rejected(reason)` → `handler.invoked` → `handler.completed(decision)` *or* `handler.failed(error)` → `outbound.queued(n)` → `outbound.delivered(n)` *(when transport confirms)*

Emission channels:

- **LocalRuntime:** `vault.signals.doer_event` stream (consumable by future ops plugin and by the existing toast notifier).
- **LambdaRuntime:** structured CloudWatch logs + X-Ray spans.

## 13. Testing strategy

### 1. Handler unit tests via `TestRuntime`

The everyday loop. Examples:

```python
def test_apply_creates_offer():
    rt = TestRuntime(plugin=acme_handlers, role="regulator")
    rt.send(route="/license/apply",
            payload={"app_id": "A1"},
            sender="EAlice...")
    assert rt.outbox.last.is_offer()
    assert rt.state.get(("application", "A1"))["status"] == "received"

def test_high_risk_workflow_escalates():
    rt = TestRuntime(plugin=acme_handlers, role="regulator")
    rt.aggregate("application", "A1").risk_score = 0.9
    rt.send(route="/license/apply", payload={"app_id": "A1"}, sender="EAlice...")
    assert rt.workflow("apply_to_grant", "A1").current_step == "escalate_to_human"
```

`hypothesis` strategies for valid AIDs, SAIDs, and CESR-compatible payloads ship with the library.

### 2. Integration tests against real adapters

- **LocalRuntime integration:** `LocalRuntimeFixture` boots a temporary `Habery` + the runtime; sends real CESR-encoded messages through full verification. Lives in `tests/integration/local/`. Aligns with Locksmith's `qapp` + `QT_QPA_PLATFORM=offscreen` pattern.
- **LambdaRuntime integration:** `tests/integration/aws/` runs the Lambda entrypoint locally with `localstack`-backed DynamoDB.
- **End-to-end (not in CI):** dev-control harness from Locksmith's `tools/devctl.py` drives two vaults exchanging real signed messages.

### Layout

```
tests/
  unit/                # TestRuntime-based + framework internals; fast
  integration/
    local/             # Real Habery, real verification
    aws/               # Lambda entry point + DynamoDB local
  conftest.py          # Shared fixtures
```

CI runs `unit/` + `integration/local/` on every PR. `integration/aws/` runs in a separate workflow.

## 14. Slice breakdown

Four slices. Handler-facing API is locked at v0.1; later slices only add features.

### v0.1 — Primitive core *(~2–3 weeks)*

**In:** `@command(route=..., schema=...)`; full `Context` minus `aggregate`/`workflow`; `Decision.none/emit/grant/admit/spurn/offer/agree/apply/parallel`; KV state with LMDB + DynamoDB + dict backends; `LocalRuntime`, `LambdaRuntime`, `TestRuntime`; framework idempotency on `ctx.message_said`; DLQ (N=5, 30-day retention); telemetry signal emission; plugin entry-point discovery; one reference "echo" plugin.

**Out:** Template binding, aggregates, workflows, scheduling, multisig identity.

**Success criteria:**

- A single `acme_handlers` package runs in **Locksmith** AND **keria-aws Lambda**, unchanged.
- Round-trip `/license/apply` → `Decision.offer` test passes in both runtimes.
- DLQ test: handler that always raises produces 5 retries then a DLQ entry.
- `TestRuntime` tests run < 1s each.

### v0.2 — Template-aware sugar *(~2–3 weeks)*

**In:** `@command(template=..., command_id=...)` + `@reaction(template=..., reaction_id=...)`; Pydantic coercion from template `payload_schema`; auto-validation of payload + auth/state/temporal preconditions; `ctx.aggregate(name, id)` event-sourced view; `Decision.emit_event`; template loader via the existing `micro_app_template/validate.py`.

**Out:** Workflow engine, scheduling, identity.

**Success criteria:**

- `grants-carrier-license` worked example template's commands map cleanly to template-bound handlers.
- Precondition failure produces a `spurn` per `failure_policy` before the handler runs.
- Aggregate replay test: given N events, projected state matches expected Pydantic model.

### v0.3 — Workflows + scheduled callbacks *(~3–4 weeks)*

**In:** Workflow engine reading template `workflow` primitives; `Decision.advance`, `Decision.schedule`, `Decision.start_workflow`; `@workflow_step`, `@scheduled`; `SchedulerDoer` (local) + EventBridge Scheduler integration (Lambda); failure-policy + timeout handling; operational telemetry emissions (workflow trace stream).

**Out:** Multisig identity.

**Success criteria:**

- Full IPEX flow (`apply → offer → agree → grant → admit`) drives a workflow instance to completion in both runtimes.
- Timeout test: `agree` doesn't arrive in time → workflow advances to a declared timeout-handling step.
- Scheduled callback fires 90 days later via `TestRuntime.advance_time`.

### v0.4 — Cross-runtime identity *(~3–4 weeks)*

**In:** Provisioning CLI for multisig group AID setup; optional delegation from org-root AID; both adapters route outbound signing through the group; rotation handshake; member loss / compromise recovery.

**Out:** Cross-runtime state coordination.

**Success criteria:**

- Same role-AID's KEL observed identically by counterparties regardless of which runtime handled a given message.
- Rotation test: group rotation event signed by one member, accepted by the other, propagated to witnesses.
- Compromise test: org-root revokes a group member; runtime ceases signing on that member's behalf.

## 15. Open questions

Each carried into the slice it belongs to, not blocking this design:

- **Plugin entry-point declaration shape.** Manifest function vs auto-discovery of decorated callables. Decided in v0.1 spec.
- **v0.2 Pydantic coercion semantics.** How strict — drop unknown fields, reject, or coerce? Decided in v0.2 spec.
- **v0.3 Lambda scheduling cost model.** Per-EventBridge-rule cost vs alternate (SQS delay queues, DynamoDB TTL + Lambda Stream consumer). Decided in v0.3 spec.
- **v0.4 multisig group provisioning UX.** CLI flow, manual coordination, or fully automated. Decided in v0.4 spec.
- **Future operational-viewer plugin.** Separate design when v0.3 telemetry is in place.
- **Cross-runtime state coordination.** Future (post-v1) design.

## 16. Glossary

See §3.
