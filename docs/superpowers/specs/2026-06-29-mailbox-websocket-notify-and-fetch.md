# Mailbox WebSocket "Notify-and-Fetch" — Serverless-Only Design & Implementation Handoff

> **Status:** Design approved (brainstorming). Not yet planned or built.
> **Created:** 2026-06-29. **Revised:** 2026-06-30 — **pivoted to serverless-only**
> (dropped the "keep SSE long-poll for standard KERI clients" goal; see §1).
> **Audience:** the Claude Code agent that will implement this. Assumes you have
> *not* read the prior conversation. Everything you need is here or cited by
> `file:line`.
> **Scope spans two repos:** the serverless mailbox **infra** lives in
> `~/code/keripy` (`keri_cdk/`); the **client** lives in this repo,
> `~/code/locksmith`. You will touch both, plus produce a reusable **client
> library** (§7). Read "Repo & push rules" (§13) before committing anything.

---

## 0. TL;DR

We are converting the serverless KERI mailbox to a **serverless-only delivery
model**: a **WebSocket API** for a persistent, idle, near-free connection, plus an
on-demand **fetch** of the actual messages. There is **one** supported client
shape — "notify-and-fetch":

1. The client opens **one idle WebSocket** and subscribes (with a signed KERI
   `qry`). It then waits, burning **zero Lambda** and only cheap connection-minutes
   (~$0.011/connection/month). It keeps the socket alive with **free ping control
   frames**.
2. When mail arrives, the mailbox pushes a tiny **nudge** (`{pre, topic, cursor}`
   — *not* the message; ≪ 128 KB).
3. The nudge wakes the client, which performs a **one-shot fetch**: POST its signed
   `qry`, receive the CESR backlog past its cursor, and the connection **closes
   immediately**. No held-open long-poll.

**What changes vs. today:** the current mailbox holds an SSE response open for up
to **780s** per connection, polling every ~1s, and stock clients reconnect
back-to-back — so there is effectively **always a live, billed Lambda per active
subscriber, all day**. We are **removing** that held-open long-poll entirely.
Lambda will run only on: connect/disconnect, subscribe, nudge fan-out, and an
on-demand fetch.

**We are NOT keeping a standard-KERI-client compatibility path.** Stock keripy /
signify-ts / keria clients that expect the SSE long-poll will **no longer work**
against this mailbox. That is an accepted, deliberate trade (see §1). Onboarding
is handled by shipping a **client library** (§7) and updating the clients we
control (Locksmith first).

**The load-bearing design choice (unchanged):** the WebSocket carries a
**notification only**, never the payload. The heavy, signature-verified,
cursor-correct CESR delivery stays on an HTTP signed-`qry` fetch. This dissolves
the three things that otherwise make WS hard for KERI (see §3) and avoids
128-KB-frame chunking of large ACDCs.

---

## 1. Decision: serverless-only (no standard-client compatibility)

Earlier framing considered keeping the SSE long-poll alongside WS so stock KERI
clients kept working. **That goal is dropped.** The mailbox now targets **only
serverless-respecting clients**. Rationale and consequences:

- **Why drop it:** the held-open SSE long-poll is the entire cost problem. Keeping
  it means keeping an always-on-per-subscriber Lambda forever. Supporting it *and*
  WS doubles the surface for no benefit to the clients we actually run.
- **Why this is acceptable now:** we control the clients (Locksmith and friends)
  and will make adoption easy with a **client library** + updates. We are not
  obligated to serve arbitrary third-party stock clients on this mailbox.
- **What breaks:** any client still doing the stock keripy `qry r=/mbx` SSE
  long-poll. After cutover those clients get a one-shot drain (or an error,
  depending on §5.4's chosen behavior) instead of a held stream, and their
  continuous-poll assumption no longer holds. **They must adopt the library.**
- **Upstream-compat caveat (read §13):** this consciously relaxes the keripy
  `CLAUDE.md` rule *"keep wallet-facing changes upstream-compatible."* We mitigate
  by building the client library on **stock keripy primitives** (`hab.query`,
  `psr.parse`) so only the *transport* diverges, not the crypto/event layer.

We still **reject pushing full CESR over WebSocket** (the "WS as full transport"
option): ACDC credentials exceed the 128 KB frame cap, forcing chunk/reassemble
and per-frame billing, with no upside over an HTTP fetch that has no size cap.
**Notify-and-fetch remains the mechanism.**

> **Do not try to raise the 128 KB limit — it is a HARD quota.** Per the AWS API
> Gateway WebSocket quotas table (verified 2026-06-30), both **WebSocket frame
> size (32 KB)** and **message payload size (128 KB)** are marked **"Can be
> increased: No"** — a service-quota request will be declined. (A message over
> 128 KB doesn't truncate; the connection closes with code **1009**.) Connection
> duration (2 hr) and idle timeout (10 min) are likewise non-adjustable. The only
> adjustable WebSocket quotas are connection-rate/counts (new-connections/sec,
> routes, integrations). The 128 KB cap is therefore a fixed boundary we **route
> around** via the HTTP fetch — not a limit to negotiate. The only way to "push
> large payloads over a socket" on AWS is to abandon API Gateway WebSockets for
> self-managed sockets (Fargate/ECS), which forfeits the serverless idle-cost win
> that motivates this whole design. Source:
> https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-execution-service-websocket-limits-table.html

---

## 2. Background: how the mailbox works today (read before coding)

### 2.1 The infra (keripy `keri_cdk/`)

- **Stack:** `keri_cdk/mailbox_stack.py` (`MailboxStack`). A Falcon ASGI app under
  **uvicorn + AWS Lambda Web Adapter (LWA)**, exposed via API Gateway **REST API**
  with native response streaming (`ResponseTransferMode.STREAM`, 15-min integration
  timeout). arm64, python3.14, two layers (`KeriRuntimeLayer` + AWS LWA), 1024 MB,
  no reserved concurrency.
- **Handler:** `keri_cdk/handlers/mailbox/mailbox_handler.py`. Routes `/` (status +
  CESR ingest), `/status` (LWA readiness), `/oobi/*`.
- **Deposit path** (`RootResource._ingest`, `mailbox_handler.py:532-578`): a POST
  of a signed `/fwd` exn is parsed (`_hby.psr.parse(... framed=True)`); the
  `ForwardHandler` (registered at `init()`, `:278-279`) routes it to
  `_hby.db.storeMsg`. **Returns `204`.** This deposit path is **kept** (senders
  still deposit over HTTP).
- **Poll path (being REPLACED):** if the body is a `qry` with `r=/mbx`
  (`_detect_mbx_query`, `:369-383`), the handler replies `200 text/event-stream`
  and attaches the async **long-poll** generator `_stream_mbx_response`
  (`:386-435`) — initial drain, then poll `cloneTopicIter` every ~1s, `:keepalive`
  every 240s, up to a **780s soft cap**. **This held-open behavior is what we
  remove (§5.4).**
- **One-shot drain already exists:** `_format_sse_events(hby, pre, topics)`
  (`:338-366`) walks `cloneTopicIter` once and returns the SSE body, empty if no
  new messages. It is currently **unused** (the long-poll generator was wired in
  instead at `:574`). The serverless fetch reuses this.
- **Storage:** `Mailboxer` (`keri/app/storing.py`). Each topic is an
  ordinal-numbered `tpcs.` sub. `storeMsg(topic, msg)` (`:109-129`) appends at the
  next ordinal `on` and returns a bool (does **not** return `on` — see §5.5).
  Topic key is `f"{recipient_pre}/{topic}".encode()`.
- **Auth model:** no bearer tokens anywhere. A `qry`/`exn` is signed CESR, verified
  against the sender's KEL the mailbox already holds (clients publish their
  inception via POST `/` → 204 before querying).
- **DB backend:** `DynamoDBer` (`src/keri/db/dynamodbing.py`) over a shared core
  table, LeadingKeys-scoped to `{STACK_NAME}:mbx`. Point reads strongly
  consistent; GSI reads eventually consistent. The connection registry (§5.2) is a
  brand-new **private** table — do **not** touch `SHARED_KEL_STORES` or the witness
  first-seen gate (unrelated subsystems; see keripy `CLAUDE.md`).
- **Reference client / contract:** `keri_cdk/probes/mailbox_conformance/probe.py`.
  Will need rework for the serverless-only model (§11).

### 2.2 The client (Locksmith, this repo)

- Python 3.14, **PySide6 desktop app** (not a browser → can set WS handshake
  headers and speak any dialect). Async via `hio` DoDoer + `qasync` Qt bridge.
- Locksmith maintains its own fork of the mailbox client:
  `src/locksmith/core/indirecting.py` — `MailboxDirector` (lines 26-288) and
  `Poller` (lines 290-407). Today `Poller.eventDo` (`:320-407`) builds
  `hab.query(pre, src=mailbox, route="mbx", query={pre, topics})`, POSTs it
  (`httping.createCESRRequest`, `:356-368`), waits ~30s for SSE `{id,data,name}`
  events (`:383-403`), persists last-seen id per topic in `witrec.topics[tpc]`
  (`:401`), and retries on a ~30s cadence (`:406`).
- **This continuous-poll loop is what the serverless client replaces** with a
  WS-driven one-shot fetch (§7). The CESR-parsing/cursor-persistence parts are
  reused; the *trigger* and *transport hold* change.
- **Topics** (`vaulting.py:154`): `['/receipt', '/multisig', '/replay',
  '/delegate', '/credential', '/challenge', '/reply']`.
- **Endpoint discovery is OOBI-based:** `agenting.httpClient(hab, mailbox_eid)`
  resolves the URL from the KEL (`hab.db.ends` / `fetchUrls`). No hardcoded URL.
- No WebSocket usage exists in Locksmith today (greenfield).

### 2.3 The KERI communication model (the non-obvious part)

KERI is **asynchronous message-passing over self-framing CESR streams; HTTP is
just an envelope.** A "reply" is a new, independently-signed message routed to the
recipient's endpoint, not an HTTP response. Mailboxes store messages for an
offline AID; senders deposit (`/fwd` exn → 204), recipients fetch (`qry r=/mbx`).
Messages flow through topics with per-topic monotonic ordinals (cursors). Full
field guide: `~/code/KERI-COMMUNICATION-MODEL.md` — **read its TL;DR + §3
(direct/indirect mode) before changing delivery semantics.**

Consequence for this work: **the WS nudge is not a KERI message.** It is an
out-of-band hint ("there is new mail"). Real KERI message-passing — signature
verification, cursors — stays on the signed-`qry` fetch where it already works.

---

## 3. The three things that make WS hard for KERI — dissolved by notify-and-fetch

1. **Auth is signature-based, not tokens.** → Verify the signed `qry` **on the WS
   subscribe message** (reusing the REST handler's `psr.parse`), not via a
   `$connect` token authorizer. Unsubscribed connections never get nudged.
2. **128 KB frame cap vs. large CESR (ACDCs exceed it).** → Nudges are tiny JSON;
   the big CESR rides the HTTP fetch which has no per-message cap.
3. **"Event source" is internal, not EventBridge/SNS.** → The deposit handler
   (already holding recipient AID + topic) fires the nudge itself (§5.4).

---

## 4. Architecture

```
 Sender (any KERI controller)
   │  POST /fwd exn  (signed CESR, over HTTPS — UNCHANGED, still 204)
   ▼
 ┌──────────────────────── MailboxStack (keri_cdk) ────────────────────────┐
 │  REST API                              WebSocket API (NEW)               │
 │   /  /status  /oobi/*                   $connect $disconnect $default     │
 │   POST / → deposit (204)                 │                                │
 │   POST / → fetch (ONE-SHOT drain,        ▼                                │
 │            returns + closes; NO          WS handlers ──▶  Connection      │
 │            long-poll)                    (subscribe =     Registry (NEW   │
 │   │                                       verify signed    DynamoDB)      │
 │   │  after storeMsg:                       qry, register)                 │
 │   └── nudge ──▶ PostToConnection ──────────────────────────────┐         │
 └────────────────────────────────────────────────────────────────┼────────┘
        ▲ one-shot CESR drain (200, returns when backlog empty)     │ wss:// nudge
        │                                                           ▼
        └──────────────  Serverless notify-and-fetch client  ◀──────
                         (Locksmith + others, via CLIENT LIBRARY §7)
                          • holds ONE idle WS (free pings) — 0 Lambda idle
                          • subscribe = signed qry over WS
                          • on nudge → one-shot fetch over HTTP → close
                          • reconnect w/ backoff; infrequent safety-net fetch
```

**There is no standard-client branch.** The only supported reader is the
serverless notify-and-fetch client.

**Invariant:** a connected client burns **no Lambda while idle**. Lambda runs only
on connect/disconnect/subscribe, nudge fan-out, and on-demand fetch.

---

## 5. Infra implementation (in `~/code/keripy`, `keri_cdk/`)

> CDK WebSocket constructs are confirmed importable in the keripy venv:
> `aws_cdk.aws_apigatewayv2.{WebSocketApi,WebSocketStage,WebSocketRouteOptions}`,
> `aws_cdk.aws_apigatewayv2_integrations.WebSocketLambdaIntegration`,
> `aws_cdk.aws_apigatewayv2_authorizers.WebSocketLambdaAuthorizer`. The deprecated
> `@aws-cdk/aws-apigatewayv2-alpha` packages are not used.

### 5.1 WebSocket API (extend `MailboxStack`)

Add to `keri_cdk/mailbox_stack.py`, in the same stack as the REST API:

```python
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk.aws_apigatewayv2_integrations import WebSocketLambdaIntegration

ws_api = apigwv2.WebSocketApi(
    self, "MailboxWsApi",
    route_selection_expression="$request.body.action",
    connect_route_options=apigwv2.WebSocketRouteOptions(
        integration=WebSocketLambdaIntegration("WsConnectInt", ws_connect_fn),
    ),
    disconnect_route_options=apigwv2.WebSocketRouteOptions(
        integration=WebSocketLambdaIntegration("WsDisconnectInt", ws_disconnect_fn),
    ),
    default_route_options=apigwv2.WebSocketRouteOptions(
        integration=WebSocketLambdaIntegration("WsDefaultInt", ws_default_fn),
    ),
)
ws_stage = apigwv2.WebSocketStage(
    self, "MailboxWsStage", web_socket_api=ws_api,
    stage_name="prod", auto_deploy=True,
)
ws_api.grant_manage_connections(self.fn)              # self.fn = existing handler
self.fn.add_environment("WS_CALLBACK_URL", ws_stage.callback_url)
self.fn.add_environment("WS_CONN_TABLE", conn_table.table_name)
```

- **Route selection** `$request.body.action`: the subscribe envelope is JSON
  `{"action":"subscribe", ...}`. The skeleton defines **no** custom `subscribe`
  route, so `action:"subscribe"` falls to `$default` → `ws_default_fn` (which
  dispatches on `action`). Or add `ws_api.add_route("subscribe", integration=...)`
  and move the logic there — pick one, be consistent.
- **No `$connect` authorizer** in the MVP (KERI has no token to check there; we
  authenticate the subscribe message). Revisit in §9.
- `ws_stage.url` → `wss://{id}.execute-api.{region}.amazonaws.com/prod` (connect
  URL). `ws_stage.callback_url` → `https://…/prod` (Management API endpoint).

### 5.2 Connection registry (NEW, private DynamoDB table)

Dedicated and private — **not** the shared core table, **not** a DynamoDBer store.

- Billing: **on-demand**.
- **PK:** `connectionId` (S) — for idempotent `$disconnect` delete.
- **GSI `byPre`:** PK `pre` (S) — notifier finds all live connections for a
  recipient AID without a scan.
- Attributes: `pre`, `topics` (map `{topic: lastCursor}` from the signed
  subscribe), `connectedAt`, `expireAt` (N).
- **TTL** on `expireAt` = `now + ~7800s` (margin past the WS 2-hr max), a backstop
  for abandoned rows. Primary cleanup is `$disconnect` + `GoneException` (§5.4).

### 5.3 WS handlers (connect / disconnect / subscribe)

Package from the mailbox handler asset (or a sibling) so they can reuse the keri
stack. The subscribe handler needs the full Habery (heavy cold start — same as the
existing mailbox Lambda), which is fine because it runs only on subscribe, never
while idle.

- **`$connect`** (`ws_connect_fn`): lightweight; return `200` to accept. No row yet.
- **`$disconnect`** (`ws_disconnect_fn`): lightweight; `DeleteItem` by
  `connectionId`. **Idempotent**; never assume it runs (best-effort).
- **subscribe** via `$default` (`ws_default_fn`): **heavy**.
  1. Parse JSON envelope `{"action":"subscribe", "qry":"<qb64 CESR>"}`.
  2. **Accept the embedded `qry` with EXACTLY the native mailbox acceptance check**
     (reuse `_detect_mbx_query`, `:369-383`): it must be a well-formed `qry r=/mbx`
     and its mailbox owner `q["i"]` (canonical; or `q["pre"]`) must be a known AID
     (`pre in _hby.kevers`) — mirroring keripy's `Kevery.processQuery`
     (`escrowQueryNotFoundEvent` when `pre not in kevers`). If not, reply with an
     error frame and **do not register**.
  3. `PutItem` the registry row `{connectionId, pre, topics, connectedAt,
     expireAt}`.
  4. Optionally push an initial nudge so the client drains any backlog immediately
     (or let the client do one fetch right after subscribe — §7).
- The KERI `qry` stays a signed CESR blob carried inside the JSON envelope. We
  transport the existing signed `qry` over WS; we do not invent a new auth scheme.

> **DECISION REVISION (2026-06-30, native parity):** an earlier draft of step 2
> said "verify the embedded signed `qry`… if the signature can't be verified, do
> not register." That was **dropped** as a non-native invention. keripy's own
> mailbox (`Kevery.processQuery`, `parsing.py:1463`) does **not** cryptographically
> verify the `qry` signature — acceptance is structural + `q["i"] in kevers`. To
> BE KERI NATIVE, the WS subscribe applies that **same** check and **no signer↔owner
> binding** — the serverless mailbox has the identical trust model as the live
> federation witnesses. Consequence (accepted): anyone who knows an AID can
> subscribe/drain its mailbox, exactly as in native KERI (contents are
> sender-signed; privacy, if needed, comes from sealed/encrypted payloads — a
> separate, explicit, future KERI-native mechanism, NOT a subscribe gate). Abuse/
> compute is handled by **WAF rate-limiting (fast-follow)**, not this gate.

### 5.4 The fetch (one-shot drain) — REPLACES the long-poll

This is the core change from today's behavior.

- Keep detecting `qry r=/mbx` on POST `/` (`_detect_mbx_query`).
- **Stop attaching the held-open generator `_stream_mbx_response`.** Instead
  respond with a **one-shot drain that returns as soon as the backlog is exhausted
  and closes** — there is no 780s hold, no keepalive, no ~1s re-poll. The one-shot
  formatter **already exists**: `_format_sse_events(hby, pre, topics)`
  (`mailbox_handler.py:338-366`). Wire it as the response body, then close.
  - **Decision (recommended, can be vetoed):** keep emitting the result as
    `text/event-stream` framing (`id/event/data`) so the client parser is
    unchanged from the SSE shape — but the response **terminates immediately**
    after the drain. Alternatively return `application/cesr` as a plain body; the
    client library then parses one CESR stream. Either works; the SSE framing
    reuses the most existing client code.
  - **Large drains:** a one-shot non-streaming API GW REST response is capped
    (~6–10 MB). If a single drain can exceed that (big ACDC batches), keep LWA
    response streaming but operate it in **drain-only** mode (stop after the
    backlog, don't long-poll). Confirm expected drain sizes (§9); default to
    streaming-drain since it already exists and handles any size.
- **Implication:** since no client long-polls anymore, the 780s soft cap, the
  keepalive logic, and the ~1s re-poll in `_stream_mbx_response` become **dead
  code for the serverless model** and can be removed once the cutover lands. (Keep
  `_stream_mbx_response` only if you choose streaming-drain and refactor it into a
  drain-only generator.)

### 5.5 The notifier (push the nudge)

**MVP — inline in the REST deposit handler** (`RootResource._ingest`,
`:532-578`), which already parses the `/fwd` exn and holds recipient AID + topic:

1. After `_hby.psr.parse(... framed=True)` succeeds and the `/fwd` is stored, add a
   `_detect_fwd(ims)` helper (mirror `_detect_mbx_query`) extracting recipient
   `pre` and `topic` from the exn modifiers `{pre, topic}` (see how the probe
   builds it, `probe.py:103-122`).
2. `Query` the registry GSI `byPre` for live `connectionId`s for that `pre`.
3. For each, `PostToConnection(ConnectionId=cid, Data=json.dumps(nudge))` via
   `boto3.client("apigatewaymanagementapi", endpoint_url=WS_CALLBACK_URL)`.
4. On `GoneException` → `DeleteItem` that row (primary stale cleanup).
5. **Fire-and-forget / best-effort:** wrap in try/except so a slow/dead connection
   never delays or fails the `204` deposit.

**Nudge payload (tiny):**
```json
{"type":"mailbox.nudge","pre":"E…bob","topic":"/credential","cursor":7}
```
`cursor` is **advisory** (lets the client skip a redundant fetch if already past
it); omit if surfacing the ordinal is awkward. (`storeMsg` computes `on` at
`storing.py:128` but returns a bool — to include `cursor`, read the topic tail
after store or make a tiny local change to surface `on`. Optional.)

**Scale-out evolution (note, don't build yet):** decouple via **DynamoDB Streams**
on the core table → a lightweight notifier Lambda (no keri/libsodium; nudges
only). Deposit returns `204` immediately; notifier fans out async. Costs: enable
Streams; notifier filters to its `{STACK_NAME}:mbx` namespace + `tpcs.` writes and
resolves recipient+topic from the key. MVP stays inline.

### 5.6 IAM

- Pushing Lambda (REST deposit handler, MVP) needs `execute-api:ManageConnections`
  via `ws_api.grant_manage_connections(self.fn)` (don't hand-write the ARN).
- WS handlers scoped tightly: `$connect` none, `$disconnect` `DeleteItem`,
  subscribe `PutItem` + `Query`(GSI); notifier `Query`(GSI) + `DeleteItem`.
- Handlers that verify signed qrys also need the existing core-table + Secrets
  Manager access (Habery). Reuse the policy pattern at `mailbox_stack.py:154-191`.

### 5.7 WSS URL discovery

KERI `loc/scheme` has no `ws`/`wss` scheme. MVP: expose the `wss://` connect URL in
the existing `GET /` status JSON (add `"ws":"wss://…/prod"` in `RootResource.on_get`,
`:517-524`) and/or via `CfnOutput`. The client library reads `GET /` to learn the
WS endpoint. (OOBI-native WS discovery is out of scope.)

---

## 6. (removed) Coexistence

There is no coexistence section anymore — serverless-only means there is no second
channel to coexist with. See §8 (cutover/migration) for how existing deployments
move over.

---

## 7. Client: the serverless mailbox library

The user's goal is to **make serverless clients easy to build**. Ship a small,
reusable **client library** that any serverless-respecting client imports to get
notify-and-fetch behavior, then wire Locksmith to it as the first consumer.

### 7.1 Library responsibilities

A focused module (Python first; e.g. a `serverless_mailbox` package, or a new
module under Locksmith with a clean public surface that can be extracted later):

1. **Discover** the mailbox `wss://` URL from `GET /` status (§5.7) given the
   mailbox HTTP URL / EID.
2. **Connect** one WebSocket (asyncio client compatible with the host loop;
   `websockets` or `aiohttp` — match the consumer's deps, see §9). Send the signed
   **subscribe** envelope `{"action":"subscribe","qry":"<signed qry>"}`. Build the
   `qry` with **stock keripy primitives**: `hab.query(pre, src=mailbox,
   route="mbx", query={pre, topics})` — identical to what the current Poller builds
   (`indirecting.py:356-368`), just wrapped in the JSON envelope instead of POSTed.
3. **On nudge** (`{type:"mailbox.nudge", pre, topic, cursor}`): perform a
   **one-shot fetch** — POST the signed `qry` for that topic from the client's
   last-seen cursor, parse the returned CESR with `psr`, advance the cursor. This
   reuses the existing CESR-handling code; only the trigger differs.
4. **Keep-alive:** send WS **ping control frames** more often than every 10 min
   (the idle-timeout) — free, no Lambda.
5. **Reconnect / lifecycle:** on close (10-min idle if pings lapse, 2-hr hard cap,
   network drop) reconnect with exponential backoff and re-subscribe with current
   cursors.
6. **Safety-net fetch:** an **infrequent** periodic fetch (e.g. every few minutes)
   to catch any missed nudge. This is *not* the old 30s treadmill — it's a rare
   backstop, so idle cost stays near zero.
7. **Expose a clean API** to the host app: start/stop, "on message" callback,
   current cursors, connection state. Keep KERI specifics (qry building, parsing)
   inside; let the host app just receive messages.

### 7.2 Locksmith integration (this repo)

- Replace the continuous-poll loop in `src/locksmith/core/indirecting.py`
  (`MailboxDirector`/`Poller`) with the library's WS-driven client, wired into the
  same `hio` DoDoer the MailboxDirector runs under. Reuse the topic list
  (`vaulting.py:154`) and the cursor-persistence in `witrec.topics`.
- The old `Poller.eventDo` ~30s SSE loop is retired for this mailbox. Keep the
  message-handling / escrow plumbing (`msgDo`, `escrowDo`) — only the
  fetch *trigger and transport* change.
- Locksmith pytest requires `--import-mode=importlib` (Locksmith `CLAUDE.md`).

### 7.3 Other clients

Any other serverless client adopts the same library (or a port). Because the
library builds on stock keripy primitives, a non-Python client (e.g. a future
signify-ts consumer) can mirror the same contract: discover WS URL → connect →
signed-qry subscribe → on nudge, one-shot signed-qry fetch.

---

## 8. Cutover / migration (this is a breaking change)

Removing the held-open long-poll **breaks** any client still doing the stock SSE
poll. Plan the rollout:

1. **Ship the client library + update Locksmith** to notify-and-fetch first.
2. **Deploy infra additively:** add the WS API, registry, nudge fan-out, and the
   one-shot fetch *before* removing the long-poll, so updated clients can move over
   while the old path still answers. (The fetch can serve both an updated client's
   one-shot drain and, transitionally, a legacy poll — though a legacy client
   long-poll will simply get a drain-and-close.)
3. **Confirm all clients you care about are updated.**
4. **Remove the long-poll machinery** (`_stream_mbx_response` hold, 780s cap,
   keepalive) once nothing depends on it.
5. Mind the keri.host federation: this touches every `Mailbox{slug}` stack. Roll
   stacks consistently; don't leave half the federation on long-poll.

There is **no** mixed-fleet steady state by design — the end state is
serverless-only.

---

## 9. Open decisions for the integrator

1. **Fetch response shape.** SSE framing terminated-after-drain (max client-code
   reuse) vs `application/cesr` plain body. Recommended: SSE-framed one-shot.
2. **Large-drain transport.** Plain REST response (~6–10 MB cap) vs LWA
   streaming-drain. Confirm max drain size; default to streaming-drain.
3. **`$connect` admission control.** MVP accepts all connects, registers only on a
   valid signed subscribe, TTL-reaps the rest. Add an authorizer / "subscribe
   within N seconds or close" policy only if abuse appears on the public endpoint.
4. **Notifier topology.** Inline-in-deposit (MVP) vs DynamoDB-Streams (scale).
   Confirm expected concurrent connection counts.
5. **Nudge granularity / cursor.** Per-topic `{pre, topic, cursor}` (recommended)
   vs coarse "you have mail"; exact ordinal vs advisory/omitted.
6. **Client WS library.** `websockets` vs `aiohttp` — match host (`hio`/`qasync`)
   deps.
7. **Library packaging.** Standalone installable package vs a Locksmith module
   with a clean surface to extract later.
8. **Stage names / environments / regions.** Match federation conventions
   (stack-name-derived).

---

## 10. Acceptance criteria (Given/When/Then)

**Infra (keripy):**
- **Subscribe registers state.** *Given* a valid signed `qry r=/mbx` sent as a WS
  `subscribe`, *then* a registry row keyed by `connectionId` exists with `pre`,
  `topics`, TTL; an invalid/unverifiable qry registers **nothing** and returns an
  error frame.
- **Disconnect cleans up (idempotently).** *Given* a registered connection, *when*
  `$disconnect` fires (or the row is already gone), *then* it's removed without
  error.
- **Deposit nudges live connections.** *Given* a live registered connection for
  `Ebob`, *when* a `/fwd` for `Ebob/credential` is deposited, *then* the client
  gets a `mailbox.nudge` for that topic **and** the deposit still returns `204`
  promptly (nudge never blocks it).
- **Fetch is one-shot (NO long-poll).** *Given* a `qry r=/mbx`, *when* the handler
  responds, *then* it drains the backlog past the cursor and **the response
  completes/closes immediately** — no 780s hold, no keepalive frames.
- **Stale connection reaped on push.** *Given* a closed connection, *when* the
  notifier `PostToConnection`s, *then* `GoneException` is caught and the row
  deleted.
- **Idle WS consumes no Lambda.** *Given* an open idle connection with no mail,
  *then* no Lambda invocations are attributable to it.

**Client / library:**
- **Nudge triggers a one-shot fetch.** *Given* a connected client past cursor N,
  *when* a nudge arrives, *then* the library fetches topic>N over the signed-qry
  path, advances the cursor, and surfaces the messages to the host app.
- **Idle is cheap.** *Given* no mail, *when* time passes, *then* the client holds
  the socket with pings and performs no fetches except the infrequent safety-net.
- **Reconnect recovers.** *Given* a 2-hr cap or network drop, *when* the socket
  closes, *then* the client reconnects with backoff and re-subscribes with current
  cursors; no messages are lost (drains are idempotent via persisted cursors).

**Migration:**
- **Additive deploy is safe.** *Given* the WS API + fetch are deployed before the
  long-poll is removed, *then* updated clients work and the system is functional
  throughout the cutover.

---

## 11. Testing

- **Infra:** rework `keri_cdk/probes/mailbox_conformance/probe.py` for
  serverless-only: (a) connect WS + signed subscribe; (b) deposit `/fwd` over REST
  (reuse `_make_fwd_message`, `probe.py:103-122`); (c) assert a nudge frame
  arrives; (d) assert the **one-shot fetch returns the backlog and closes**
  (replace the old "stream stays open" assertions, e.g.
  `test_mbx_query_returns_streaming_response`, with "drain then EOF").
- **CDK synth tests** (keripy `tests/cdk/`): assert the stack synth includes the
  WS API, stage, registry table (PK `connectionId`, GSI `byPre`, TTL), and the
  `grant_manage_connections` policy.
- **Client/library:** Locksmith pytest (`--import-mode=importlib`) — unit test
  nudge→fetch wiring with a fake WS feeding nudge frames into a stubbed fetch;
  reconnect/backoff; safety-net fetch cadence; cursor idempotency.

---

## 12. Cost model (verify current rates/region)

- **WS messages:** ~$1.00 / million (32 KB increments; **control frames free**).
- **WS connection-minutes:** ~$0.25 / million; one connection/month ≈ 43,200
  conn-min ≈ **$0.011**.
- **Lambda:** runs only on connect/sub/nudge-fanout/fetch. No held-open compute.
- **Net vs. today:** replaces an always-on-per-subscriber Lambda (held SSE
  long-poll, reconnecting back-to-back) with a near-free idle socket + on-demand
  fetch. Cost scales with concurrent-connection-count × hold-time, not held
  compute.

---

## 13. Repo & push rules (read before committing)

- **keripy** (`~/code/keripy`): `seriouscoderone` fork. **Push to `fork` ONLY —
  never `origin`/WebOfTrust.** Build the arm64 runtime layer
  (`keri_cdk/layers/build_layer.sh`, needs Docker) before synth/deploy. `moto`
  required for DynamoDBer tests.
- **locksmith** (`~/code/locksmith`): `origin` = `seriouscoderone`, `upstream` =
  `keri-foundation`. **Upstream-compat note:** the keripy `CLAUDE.md` rule "keep
  wallet-facing changes upstream-compatible" is **consciously relaxed** for the
  mailbox *transport* — a serverless-only mailbox no longer speaks the stock SSE
  long-poll. Mitigation: the client library builds on **stock keripy primitives**
  (`hab.query`, `psr.parse`), so the crypto/event layer stays compatible and only
  the transport/trigger diverges. Surface this to the maintainers; it's a
  deliberate divergence, not an accident.
- Keep the two halves on separate branches in their respective repos.

---

## 14. File / path map

**keripy (infra):**
- `keri_cdk/mailbox_stack.py` — add WS API + stage + registry table + IAM + env.
- `keri_cdk/handlers/mailbox/mailbox_handler.py` — add `_detect_fwd` + nudge
  fan-out in `_ingest`; switch the fetch from `_stream_mbx_response` (long-poll) to
  `_format_sse_events` (one-shot, `:338-366`); add the `ws` field in `GET /`; add
  the WS connect/disconnect/subscribe handlers (here or a sibling module); retire
  the 780s/keepalive long-poll after cutover.
- `keri_cdk/probes/mailbox_conformance/probe.py` — serverless-only conformance.
- `tests/cdk/` — synth assertions.
- Reference (don't break): `src/keri/app/storing.py` (`Mailboxer.storeMsg`,
  `cloneTopicIter`), `src/keri/db/dynamodbing.py`, keripy `CLAUDE.md`.

**locksmith (client + library):**
- New `serverless_mailbox` library (package or `src/locksmith/core/` module with a
  clean public surface) — WS connect, signed-subscribe, nudge→one-shot-fetch,
  ping, reconnect/backoff, safety-net fetch.
- `src/locksmith/core/indirecting.py` — replace the continuous `Poller` loop with
  the library client; keep `msgDo`/`escrowDo` plumbing and cursor persistence.
- `src/locksmith/.../vaulting.py` — wire the library into the DoDoer; reuse the
  topic list (`:154`).
- Locksmith `CLAUDE.md` — pytest `--import-mode=importlib`.

---

## 15. References

- `~/code/KERI-COMMUNICATION-MODEL.md` — canonical field guide (TL;DR + §3). **Read
  first.**
- keripy `CLAUDE.md` — serverless stack conventions, shared-KEL oracle, DynamoDBer
  gotchas, first-seen gate (none of which this work should disturb).
- AWS API Gateway WebSocket developer guide — routes, `@connections`/Management
  API, limits (10-min idle, 2-hr max, 128 KB / 32 KB metering, control frames
  free).
- boto3 `apigatewaymanagementapi` (`post_to_connection`, `GoneException`).
- aws-cdk-lib `aws_apigatewayv2` / `_integrations` / `_authorizers` (WebSocket
  constructs; alpha modules deprecated).
