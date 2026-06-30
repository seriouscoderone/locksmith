# Unified Mailbox Architecture — De-leak + Universal Client + KERI-native Serverless Delivery

> **Status:** Design approved (brainstorming, 2026-06-30). Not yet planned or built.
> **Supersedes nothing; reconciles with** the approved WebSocket infra spec
> `docs/superpowers/specs/2026-06-29-mailbox-websocket-notify-and-fetch.md` (the "WS spec").
> This document is the **top-level** design; it owns the client architecture, the
> de-leak, and KERI-native capability discovery, and **cites the WS spec** for the
> Phase-3 server infra detail (with the deltas listed in §7).
> **Spans three+ repos:** keripy fork (`~/code/keripy`), Locksmith (`~/code/locksmith`),
> concierge-api (`~/code/concierge-api`), and a **new standalone package** (§5).

**Goal:** Make "mailbox" a single, KERI-native, transport-agnostic abstraction across
the codebase, with a universal client that talks to any mailbox (held-SSE *or*
serverless WebSocket notify-and-fetch) by discovering the mailbox's capability from
its KEL — fixing today's federation retrieval failure and enabling the serverless
cost model.

**Architecture:** One client interface; two seams underneath — **resolve target**
(which AID hosts the mailbox: `agenting.mailbox`, role-first/witness-fallback) and
**select strategy** (how to talk to it: Standard SSE vs Serverless WS), chosen by a
KEL-advertised `wss` loc scheme. The serverless server delivers a notification-only
nudge over WebSocket plus a one-shot HTTP fetch of the CESR payload.

**Tech stack:** Python 3.14; keripy (KERI/CESR primitives, `hio` async); AWS API
Gateway WebSocket + Lambda (LWA) + DynamoDB (`keri_cdk`); PySide6/`qasync` (Locksmith
host loop). The new client package builds **only** on stock keripy primitives
(`agenting.mailbox`, `hab.query`, `hab.fetchUrl`, `psr.parse`) so only *transport*
diverges from stock keripy, never the crypto/event layer.

## Global Constraints

- **BE KERI NATIVE (prime law).** Mailbox **discovery** is a KERI-core concern → it MUST
  ride the KEL/OOBI, not an HTTP side-channel. Capability is advertised as a signed
  `wss` loc scheme on the mailbox AID; the client learns it via `hab.fetchUrl(eid,
  scheme=wss)`. "Mailbox" is a KERI **end-role** primitive; witness-as-mailbox is the
  *fallback implementation*, never the concept.
- **One mailbox abstraction throughout.** Every poll/deposit target-selection site uses
  `agenting.mailbox(hab, cid)` (role-first, witness-fallback). No site enumerates
  `kever.wits` as if witnesses *are* mailboxes.
- **Serverless-only server, universal client.** The keri.host federation mailbox serves
  **only** notify-and-fetch (per the WS spec §1); the *client* still speaks Standard SSE
  to non-serverless mailboxes (peers, demo, stock keripy). The client is strictly more
  general than any one server.
- **Phased + independently verifiable.** Phase 1 ships and is verified **live against the
  real federation** before Phase 2 begins.
- **Push rules.** keripy → push to `fork` ONLY (never `origin`/WebOfTrust). Locksmith →
  `origin` = seriouscoderone. New package → its own repo. Nothing pushed without explicit
  user request. Locksmith pytest requires `--import-mode=importlib`.
- **Reuse stock keripy.** Use `agenting.mailbox`, `hab.fetchUrl`, `hab.query`, `psr.parse`
  as-is. The only keripy change is teaching it the `wss` loc scheme (§4.2).

---

## 1. Problem (verified this session)

A carrier's `grant_license` exn mailed to a witnessed DOI on the live federation is
**never retrieved** by the hosting vault (`pollers=5`, pulled 0). Root cause, traced in
code:

- **Three divergent mailbox-target models exist:**
  1. **keripy canonical** — `agenting.mailbox(hab, cid)` (`agenting.py:967`): returns the
     AID's **mailbox end-role** EID if designated, else a **witness** (`random.choice(
     kever.wits)`), else `None`. The correct universal resolver.
  2. **concierge (leak)** — `BindingController._ensure_mailbox_polled` (`binding.py:135`)
     iterates `hab.kever.wits` and adds a poller per **witness**, ignoring the mailbox
     end-role.
  3. **wallet** — `Vault.activate_mailbox` (`vaulting.py:240`) polls an explicit `db.mbx`
     registry of designated EIDs; `load_active_mailboxes` (`:233`) seeds pollers from it.
     Closer to correct, but nothing auto-seeds the registry from the KEL, so a fresh
     federation AID polls nothing.
- **The federation separates witnesses and mailboxes into distinct AIDs**
  (`keripy/ecosystems/keri_host/federation_aids.json`: 5 `witness.*` + 5 `mailbox.*`).
  Witnesses do **not** serve `/mbx`. The carrier deposited at the DOI's designated mailbox
  (`mailbox.keri.host`); the vault polled the 5 witnesses → 0.
- **Independently:** the current serverless mailbox serves a **held-open SSE long-poll**
  (`mailbox_stack.py:227` `ResponseTransferMode.STREAM`; `mailbox_handler.py:571-574`
  `_stream_mbx_response`, 780s cap), i.e. an always-billed Lambda per subscriber — the
  cost problem the WS spec targets. (`kli mailbox debug` against the mailbox hung the full
  watchdog window, re-confirming the held connection.)

So there are two distinct fixes: a **client-side target de-leak** (axis 1, makes
retrieval work on current infra) and a **server-side delivery redesign** (axis 2, the
cost win). This spec unifies both behind one client interface.

## 2. Decisions (from brainstorming)

1. **Phasing:** de-leak first → universal client package → serverless WS infra. Phase 1
   gets the federation **working**; Phase 3 makes it **cheap**.
2. **Discovery: KERI-native, KEL-advertised.** A `wss` loc scheme on the mailbox AID *is*
   the notify-and-fetch capability. No HTTP `GET /` discovery side-channel.
3. **Client: standalone package from day one.** A reusable, pip-installable
   `keri-serverless-mailbox` package (import `keri_serverless_mailbox`); Locksmith is its first
   consumer and depends on it.
4. **WAF rate-limiting: fast-follow, not MVP.** Removing the held-open long-poll already
   neutralizes the expensive failure mode; rate-limiting is added if abuse appears.

## 3. Architecture (the layered model)

```
Host app (Locksmith vault, a Service-AID, any KERI client)
   │ depends on ▼
┌─ keri-serverless-mailbox  (NEW standalone package) ──────────────────────────┐
│  MailboxClient                                                          │
│    public API: start(hab, cid, topics, on_message, cursor_store);       │
│                stop(); state. Loop-agnostic core + a hio adapter.       │
│      │                                                                  │
│      ├─ 1. RESOLVE TARGET   eid = agenting.mailbox(hab, cid)            │
│      │       (role-first, witness-fallback — the one resolver)         │
│      ├─ 2. DISCOVER          url = hab.fetchUrl(eid, scheme=wss)        │
│      │       url present → Serverless ; None → Standard                 │
│      └─ 3. RUN STRATEGY (swappable; host never sees which)             │
│             • StandardStrategy   → signed hab.query r=mbx over SSE/poll │
│             • ServerlessStrategy → WS subscribe → nudge → 1-shot fetch  │
│           both → psr.parse(CESR) → on_message(msg) → cursor_store.set   │
└─────────────────────────────────────────────────────────────────────────┘
        ▲ resolves via OOBI/KEL ; talks https + wss
┌─ keripy keri_cdk  (server, fork) ───────────────────────────────────────┐
│  MailboxStack: publishes a signed `wss` loc-scheme rpy (NEW) + the WS    │
│  API/registry/nudge/one-shot-drain (WS spec) + onboarding headers       │
└─────────────────────────────────────────────────────────────────────────┘
```

**Two seams, one interface.** "Which AID" (resolve) and "how to reach it" (strategy) are
independent; the host only ever holds a `MailboxClient`. Capability is **self-describing
in the KEL**.

## 4. Components

### 4.1 De-leak: one resolver everywhere (Phase 1)

There is **no new abstraction** — use keripy's existing `agenting.mailbox(hab, cid)` at
every target-selection site:

- **concierge** `binding.py:_ensure_mailbox_polled`: replace the `for eid in
  hab.kever.wits` loop with:
  ```python
  eid = agenting.mailbox(hab, hab.pre)
  if eid is not None:
      try:
          mbx.add_poller(hab, eid, extra_topics=extra)
      except TypeError:                      # host add_poller predates extra_topics
          mbx.add_poller(hab, eid)
  ```
  One poller for the **resolved** mailbox (federation → `mailbox.keri.host`; demo/stock →
  witness-fallback).
- **wallet** `vaulting.py`: on vault-open, for each local hab, **auto-seed `db.mbx`** from
  `agenting.mailbox(hab, hab.pre)` (when it returns an EID and no active listener exists),
  then `activate_mailbox`. So the wallet polls the mailbox each AID designated **in its own
  KEL**. Explicit UI designations (existing `activate_mailbox` callers) remain as
  overrides/additions; `db.mbx` stays the persistent registry.
- **Edge case:** if an AID designates multiple `mailbox` end-roles, MVP uses the first
  allowed (what `agenting.mailbox` returns); polling several designated mailboxes is a
  documented possible enhancement, not built now (YAGNI).

### 4.2 `wss` loc scheme — KERI-native capability discovery (Phase 2 client read; Phase 3 server publish)

- **keripy fork:** add `wss` to `kering.py:375` `Schemes = Schemage(tcp='tcp', http='http',
  https='https', wss='wss')`. The validation (`ending.py:452` `if scheme not in Schemes`)
  and parse/fallback (`habbing.py:1238-1239`) already key off `Schemes`, so they accept and
  preserve `wss` with no further change. `hab.fetchUrl(eid, scheme=Schemes.wss)`
  (`habbing.py:1990`) returns the advertised `wss://` URL or `None`.
- **Client capability check (the discovery primitive):**
  ```python
  ws_url = hab.fetchUrl(eid, scheme=Schemes.wss)
  strategy = ServerlessStrategy(ws_url) if ws_url else StandardStrategy()
  ```
- **Server publish (Phase 3):** `MailboxStack` generates a **controller-signed `wss`
  loc-scheme `rpy`** for its mailbox AID (URL = the WS stage connect URL) alongside its
  existing `https` loc, and serves it at its OOBI so OOBI resolution delivers it into the
  client's `db.locs`. (`ws_stage.url` from the WS spec §5.1 is the URL.)

### 4.3 The `keri-serverless-mailbox` package (Phase 2 core; Phase 3 adds ServerlessStrategy)

Public surface (host-facing), stock-keripy deps only:
- `MailboxClient(hab)` with `start(cid, topics, on_message, cursor_store)` / `stop()` /
  `state`. Internally: resolve (§4.1) → discover (§4.2) → run strategy.
- `CursorStore` **port** (host supplies persistence): `get(eid, topic) -> int|None`,
  `set(eid, topic, idx)`. Locksmith implements it over `db.tops` (`witrec.topics`,
  `indirecting.py:401`); another client implements it however it likes.
- `Strategy` interface: `run(client_ctx) -> async`; two impls:
  - **`StandardStrategy`** — a clean reimplementation of today's SSE/poll using
    `hab.query(pre, src=eid, route="mbx", query={pre, topics})` + `psr.parse`, mirroring
    `indirecting.py:356-403`. For non-serverless mailboxes.
  - **`ServerlessStrategy`** — WS subscribe (signed `qry` in a JSON envelope) → on nudge,
    one-shot signed-`qry` fetch → `psr.parse`; ping keep-alive; reconnect/backoff;
    infrequent safety-net fetch. Implements the WS spec §7 client behavior.
- **Loop integration:** a core that is asyncio-loop-agnostic plus a thin **hio adapter**
  (a `doing.DoDoer`) so Locksmith mounts it under its existing Doist, the way
  `MailboxDirector` runs today.
- **WS client library** (`websockets` vs `aiohttp`): open decision (§9), chosen to match
  the Locksmith/`hio`/`qasync` dependency set.

### 4.4 Locksmith integration (Phase 2)

- Add `keri-serverless-mailbox` as a Locksmith dependency. Replace the forked `Poller`
  poll-loop in `indirecting.py` with the package's `MailboxClient`, mounted under the
  same DoDoer (`vaulting.py:152,206`). Keep the message-handling/escrow plumbing
  (`msgDo`/`escrowDo`) and cursor persistence (`db.tops`) — only the *trigger and
  transport* move into the package.
- `MailboxDirector.add_poller(..., extra_topics=)` (the micro-app command-topic seam,
  `indirecting.py:154`) is preserved through the package's `topics` argument.

### 4.5 Server (keri_cdk, Phase 3)

Implement the WS spec (§5: WS API, connection registry, nudge fan-out, one-shot drain
replacing the long-poll), **plus the deltas in §7 below** (publish `wss` loc; onboarding
headers; drop `GET /` as a *discovery* channel).

## 5. Data flow

**Deposit (unchanged):** sender resolves recipient's mailbox via `agenting.mailbox` →
POST `/fwd` exn (signed CESR) → mailbox `storeMsg` → `204`.

**Standard retrieval (Phase 1–2):** client resolves mailbox EID → no `wss` loc → SSE
`qry r=mbx` → drain/stream events → `psr.parse` → `on_message` → advance cursor.

**Serverless retrieval (Phase 3):** client resolves mailbox EID → `wss` loc present →
open one idle WS, send signed-`qry` **subscribe** → server registers connection → on
deposit, server pushes a tiny **nudge** `{pre, topic, cursor}` → client does a one-shot
signed-`qry` **fetch** over HTTPS → drain-and-close → `psr.parse` → `on_message` → advance
cursor. Idle = ping frames only, ~0 Lambda.

## 6. Phasing, deliverables, acceptance

| Phase | Repos | Deliverable | Acceptance (hard gate) |
|---|---|---|---|
| **1 — De-leak** | concierge, locksmith | Both target-selection sites use `agenting.mailbox`; wallet auto-seeds `db.mbx` from the KEL | **LIVE federation roundtrip retrieves off `mailbox.keri.host`** (re-run the witnessed/in-vault path against the real federation; the carrier's exn is delivered to the vault and a `carrier_license` issues). Demo path still green. |
| **2 — Client package** | new `keri-serverless-mailbox`, locksmith | `MailboxClient` + `StandardStrategy` + `CursorStore` + KEL capability discovery (`wss` read); Locksmith depends on it, retires its forked poll-loop | Package unit tests green standalone; Locksmith retrieves via the package against a standard mailbox (federation Phase-1 result reproduced *through the package*); `--import-mode=importlib`. |
| **3 — Serverless** | keripy (`keri_cdk`), `keri-serverless-mailbox`, locksmith | WS infra (WS spec) + `wss` loc publish + `ServerlessStrategy` + onboarding headers + cutover | WS nudge→one-shot-fetch end-to-end on the federation; idle WS = ~0 Lambda; stock SSE client gets a drain-and-close + onboarding header (not a held stream). |

**WAF rate-limiting** is a documented **fast-follow** after Phase 3 (add an AWS WAF
rate-based rule + 429-with-onboarding-body if treadmill abuse appears).

**Each phase gets its own implementation plan** (writing-plans) and is built + verified
before the next begins. Phase 1's live-federation gate must pass before Phase 2 starts.

## 7. Deltas to the approved WS spec

The WS spec (`2026-06-29-...`) stands for the Phase-3 server infra. This unified design
**overrides** it on three points:

1. **Discovery is KEL-native, not `GET /`.** WS spec §5.7 advertised the `wss://` URL in
   `GET /` status as the discovery channel. **Replace** with a signed `wss` loc-scheme
   `rpy` on the mailbox AID (§4.2). `GET /` survives only as a **human/debug status page**
   and onboarding-pointer surface — explicitly **not** the discovery source of truth.
2. **Onboarding message channel.** Add informational headers to the one-shot fetch
   response (`X-Mailbox-Mode: notify-and-fetch`, `X-Mailbox-Client: <package URL>`) and
   include the same pointers in the `GET /` status body, so a non-cooperating stock client
   is told how to adopt the package. (WS spec §1/§5.4 noted stock clients break but gave
   them no pointer.)
3. **WAF gating is fast-follow** (§2.4 / §6), consistent with WS spec §9.3 ("only if abuse
   appears").

Everything else in the WS spec (WS API shape §5.1, connection registry §5.2, handlers
§5.3, one-shot drain §5.4 reusing `_format_sse_events`, nudge fan-out §5.5, IAM §5.6, cost
model §12, migration §8) is adopted as-is for Phase 3.

## 8. Error handling

- **Resolver returns `None`** (no mailbox role, no witnesses): the client logs and polls
  nothing for that AID — no crash. Concierge/wallet skip seeding.
- **Capability ambiguity:** absence of a `wss` loc deterministically means Standard; a
  malformed/unverified loc `rpy` is ignored by keripy's reply verification, so the client
  falls back to Standard (fail-safe, never serverless-by-accident).
- **Serverless reconnect:** on WS close (10-min idle if pings lapse, 2-hr hard cap, network
  drop) reconnect with exponential backoff and re-subscribe with current cursors; an
  infrequent safety-net fetch catches missed nudges. Drains are idempotent via persisted
  cursors → no message loss/dup.
- **Stale connection (server):** `GoneException` on `PostToConnection` → delete the
  registry row (WS spec §5.5).
- **Nudge is best-effort:** wrapped so it never blocks/fails the `204` deposit (WS spec
  §5.5).

## 9. Open decisions for the planner

1. **WS client library: DECIDED — `websockets`** (lightweight, asyncio-native; bridged to
   Locksmith's `hio`/`qasync` via the hio adapter, §4.3).
2. **Package: DECIDED — `keri-serverless-mailbox`** (import `keri_serverless_mailbox`), its
   own new repo (proposed `~/code/keri-serverless-mailbox`). One consumer today (Locksmith).
3. **Fetch response shape:** SSE-framed-terminated-after-drain (max client-code reuse) vs
   `application/cesr` plain body — inherit WS spec §9.1 recommendation (SSE-framed one-shot).
4. **`wss` loc URL form:** the WS connect URL (`wss://…/prod`) directly, vs a discovery URL
   the client expands. Default: the connect URL directly.
5. **Multiple designated mailboxes:** MVP = first allowed (`agenting.mailbox`); polling all
   designated mailboxes deferred.

## 10. Non-goals (YAGNI)

- No `GET /`-based discovery; no token/$connect authorizer in MVP (signed-`qry` subscribe
  is the auth — WS spec §3/§9.3).
- No pushing full CESR over WebSocket (WS spec §1 — frame cap; fetch carries payload).
- No WAF in MVP (fast-follow).
- No standard-SSE compatibility path **on the federation server** (serverless-only, WS
  spec §1); the *client* keeps Standard SSE only for *other* mailboxes.
- No multi-mailbox redundancy polling in MVP.

## 11. Testing

- **Phase 1:** concierge unit test — `_ensure_mailbox_polled` adds one poller for the
  resolved mailbox role (and witness-fallback when none); wallet unit test — vault-open
  auto-seeds `db.mbx` from `agenting.mailbox`. **Live gate:** the federation witnessed
  roundtrip (`locksmith-micro-app-designer/tests/integration/microapp_in_vault_witnessed.sh`
  with `WITNESS_PROFILE=federation`) **retrieves and issues**.
- **Phase 2:** package unit tests (resolve→discover→strategy selection; Standard SSE
  parse/cursor; `CursorStore` contract) with fakes; Locksmith integration via the package
  against a standard mailbox; `--import-mode=importlib`.
- **Phase 3:** keripy `keri_cdk` synth tests (WS API, registry table PK/GSI/TTL,
  `grant_manage_connections`, `wss` loc publish); conformance probe reworked for
  serverless-only (WS spec §11) — connect WS + signed subscribe; deposit `/fwd`; assert
  nudge; assert one-shot drain returns + closes; package `ServerlessStrategy` unit tests
  (nudge→fetch, reconnect/backoff, safety-net, cursor idempotency).

## 12. File / path map

**concierge-api:** `src/concierge_api_local/binding.py` (`_ensure_mailbox_polled` →
`agenting.mailbox`).
**locksmith:** `src/locksmith/core/vaulting.py` (auto-seed `db.mbx` on vault-open);
`src/locksmith/core/indirecting.py` (retire `Poller` loop → package `MailboxClient`);
`pyproject.toml` (+`keri-serverless-mailbox` dep); `CLAUDE.md` (pytest importlib).
**keri-serverless-mailbox (new):** `MailboxClient`, `Strategy`/`StandardStrategy`/
`ServerlessStrategy`, `CursorStore`, capability discovery, hio adapter; package metadata.
**keripy (fork):** `src/keri/kering.py:375` (+`wss` scheme); `keri_cdk/mailbox_stack.py`
(WS API + `wss` loc publish); `keri_cdk/handlers/mailbox/mailbox_handler.py` (one-shot
drain, nudge, onboarding headers, WS handlers, drop `GET /` discovery role); WS spec §14
for the full keri_cdk map. Reference (don't break): `src/keri/app/agenting.py:967`
(`mailbox`), `src/keri/app/storing.py`, `src/keri/db/dynamodbing.py`, keripy `CLAUDE.md`
(shared-KEL oracle, first-seen gate, witness Receiptor model — untouched).

## 13. References

- WS spec: `docs/superpowers/specs/2026-06-29-mailbox-websocket-notify-and-fetch.md`.
- `~/code/KERI-COMMUNICATION-MODEL.md` — async msg-passing; deposit 204 / fetch; read first.
- keripy `agenting.mailbox` (`agenting.py:967`); `kering.Schemes` (`kering.py:375`);
  `hab.fetchUrl`/`fetchLoc` (`habbing.py:1918/1990`); `ending.py:452`.
- `keripy/ecosystems/keri_host/federation_aids.json` (5×5 witnesses/mailboxes).
- keripy `CLAUDE.md`; Locksmith `CLAUDE.md` (`--import-mode=importlib`, packaging shadow).
