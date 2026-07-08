# Serverless WS Mailbox (Phase 3 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
> **READ FIRST, in this order:** (1) the WS infra spec `docs/superpowers/specs/2026-06-29-mailbox-websocket-notify-and-fetch.md` — it carries the detailed CDK + handler code this plan sequences; (2) the unified spec `docs/superpowers/specs/2026-06-30-unified-mailbox-architecture-design.md` §4.2/§5/§7 + the §7 deltas; (3) the ledger `.superpowers/sdd/progress.md` (Phase 1+2 record). This plan = task decomposition, acceptance gates, env, the baked §9 decisions, and the new `ServerlessStrategy` code; the bulk infra code lives in the WS spec by `file:line` (cited per task — that is NOT a placeholder, it is the design doc).

**Goal:** Make the serverless KERI mailbox deliver via **WebSocket notify-and-fetch** — an idle WS that pushes a tiny nudge on deposit + a one-shot HTTP drain — replacing the held-open SSE long-poll; fill in the package's `ServerlessStrategy`; advertise the `wss` capability in the KEL; and prove federation mailbox **retrieval** end-to-end (the acceptance Phase 1 deferred).

**Architecture:** Deposit stays HTTP `/fwd`→204. A new API Gateway **WebSocket API** + a private **connection registry** (DynamoDB) hold idle subscriber sockets; the deposit handler fires a **nudge** (`{pre,topic,cursor}`, never the payload) to live connections; the client does a **one-shot signed-`qry` fetch** (the long-poll is removed → drain-and-close). The mailbox AID advertises a signed **`wss` loc scheme** (Phase-2 reader already in place); the package's `ServerlessStrategy` (Phase-2 stub) is filled in.

**Tech Stack:** keripy fork `keri_cdk` (AWS CDK Python — `aws_apigatewayv2` WebSocketApi/Stage + `_integrations.WebSocketLambdaIntegration`; Lambda + LWA; DynamoDB; boto3 `apigatewaymanagementapi`); the `keri-serverless-mailbox` package (`websockets` lib — NEW dep); Locksmith (consumes via the already-wired `MailboxClient`).

## Global Constraints

- **BE KERI NATIVE.** Discovery rides the KEL: the server publishes a signed `wss` loc scheme; the client reads it via `hab.fetchUrl(eid, scheme=Schemes.wss)` (already implemented Phase 2). The WS **nudge is NOT a KERI message** — it's an out-of-band hint; all signature-verified, cursor-correct CESR stays on the signed-`qry` HTTP fetch.
- **Serverless-only server, universal client** (WS spec §1): the federation mailbox serves ONLY notify-and-fetch after cutover; stock-SSE clients break (deliberate). The `keri-serverless-mailbox` client stays universal (Standard SSE for *other* mailboxes).
- **Never push full CESR over WS** (WS spec §1): 128 KB frame cap is a HARD AWS quota — nudges are tiny JSON; payload rides the HTTP fetch.
- **Idle = ~0 Lambda** (WS spec §4 invariant): Lambda runs only on connect/disconnect/subscribe, nudge fan-out, and on-demand fetch.
- **§9 open decisions — BAKED to the WS-spec recommendations (revisit only if a task surfaces a reason):** (1) fetch shape = **SSE-framed, terminated-after-drain** (max client reuse); (2) large-drain = **LWA streaming-drain operated drain-only** (handles any size); (3) `$connect` admission = **MVP accepts all; register only on a valid signed subscribe; TTL-reap** (no authorizer); (4) notifier = **inline in the deposit handler** (MVP; DynamoDB-Streams deferred); (5) nudge = **per-topic `{pre,topic,cursor}`**; (6) WS client lib = **`websockets`**; (7) package already standalone; (8) stage/region = federation conventions (stack-name-derived).
- **WAF rate-limiting = FAST-FOLLOW, not a task here** (add an AWS WAF rate-based rule + 429-with-onboarding-body only if abuse appears). Onboarding *message* IS in scope (Task 5).
- **ENV (critical):** `keri_cdk` CDK/synth work needs `aws_cdk` — that is in the **keripy keri_cdk venv** (locate it under `~/code/keripy`, e.g. its `.venv`; the WS spec §5 confirmed the WS constructs import there), **NOT** the locksmith `.venv` (which has `keri` but no `aws_cdk`). Build the arm64 runtime layer (`keri_cdk/layers/build_layer.sh`, needs Docker) before `cdk synth`/deploy. `moto` for DynamoDBer tests. Package tests: locksmith `.venv` + pyproject `pythonpath=["src","../keripy/src"]` + the new `websockets` dep; `~/code/keripy` must carry the `wss` scheme (now on `development`).
- **Push rules:** keripy → `fork` ONLY (never origin/WebOfTrust). Package (`keri-serverless-mailbox`, public at `usuranceai/keri-serverless-mailbox`) → push when the task ships. Locksmith → `origin`. **Do NOT push / deploy to live AWS without explicit user confirmation** — deploys touch the live keri.host federation (5 `Mailbox{slug}` stacks).
- **Do NOT disturb** (keripy `CLAUDE.md`): `SHARED_KEL_STORES`/the shared-KEL oracle, the witness first-seen gate, the per-witness Receiptor model. The connection registry is a brand-new PRIVATE table, not a DynamoDBer store.

---

## Starting state (Phase 1+2 shipped)

- keripy `development` @ `0caf71ae`: `wss` loc scheme in `Schemes` (client-read live).
- `keri-serverless-mailbox` published `main` @ `9026c93` (public): `MailboxClient`/`MailboxClientDoer`, `StandardStrategy` (SSE), **`ServerlessStrategy` = `NotImplementedError("Phase 3: WS notify-and-fetch")` stub**, `discover_strategy` (selects Serverless when a `wss` loc is advertised — currently never, since no server publishes one yet).
- locksmith `development` @ `1feb1f0`: vault mounts `MailboxClient`; `Poller` retired; `add_poller` idempotent.
- The held-open SSE long-poll (`mailbox_handler.py:386 _stream_mbx_response`, wired at `:574`) is what Phase 3 replaces; the one-shot `_format_sse_events` (`:338`) already exists and is currently unused.

## File / path map

| File | Repo | Change |
|---|---|---|
| `keri_cdk/mailbox_stack.py` | keripy | WS API + stage + connection-registry table + IAM + env (Task 1) |
| `keri_cdk/handlers/mailbox/ws_handlers.py` (new, or in mailbox_handler) | keripy | `$connect`/`$disconnect`/subscribe (Task 2) |
| `keri_cdk/handlers/mailbox/mailbox_handler.py` | keripy | one-shot drain (Task 3); nudge fan-out in `_ingest` (Task 4); `wss` loc publish + `GET /` mode + onboarding headers (Task 5) |
| `tests/cdk/test_*` | keripy | synth assertions (Task 1) |
| `keri_cdk/probes/mailbox_conformance/probe.py` | keripy | serverless-only conformance (Task 7) |
| `src/keri_serverless_mailbox/serverless.py` (new) + `strategy.py` | keri-serverless-mailbox | fill `ServerlessStrategy` (Task 6); `websockets` dep in `pyproject.toml` |
| (locksmith) | locksmith | no code change expected — `MailboxClient` already auto-selects Serverless when `wss` is advertised; Task 8 verifies |

---

## Task 1: CDK — WebSocket API + connection registry + IAM/env

**Files:** Modify `keri_cdk/mailbox_stack.py` (the `MailboxStack` at `:75`; `self.fn` at `:118`); Test `tests/cdk/test_mailbox_ws_stack.py` (new, mirror `tests/cdk/test_core_stack.py` style).
**Interfaces — Produces:** a `WebSocketApi` (`$connect`/`$disconnect`/`$default` → integrations), `WebSocketStage` (`prod`, `auto_deploy`), a private `conn_table` (PK `connectionId` S; GSI `byPre` PK `pre` S; TTL `expireAt`; on-demand billing), `self.fn` granted `execute-api:ManageConnections` via `ws_api.grant_manage_connections(self.fn)`, env `WS_CALLBACK_URL = ws_stage.callback_url` + `WS_CONN_TABLE = conn_table.table_name`.

- [ ] **Step 1 (test):** add a CDK synth test asserting the synthesized template includes the WS API, the WS stage, the registry table (PK `connectionId`, GSI `byPre`, TTL on `expireAt`), and the `grant_manage_connections` policy statement. Use the CDK `assertions.Template.from_stack` pattern from `tests/cdk/test_core_stack.py`. Run with the **keri_cdk venv**: `<keripy-cdk-venv>/bin/python -m pytest tests/cdk/test_mailbox_ws_stack.py -q` → FAIL (constructs absent).
- [ ] **Step 2 (impl):** add the constructs from **WS spec §5.1** (`WebSocketApi`/`WebSocketStage`/`WebSocketLambdaIntegration`, route selection `$request.body.action`, no `$connect` authorizer) + **§5.2** (the registry table) + **§5.6** (IAM) verbatim, into `MailboxStack`. WS handler Lambdas (`ws_connect_fn`/`ws_disconnect_fn`/`ws_default_fn`) point at the assets created in Task 2 (or, MVP, reuse `self.fn`'s asset with distinct handlers — pick per §5.3; be consistent).
- [ ] **Step 3:** run synth test → PASS; `cdk synth` (build the layer first per ENV) produces a valid template. Commit on a keripy branch `feat/mailbox-ws-phase3` off `development`.

## Task 2: CDK — WS handlers ($connect / $disconnect / subscribe)

**Files:** `keri_cdk/handlers/mailbox/ws_handlers.py` (new) or a sibling; Test: handler unit tests with `moto` (DynamoDB) + a stubbed Habery.
**Interfaces — Consumes:** `conn_table` (Task 1). **Produces:** `$connect`→200; `$disconnect`→idempotent `DeleteItem(connectionId)`; subscribe (via `$default`, action=`subscribe`)→ **NATIVE-PARITY acceptance** of the `qry r=/mbx` (reuse `_detect_mbx_query`, `mailbox_handler.py:369`) + the same gate keripy applies (`q["i"]`-or-`q["pre"]` recipient AID must be in `_hby.kevers`), then `PutItem {connectionId, pre, topics, connectedAt, expireAt}`; non-/mbx or unknown-AID qry → register nothing + error frame. **NO signature verification, NO signer↔owner binding** (see DECISION REVISION below).

> **DECISION REVISION (2026-06-30): native parity, NOT a bespoke gate.** The original step 2 ("verify the embedded signed qry; if unverifiable, do not register") was DROPPED. keripy's mailbox does NOT verify the qry signature (`parsing.py:1463` ToDo; `Kevery.processQuery` placeholder) — acceptance is structural + `q["i"] in kevers`. BE KERI NATIVE ⇒ the WS subscribe applies that SAME check and nothing more. This DELETES the hand-rolled `_verify_qry_sig` CESR walk entirely (resolves the prior Critical signer-binding gap AND the BE-KERI-NATIVE finding in one move). Subscribe does NOT `psr.parse` the qry (no Habery state mutation on subscribe — it only needs to peek + check `pre in kevers` + register). Abuse/compute = WAF fast-follow. Stronger per-AID privacy, if ever needed, = a separate explicit KERI-native mechanism (authorized end-role / sealed payloads), not this gate. See spec §5.3 DECISION REVISION.

- [ ] **Step 1 (test):** subscribe with a valid `qry r=/mbx` for a KNOWN AID → a registry row keyed by `connectionId` with `pre`/`topics`/TTL; a qry for an UNKNOWN AID (`pre not in kevers`) → no row + error; a qry for a known AID signed by a DIFFERENT key → **ACCEPTED** (row written — locks in native parity / no signer binding). `$disconnect` → row deleted, idempotent. Use `moto` + a temp Habery (`tests/handlers/conftest.py` + `test_mailbox_handler.py` pattern). RED.
- [ ] **Step 2 (impl):** native-parity per the revised §5.3: peek `_detect_mbx_query` → `pre = q.get("i") or q.get("pre")` → require `pre in _hby.kevers` (`mailbox_handler.init()` for the Habery) → `PutItem`. No `_verify_qry_sig`, no `psr.parse`-on-subscribe. GREEN.
- [ ] **Step 3:** commit.

## Task 3: Handler — one-shot drain replaces the held-open long-poll

**Files:** Modify `keri_cdk/handlers/mailbox/mailbox_handler.py` (`RootResource._ingest` `:532`; the `qry r=/mbx` branch `:571-574`).
**Interfaces:** the deposit path (`/fwd`→204) is UNCHANGED. The `qry r=/mbx` path stops attaching `_stream_mbx_response` (`:386`, held-open) and instead drains once via `_format_sse_events(hby, pre, topics)` (`:338`, already exists) and returns/closes — SSE-framed, terminated-after-drain (§9.1). For large drains, keep LWA response streaming but operate it **drain-only** (§9.2).

- [ ] **Step 1 (test):** a `qry r=/mbx` with N queued messages → the response contains the N events past the cursor and the stream **completes/EOFs** (no 780s hold, no `:keepalive` frames); empty backlog → empty drain + close. Replace the old "stream stays open" assertion (`test_mbx_query_returns_streaming_response` per WS spec §11) with "drain then EOF". RED (current code holds the connection).
- [ ] **Step 2 (impl):** per **WS spec §5.4** — wire `_format_sse_events` as the response body and close; if streaming-drain, refactor `_stream_mbx_response` into a drain-only generator (no soft-cap, no keepalive, no ~1s re-poll). GREEN.
- [ ] **Step 3:** commit. (The 780s cap / keepalive / re-poll become dead code — removed in Task 8 cutover, not here, so legacy clients still drain during migration.)

## Task 4: Handler — nudge fan-out on deposit (inline notifier, MVP)

**Files:** Modify `mailbox_handler.py` `RootResource._ingest` (`:532`); add `_detect_fwd(ims)` (mirror `_detect_mbx_query`).
**Interfaces — Consumes:** `conn_table` GSI `byPre`, `WS_CALLBACK_URL`. **Produces:** after a `/fwd` is stored, fire a nudge to live connections; deposit still returns 204 promptly.

- [ ] **Step 1 (test):** a live registered connection for `Ebob` + a `/fwd` for `Ebob/credential` → the client receives `{"type":"mailbox.nudge","pre":"Ebob","topic":"/credential","cursor":N}` AND the deposit returns 204 (nudge never blocks/fails it); a closed connection → `GoneException` caught + row deleted. Use `moto` + a stubbed `apigatewaymanagementapi` (boto stub) asserting `post_to_connection`. RED.
- [ ] **Step 2 (impl):** per **WS spec §5.5** — `_detect_fwd` extracts recipient `pre`+`topic` from the `/fwd` exn modifiers (see `probe.py:103-122`); `Query` GSI `byPre`; `PostToConnection` via `boto3.client("apigatewaymanagementapi", endpoint_url=WS_CALLBACK_URL)`; `GoneException`→`DeleteItem`; wrap fire-and-forget in try/except so it never delays the 204. `cursor` advisory (omit if surfacing `on` is awkward — `storeMsg` returns a bool). GREEN.
- [ ] **Step 3:** commit.

## Task 5: Discovery publish + onboarding (the `wss` server side + GET / + headers)

**Files:** Modify `mailbox_handler.py` (`RootResource.on_get` `:517`); the stack/handler init that builds the mailbox AID's endpoint records.
**Interfaces — Produces:** (a) the mailbox AID advertises a signed **`wss` loc scheme** `rpy` (URL = `ws_stage.url`, `wss://…/prod`) alongside its `https` loc, served at its OOBI — so a client's `hab.fetchUrl(eid, scheme=Schemes.wss)` returns it (the Phase-2 reader + the unified §4.2 server-publish side). (b) `GET /` status JSON gains `"ws": "wss://…/prod"`, `"mode": "notify-and-fetch"`, and `"client": "<package URL>"`. (c) the one-shot fetch response carries headers `X-Mailbox-Mode: notify-and-fetch` + `X-Mailbox-Client: https://github.com/usuranceai/keri-serverless-mailbox` (onboarding for non-cooperating stock clients).

- [ ] **Step 1 (test):** resolving the mailbox AID's OOBI yields a `wss` loc in `db.locs` such that `fetchUrl(eid, scheme=Schemes.wss)` returns the stage URL; `GET /` JSON has `mode`/`ws`/`client`; the fetch response has the two onboarding headers. RED.
- [ ] **Step 2 (impl):** generate the `wss` loc `rpy` (controller-signed) at stack/handler init; add the `GET /` fields (per WS spec §5.7) + the response headers (unified §7.2 delta). GREEN.
- [ ] **Step 3:** commit.

## Task 6: Package — fill in `ServerlessStrategy` (WS notify-and-fetch client)

**Files:** Create `src/keri_serverless_mailbox/serverless.py`; Modify `strategy.py` (`ServerlessStrategy.run` delegates to it), `pyproject.toml` (+`websockets`), Test `tests/test_serverless_strategy.py`. Repo: `~/code/keri-serverless-mailbox` (`main`).
**Interfaces — Consumes:** `scheduler` (the host DoDoer, Phase-2 contract), `CursorStore`, `on_message`; the mailbox's `wss` URL via `hab.fetchUrl(eid, scheme=Schemes.wss)`. **Produces:** `ServerlessStrategy.run(*, hab, eid, topics, on_message, cursor_store, retry_ms, scheduler)` that: discovers the `wss` URL; opens one idle WS; sends a signed **subscribe** envelope `{"action":"subscribe","qry":"<hab.query r=mbx qb64>"}` (build the `qry` exactly as `StandardStrategy`/`run_standard` does); on a `mailbox.nudge` frame → does a **one-shot signed-`qry` fetch** over HTTPS (reuse the `run_standard` fetch+parse-deliver+cursor path, drain-and-close) → `on_message(topic, raw)` + `cursor_store.set`; sends WS **ping** more often than the 10-min idle timeout; reconnects with exponential backoff (re-subscribe with current cursors) on close (10-min idle / 2-hr cap / drop); runs an **infrequent safety-net fetch**.

- [ ] **Step 1 (test):** with a FAKE WS (async iterator feeding a `mailbox.nudge` frame) + a fake one-shot-fetch (monkeypatched), assert: subscribe envelope is sent with a signed `qry`; a nudge triggers exactly one fetch for that topic past the cursor; delivered messages reach `on_message` as raw bytes + cursor advances; a close triggers a reconnect+re-subscribe; the safety-net fires on its cadence. NO real network (use `websockets`' test utilities or a fake). RED.
- [ ] **Step 2 (impl):** implement `serverless.py`; choose `websockets` async client bridged to the host loop (the `MailboxClientDoer` runs under hio — provide an asyncio bridge or run the WS client in a thread/loop the doer drives; mirror how Locksmith bridges hio↔asyncio via `qasync` if needed — keep the package host-agnostic: expose the WS loop so the host integrates it). Reuse the fetch/parse/cursor logic from `standard.py` (extract a shared `_drain_fetch` helper if cleaner — DRY). GREEN; run the FULL package suite.
- [ ] **Step 3:** commit + push the package (`origin` = `usuranceai/keri-serverless-mailbox`); bump version to `0.2.0`.

## Task 7: Conformance probe — serverless-only

**Files:** Rework `keri_cdk/probes/mailbox_conformance/probe.py` (+ README).
- [ ] **Step 1–3:** per **WS spec §11**: (a) connect WS + signed subscribe; (b) deposit `/fwd` over REST (reuse `_make_fwd_message`, `probe.py:103-122`); (c) assert a nudge frame arrives; (d) assert the one-shot fetch returns the backlog and closes (replace the old "stream stays open" assertion). Run against a local moto/dev stack or a deployed dev stage (NOT live federation without confirmation). Commit.

## Task 8: Cutover / migration + remove the long-poll

**Files:** `mailbox_handler.py` (remove `_stream_mbx_response` hold / 780s cap / keepalive once nothing depends on it); deploy ordering.
- [ ] Per **WS spec §8**: confirm the package client (Tasks 6) + the one-shot fetch (Task 3) are shipped; **additive deploy** (WS API + registry + nudge + drain) is already live (Tasks 1–5) so updated clients move over while the old path still drains; then **remove** the held-open long-poll machinery. Roll all 5 `Mailbox{slug}` federation stacks consistently. **Each AWS deploy requires explicit user confirmation** (live federation). Commit the long-poll removal.

## Acceptance (Phase 3 = the gate Phase 1 deferred)

- **Synth/unit:** Tasks 1–6 tests green (CDK synth incl. WS API/registry/IAM; WS handlers via moto; one-shot drain EOFs; nudge fan-out + 204; `wss`/GET-/+headers; `ServerlessStrategy` nudge→fetch with fakes). Package suite green (`websockets` added).
- **Conformance (Task 7):** connect→subscribe→deposit→nudge→one-shot-drain passes against a dev stage.
- **LIVE FEDERATION e2e (the headline):** rerun the witnessed roundtrip against the deployed federation — the carrier mails → the mailbox nudges → the vault's `MailboxClient` (now selecting `ServerlessStrategy` because the mailbox advertises `wss`) does the one-shot fetch → a `carrier_license` is **retrieved + issued**. This is the federation-retrieval acceptance Phase 1 proved was blocked on the held-SSE; gated on a live deploy (user-confirmed).
- **Idle cost:** an open idle connection with no mail attributes ~0 Lambda invocations.

## Self-Review

- **Spec coverage:** WS spec §5.1/§5.2/§5.6→Task 1; §5.3→Task 2; §5.4→Task 3; §5.5→Task 4; §5.7 + unified §4.2/§7.2→Task 5; §7→Task 6; §11→Task 7; §8→Task 8. §9 decisions baked in Global Constraints; WAF = documented fast-follow.
- **Placeholder scan:** infra code is cited to the WS spec by `file:line` (the design doc holds it — not a TODO); the only net-new code (ServerlessStrategy, the synth/handler tests) is specified by interface + acceptance per task.
- **Type/interface consistency:** `ServerlessStrategy.run` uses the Phase-2 `scheduler` contract; the fetch reuses `run_standard`'s parse/cursor path; `wss` discovery uses the Phase-2 `fetchUrl(scheme=Schemes.wss)` reader.
