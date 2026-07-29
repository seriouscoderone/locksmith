# Embedded KERI-Native Assistant — Design

**Status:** proposed (design; Phase 0 + Phase 1 in scope, later phases deferred)
**Date:** 2026-07-29
**Branch / worktree:** `embedded-assistant` (`.claude/worktrees/embedded-assistant`, from `development`)
**Deliverable:** a UI-agnostic **assistant library** — the "third universal surface" — plus a Phase-1 deterministic realization wired into Locksmith.

**Goal.** Give the Locksmith wallet (and, by the same library, the concierge CLI) a natural-language
assistant that turns user utterances into **KERI-protocol actions over ACDCs**, gated by a human
confirmation ceremony, without ever letting the language model become an authority.

**Architecture (one paragraph).** The assistant is a **library**, not a Locksmith feature. It owns the
*harness* — match utterance → constrained action grammar → resolve against grounding → preview → **confirm**
→ dispatch → audit. Its action space is the **KERI protocol** (IPEX participation verbs + custom `exn`
routes + `qry` reads) over ACDCs; its *grounding* (what a phrase resolves to — which schema SAID, which
counterparty AID) comes from micro-app templates + EGF + ACDC schemas + the user's vault state. The library
emits an **inert, grammar-constrained intent object**; a trusted, host-provided **`Dispatcher`** (wrapping
keripy) performs the actual protocol work only *after* a human confirms. Locksmith (universal UI) and
concierge (universal CLI) are interchangeable **displays** over this one library.

**Tech stack.** Pure-Python library core (zero heavy deps for the harness; no direct keripy import in the
core — keripy lives behind the host `Dispatcher`). Phase 1 needs no LLM. Later phases add a `llama-server`
sidecar (Phase 2) and push-to-talk voice + the `ai-identicon` presence widget (Phase 3).

---

## Global Constraints (bind every task)

- **BE KERI NATIVE (LAW).** Authorization is *represented by credentials* (ACDC possession, edges,
  key-state, delegation, multisig threshold), **never computed** by the assistant. The assistant may
  compile the *grammar of what verbs exist* (syntactic); it must never decide *whether an actor may act*.
  Source: `~/code/ugard/docs/canon/be-keri-native.md`.
- **The LLM/matcher is never the authority.** "The harness's job is to make the LLM useful without ever
  trusting it to be the authority." The assistant only ever *proposes*; a human **Confirm = a signature**
  authorizes; a trusted executor signs. Never-verbs (`rotate / delegate / revoke / recover / seed / passcode
  display / IPEX admit-into-vault`) are **structurally absent** from the grammar — not even confirmable.
- **Emit ≠ execute.** The library's output is an inert intent object (grammar-constrained JSON). It is not
  CESR, not a signed event, not a key operation. Only the host `Dispatcher` speaks protocol / holds keys.
- **Depend on stock keripy APIs only** (per `CLAUDE.md`). No changes to `keri.__version__`.
- **Library, not a Locksmith module.** The library must not import Locksmith; both Locksmith and concierge
  depend on *it*. (Same extraction pattern as `ai-identicon`.)
- **Deterministic-first, LLM-last; the model is never load-bearing.** The wallet stays fully usable with no
  model installed. Phase 1 ships with no LLM at all.

---

## 1. Context & prior art

This design **builds on**, and does not re-derive, prior work — read these for the rationale that is not
repeated here:

- `~/code/ugard/backlog/2026-07-17-locksmith-embedded-assistant.md` — the backlog item + its 07-18
  (rebecca-poc findings, harness framing) and 07-19 (KERI-native remote control) amendments. **This spec is
  the Phase-0/Phase-1 realization of that item.**
- `~/code/ugard/docs/superpowers/specs/2026-07-17-embedded-assistant-expert-panel.md` — the five-lens panel
  (esp. the KERI-native-security "Smith lens": *"the signature ceremony is the boundary"*).
- `~/code/ugard/docs/canon/keri-communication-model.md` — the async message-passing field guide (§2, §8).
- `~/code/rebecca-poc` — throwaway POC that de-risked the *proposer* half (grammar-constrained local LLM →
  validated command JSON; the grammar held — no never-verb was ever emitted).
- `2026-07-19-keri-native-remote-control-assistant-design.md` (this repo's `keri-remote-assistant` worktree)
  — the phone→desktop signed-control-channel slice; **Confirm = a signature** originates there.

Key finding from grounding this session: **nothing today enumerates micro-app `commands[]` into a discrete
verb surface.** concierge dispatches generically (`call --route --payload`); Locksmith has *no*
template-rendering code. The assistant is the first component to compile a command surface — i.e. this is
the unbuilt `2026-07-13-agent-llm-bridge` work.

---

## 2. Architecture — the third universal surface

Locksmith is the **universal UI**; concierge is the **universal CLI**; the assistant library is the
**third universal surface** (natural language), a peer to both.

```
                 ┌──────────────────────────────────────────────────┐
                 │        assistant library  (UI-agnostic core)      │
   utterance ──▶ │  match → grammar/allow-list → resolve(grounding)  │ ──▶ ResolvedIntent
                 │  → preview → CONFIRM → dispatch → audit           │
                 └───────┬─────────────────┬───────────────┬─────────┘
        consumes ▲       │        host provides             │
   CommandSurface│       ▼                 ▼                ▼
 (from grounding)   Confirmer          Dispatcher        AuditSink
                (renders preview,   (wraps keripy;      (proposed-by /
                 returns yes/no)     performs protocol)  authorized-by log)
```

**The library owns** the harness (match, grammar/allow-list, resolution, preview, confirm-orchestration,
audit shaping). **The host provides** three thin seams:

| Seam | Responsibility | Locksmith impl | concierge impl |
|---|---|---|---|
| `CommandSurface` provider | compile the grounded verb set (see §5) | from active micro-app template(s) + vault state | same, from loaded template |
| `Confirmer` | render the resolved-intent preview; return the human's authorize/reject (the ceremony) | a Qt confirm dialog | a CLI prompt |
| `Dispatcher` | perform the confirmed KERI protocol action (build/sign/send); return result | **in-process keripy doers** (`core/serviceaid_bridge.py`: `GrantDoer/ApplyDoer/AdmitDoer/ServiceaidIssueDoer`) | `hab.exchange(route=…)` / `kli` (fallback only) |
| `AuditSink` | record `proposed-by` (assistant identity) + `authorized-by` (human signature) as distinct facts | vault audit surface / `DoerSignalBridge` | CLI log |

`Dispatcher` is deliberately a per-host interface: Locksmith already dispatches IPEX **in-process** (it does
not need to shell to `kli`; `kli`-as-subprocess is a fallback only, and has known v2 traps — see `CLAUDE.md`
and the publisher's move off `kli --receipt-endpoint`).

**Packaging (decided).** A **standalone pure-Python package in its own repo — a *sibling* to `ai-identicon`,
not part of it** (ai-identicon is generative visual presence; this is KERI-protocol logic — different deps,
audience, and release cadence; bundling them would conflate two libraries). Develop it in-worktree first as
a self-contained, zero-Locksmith-import package, then extract to its own repo at implementation-readiness —
the exact *pattern* ai-identicon used. This keeps the core pure and independently testable, and lets
concierge depend on it without depending on Locksmith. Repo creation + final name are deferred to
implementation (need the owner's go).

---

## 3. The KERI-native communication model (folded in)

The assistant's action model only makes sense against KERI's *actual* communication model, which is **not
request/response** (`keri-communication-model.md` §2).

**Three planes** the assistant operates across:

| Plane | Messages | Meaning |
|---|---|---|
| **Commit** | KEL (`icp/rot/ixn/dip/drt`), TEL (`vcp/iss/rev`) | An AID's *own* authoritative state change, under its own authority |
| **Query / announce** | `qry`/`rpy`, `pro`/`bar` | Read state; answer or (gratuitously) announce state |
| **Exchange** | `xip`/`exn` | Signed peer messages that propose / offer / request / grant / notify / coordinate |

**Async, not request/reply.** Every routed message is independent and individually signed; correlation is by
explicit fields (`ri` = Receiver AID, `rr` = return route, `p` = prior, `x` = transaction), never a socket.
A "reply" is a brand-new signed message routed to the recipient's mailbox. Over HTTP, event POSTs typically
return `204`; the work-product returns via `/receipts` or a mailbox SSE poll.

**`xip` vs `exn` = inception vs continuation** (NOT request vs reply). Field shapes (spec `event-model.md`):

```
xip  [v, t, d, u, i, ri, dt, r, q, a]      ← exchange INCEPTION: opens a transaction; d = transaction id; has nonce u; no x/p
exn  [v, t, d, i, ri, x, p, dt, r, q, a]   ← exchange message: standalone (x,p empty) OR a turn in a transaction (x = xip SAID, p = prior)
```

This is the same inception→continuation pattern as `icp`→`ixn` (KEL) and `vcp`→`iss` (TEL): **an exchange
transaction is just another append-only, hash-chained, signed log — a mini-log of a conversation.**

**`exn` is communication, not RPC.** An `exn` is a signed *speech-act* deposited in a mailbox — no synchronous
return, and the recipient is **sovereign**: it independently *verifies* the sender's authority (credential /
key-state) and decides; it does not "obey." The authoritative mutation is a KEL/TEL event, not the message.

---

## 4. The action model

**Action space = a signed `exn` whose `route` is drawn from the grounded route-set, carrying a grounded,
schema-valid payload** — where the grounded route-set is:

1. **IPEX routes** (built-in credential subset): `apply / offer / agree / grant / admit / spurn` — the
   standardized, bilateral, non-normative-but-canonical credential issuance & presentation handshake.
   *(⚠️ Which of these the assistant may **propose** vs. which are human-only is unresolved: the backlog
   lists **IPEX `admit`** — accepting a credential into the vault — as a **never-verb**. This spec does not
   decide it; see the reconciliation verify-item in §9. Until reconciled, treat `admit` as human-only.)*
2. **Custom micro-app command routes** (`/<eco>/cmd/<verb>_<noun>`) — the framework's declared non-credential
   coordination.
3. **`qry` reads** — for read/lookup intents (and `projections[]` over local state).

IPEX is *one* provider of routes, not the whole vocabulary. Never-verbs (KEL establishment: rotate/delegate/
etc.) are not `exn` routes at all, so they fall outside this action space **by construction** — a structural
bonus for the never-verbs invariant.

**The intent object (inert, grammar-constrained).** The library emits, and the human confirms, a small object
like:

```
ResolvedIntent {
  route:         <grounded route, e.g. "/ipex/grant" or "/insurance/cmd/submit_quote">,
  receiver_aid:  <grounded AID, chosen from the grounding set — never invented>,
  schema_said:   <grounded ACDC schema SAID, when the action concerns a credential>,
  payload:       <schema-valid attributes>,
  transaction:   <xip SAID if continuing a transaction, else open a new one>,
  provenance:    <edge references, when hand-off across a chain — see §6>,
}
```

The **hybrid, grounding-constrained** rule (signed off): the *route*, *schema SAID*, and *receiver AID* can
only be chosen from what the grounding actually exposes — the model/matcher **cannot emit an ungrounded
value**. It "thinks in KERI protocol" (fully general) but cannot hallucinate a schema or recipient.

**Phase 1 ≡ Phase 2 surface.** In Phase 1 the deterministic matcher's grounded actions *are* the active
template's `commands[]` (the highest-confidence grounded subset), emitted as the same `ResolvedIntent`. In
Phase 2 the LLM generalizes to any grounding-constrained protocol action. **The intent object and the
`Dispatcher` are identical across phases — only the matcher changes.**

### 4.1 Seven KERI-native principles (the action model's spine)

1. **Choreography, not orchestration.** No central executor. A micro-app is one role's autonomous
   participation: the commits it may make + messages it sends + how it **reacts** to inbound messages.
2. **A command = (authorized commit events) + (exchange messages) + (awaited reactions).** A command declares
   its `emissions` as *typed KERI operations* (TEL `iss`/`rev`, KEL `ixn` anchor, IPEX `grant`/`apply`, or
   custom `exn`), not an opaque RPC. The trusted `Dispatcher` expands one confirmed intent into that full
   sequence; the assistant proposes only the intent.
3. **A workflow instance IS an exchange transaction (`xip`).** Instance id = `xip` SAID; each step = an `exn`
   chained by `p`, bound by `x`. You get a signed, hash-chained, replayable audit log per instance for free.
4. **Prefer the standardized primitive; reserve custom `exn` for genuine gaps.** Anything that is issuance/
   presentation of a credential MUST be IPEX + ACDC + TEL — never a bespoke `/cmd/` payload (else you reinvent
   IPEX and lose graduated disclosure, the state machine, and interop). Custom `exn` routes are only for
   non-credential coordination. *(Verify-item — see §9.)*
5. **Authority is verified possession, not permission-from-a-server.** A command's `authz` (`open/aid/
   allowlist/credential`) is a *claim about what the actor must hold*, verified independently by each
   recipient. The assistant reads it as data and never re-derives it. (concierge's `bind_authz` is the
   recipient-side fail-closed check.)
6. **"Results" are observed state, not returned values.** `projections[]` (local TEL/KEL replay; `qry`/`rpy`
   for counterparties') are how a role observes evolving shared state. Commands don't return.
7. **Mutable non-KERI data (if any) follows RUN/BADA, not CRUD** — Read/Update/**Nullify** + monotonic
   ordering, signed, replay-safe. (Relevant only if the framework stores non-KEL/TEL/ACDC data.)

---

## 5. Grounding model

Grounding is *what a phrase resolves to* — the soft-knowledge layer that turns "submit the quote" into a
concrete, correctly-parameterized intent. Sources, composed into a **constraint set** the grammar draws from:

- **Active micro-app template(s)** — `commands[]` (route, `payload_schema`, `authz` descriptor, `emissions`),
  `projections[]` (read views), and role/responsibility context.
- **EGF** documents — ecosystem governance framing (who the counterparties/roles are, what schemas are
  canonical).
- **ACDC schemas** — by SAID; the shapes credentials must satisfy.
- **The user's vault state** — which credentials they *hold* (→ which grounded actions are even reachable),
  known counterparty AIDs, registries, transaction history.

The constraint set answers, for a candidate intent: *is this route grounded? is this schema SAID one the
grounding exposes? is this receiver AID a known counterparty? is the payload schema-valid?* Anything not
answered "yes" is not emittable. **RAG mechanics** (retrieval, cite-by-SAID) are a Phase-2 concern and are
deferred to that spec; Phase 1 uses direct lookups over the active template + vault (bounded, no vector DB).

---

## 6. Multi-party & groups (folded in)

**Messaging is point-to-point.** Every `exn`/`xip` carries a single `ri` (Receiver AID). There is **no native
broadcast/multicast**. "Notify N parties" = **fan-out**: N addressed messages, one per recipient mailbox,
each independently signed (and per-recipient disclosure may differ — selective disclosure). The only "gossip"
in the spec is witnesses disseminating receipts among themselves — not a messaging primitive.

**"Group" = a multisig group AID**, not a chat room: an identifier jointly controlled by members with a
signing threshold (keripy `GroupHab`; Locksmith already lists these), coordinated via `/multisig/*` `exn`
routes. Shared *control of an identifier*, not a broadcast channel. A product "chat group" is an app-layer
projection over bilateral message logs sharing a topic id; joint *authority* uses a group AID.

**Multi-party workflows** are a **choreography correlated by a shared transaction id, with authority carried
by an ACDC edge chain**:

- Each hop is bilateral (`i` → `ri`), but all messages share the same `x` (the `xip` transaction id) — the
  "baton passing around" (supply chain, corporate workflow) with a common purpose.
- The transaction is **distributed** — no central log; each participant holds their slice and can prove it;
  the DAG is reconstructed by correlating `x`.
- Authority/provenance hand-off rides **ACDC edges** (`e` → `n` = upstream ACDC SAID, operators/weights), not
  the transaction id: each party issues a new ACDC **edged** to the upstream one, delivered by a bilateral
  IPEX `grant`; chain-link confidentiality (R17) can propagate disclosure terms down the chain.
- So a multi-party workflow uses **both**: `x` = session correlation; **edges = the authority/provenance
  spine**.

*(Verify-item: IPEX is strictly bilateral; arbitrary multi-party transaction topologies over a shared `x` are
the generalized pattern — confirm current keripy support. See §9.)*

---

## 7. Authority & trust invariants

- The assistant **never computes authz** and never holds keys, signs, or serializes an event.
- The assistant's output is **inert** until a human confirms; **Confirm = a signature** happens in the
  trusted `Dispatcher`, never in the model.
- **Never-verbs are absent from the grammar** (structural, not a runtime check).
- **`proposed-by` / `authorized-by`** are recorded as distinct facts on every dispatched action.
- Prompt-injection is treated as the top threat: because the grammar + confirm are the boundary (not the
  model's judgment), schema-valid-but-wrong is the residual risk, mitigated by grounding-constraint +
  human confirm.

---

## 8. Scope — phased

**In scope now (Phase 0 + Phase 1):**

- **Phase 0 (design artifacts):**
  - The `ResolvedIntent` object schema (concrete fields + validation).
  - The `CommandSurface` abstraction + the `MicroAppSurface` provider (template `commands[]`/`projections[]`
    → grounded verb set).
  - The `Dispatcher`, `Confirmer`, `AuditSink` interfaces (host seams).
  - The grounding constraint-set model (Phase-1 direct-lookup form).
- **Phase 1 (deterministic harness, no LLM):**
  - Deterministic matcher: utterance → grounded intent over the active template's `commands[]`
    (phrase/synonym match; disambiguation on tie/low-confidence).
  - Full flow: match → grammar/allow-list check → resolve against grounding → **preview → confirm → dispatch
    → audit**, behind a feature flag, instrumented (enable rate, success rate, latency percentiles).
  - Two host wirings proving surface-agnosticism: **Locksmith** (Qt `Confirmer` + in-process keripy
    `Dispatcher`) and **concierge** (CLI `Confirmer` + `hab.exchange` `Dispatcher`).

**Deferred to their own specs/plans (out of scope here):**

- **Phase 2 — LLM proposer:** `llama-server` sidecar + `AssistantBinding` (`propose(context, schema) →
  structured`; MCP only at the BYO-AI boundary; enforcement-strength negotiation) + RAG grounding
  (cite-by-SAID). The Phase-1 `ResolvedIntent` and `Dispatcher` are designed to accept this unchanged.
- **Phase 3 — voice + presence:** push-to-talk, STT/TTS, the `ai-identicon` widget.

**Confirm ceremony (Phase 1):** given Phase 1 has no consequential verbs yet, the ceremony still renders a
resolved-intent preview for every command (uniform confirm) — this establishes the boundary ritual that
becomes load-bearing in Phase 2. *(This was the pending confirm-ceremony question; defaulting to "uniform" as
it aligns with the security framing; open to revisit.)*

**Future (not Phase 1): a "skip / always-allow" confirm preference.** A user-settable preference to suppress
the confirm step for a given command. **KERI-native guardrail:** it may apply **only to zero-consequence
actions** (reads / navigation / `qry`), and **never** to any authority-bearing action (any commit or
credential-bearing `exn`) — auto-allowing those would gut the `Confirm = a signature` boundary. Scope and
storage of this preference are deferred to the phase that introduces it.

---

## 9. Verify-items & open questions (for the agents in this area)

1. **Principle 4 — template command KERI-nativeness.** Do the current templates' `commands[].emissions`
   resolve to IPEX/ACDC/TEL for anything credential-bearing, or do some carry meaning only in a bespoke `exn`
   payload? (Other agents are working the template area; flagged, not resolved here.)
2. **keripy `xip` transaction support.** How far does stock keripy support multi-party exchange transactions
   over a shared `x` vs. bilateral IPEX only? Governs how literally §6's "workflow = transaction" can be
   implemented (stock-keripy-only per `CLAUDE.md`).
3. **Library packaging (decided) — final name + repo creation.** Standalone pure-Python package, its own
   repo, **sibling to `ai-identicon`** (§2). Only the final package/repo name and the actual repo creation
   remain, deferred to implementation (needs owner's go).
4. **Phase-2 grounding/RAG mechanics.** Retrieval strategy + cite-by-SAID — deferred to the Phase-2 spec.
5. **Never-verb list vs. KERI-protocol action space (reconciliation).** The backlog's never-verb list was
   authored for the earlier *wallet-shell* framing and marks **IPEX `admit`** never-reachable. The new
   KERI-protocol action model (§4) treats IPEX as the action vocabulary, where `admit` is a core verb.
   Decide, per verb, which IPEX participation verbs are assistant-**proposable** (behind Confirm) vs.
   **human-only/absent** — and update the backlog's never-verb list to match. Touches signed-off prior art,
   so it's an explicit decision, not a silent change.

---

## 10. Testing strategy

- **Library core (pure, no host):** unit tests for the matcher, grammar/allow-list construction from a
  fixture template, grounding constraint-set resolution, and `ResolvedIntent` validation. **Never-verb
  invariant test:** assert no never-verb route is constructible from any fixture template.
- **Golden surface tests:** a fixture micro-app template → expected grounded verb set (pins the compilation).
- **Host-seam tests:** a fake `Dispatcher`/`Confirmer`/`AuditSink` verifying the flow (preview→confirm→
  dispatch→audit) and the `proposed-by`/`authorized-by` split, with confirm and **reject** both exercised.
- **Locksmith integration:** the deterministic palette drives real in-process `Dispatcher` doers against a
  test vault (dry-run/preview where a real counterparty is unavailable).
- Run with `--import-mode=importlib` in Locksmith (per `CLAUDE.md`, the `packaging/` shadow trap).

---

## 11. Cross-links

- Backlog item (to receive a pointer amendment): `~/code/ugard/backlog/2026-07-17-locksmith-embedded-assistant.md`
- Panel: `~/code/ugard/docs/superpowers/specs/2026-07-17-embedded-assistant-expert-panel.md`
- Comms model: `~/code/ugard/docs/canon/keri-communication-model.md`
- Be-keri-native LAW: `~/code/ugard/docs/canon/be-keri-native.md`
- Remote-control design: `2026-07-19-keri-native-remote-control-assistant-design.md`
- keri-skills references used for grounding: `spec/references/event-model.md`, `acdc/references/disclosure-ipex.md`, `acdc/references/acdc-structure.md`
