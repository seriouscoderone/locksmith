# Mailbox KEL-Registration Fix — Design

**Date:** 2026-07-01
**Status:** Approved design (brainstorming → this spec → implementation plan)
**Spans:** keripy fork (`~/code/keripy`, server) + Locksmith (`~/code/locksmith`, client)

## Problem

A Locksmith wallet AID that designates the serverless federation mailbox
(`mailbox.keri.host`) as its mailbox end-role **cannot collect its mail**: the
notify-and-fetch **subscribe gate rejects it** because the mailbox answers
"unknown aid." Verified live 2026-07-01 against a witness-less Carrier AID
(`EFG_tHGuv-2TvERl85GEpSfeW1autV8FzMzl9hD6DWpk`): `GET /oobi/<carrier>` → 404
across 12+ requests, and the subscribe gate (`ws_handlers.py:146`,
`if pre not in hby.kevers`) would reject identically. This blocks Stage-1 live
mailbox retrieval in the real wallet.

Two independent root causes, both consequences of a deliberate architectural
choice — **this federation splits the mailbox into its own AID, distinct from
the witnesses** (classic KERI co-locates them):

1. **Client gap.** In classic KERI your mailbox *is* one of your witnesses, so
   your KEL arrives at the mailbox for free as a side effect of being witnessed
   at inception. Once mailbox ≠ witness, that free registration disappears. The
   wallet's mailbox-designation flow (`SetRoleDoer`) never publishes the AID's
   KEL to the standalone mailbox. It *does* forward the KEL via
   `forwarding.StreamPoster(topic="reply")`, but that stores it as **mail
   addressed to the mailbox AID**, not as a KEL ingested into the mailbox's
   key-state. So the mailbox never learns the AID.

2. **Server gap (stale in-memory `kevers`).** The mailbox is serverless (AWS
   Lambda). keripy was built for a long-running process: it loads every known
   key-state from the DB into an in-memory `kevers` dict **once at startup**,
   then every `pre in kevers` check reads that dict, not the DB. A Lambda
   container loads `kevers` at cold-start and then serves requests for minutes
   with a **frozen** view while other containers write new AIDs to the shared
   DB. So even key-state that *is* in shared DynamoDB reads as "unknown" from a
   warm container. This affects **all** serverless KERI services (witnesses
   too), not just mailboxes.

The federation already pools **public key-state** into one shared DynamoDB
namespace (`SHARED_KEL_STORES = kels., stts., ksns., knas.` + reachability
`ends., locs., eans.`; `src/keri/app/lambding.py`) — the "KEL oracle." So at the
**data layer** sharing is already automatic; the bug is that the serving layer
never re-consults it after cold-start.

### Vocabulary (for reviewers new to KERI)
- **`pre`** — prefix, i.e. the AID identifier string; the primary key for an identity.
- **KEL** — Key Event Log: the append-only raw event history of one AID.
- **Kever** — in-memory object holding an AID's *current verified key-state*
  (current keys, sequence number, witnesses, thresholds); the processed result
  of a KEL.
- **`kevers`** — a dict `{pre → Kever}`: the AIDs a node currently knows.

## Goals

- A wallet AID that designates the federation mailbox can subscribe and retrieve
  its mail (Stage-1 unblocked), **with no assumption about whether the AID is
  witnessed**.
- The mailbox (and other serverless KERI services) resolve any AID whose public
  key-state is in the shared oracle, regardless of which Lambda container serves
  the request.
- The mailbox learns a witness-less AID's key-state when that AID designates it.

## Non-Goals

- No change to the write / first-seen / duplicity-detection path (see the
  critical constraint below). We do **not** make `kevers` a blanket read-through.
- No change to receipting/witnessing — the mailbox remains pure store-and-forward
  (non-transferable, no witnesses). "Registering with the mailbox" is a one-way
  "here is my public key-state," **not** a witness round-trip.
- No new shared store; `stts.`/`kels.` are already pooled. `evts.` stays
  per-stack (correct — see MissingEntryError handling).
- Package `keri-serverless-mailbox` is untouched.

## Global Constraints

- **BE KERI NATIVE.** Rebuilding a Kever from a stored key-state record is
  exactly how keripy boots (`Baser.reload`, `basing.py:97`); publishing a KEL to
  a mailbox is a standard `POST` of `hab.replay()`. Both are KERI-faithful.
- **Preserve write-path semantics.** `pre not in hby.kevers` MUST keep meaning
  "not locally first-seen" on the ingest/duplicity path. The lazy-load is added
  ONLY at read/serving checks (subscribe gate, `/oobi`, mbx-query gate).
- **keripy pushes to the fork (`seriouscoderone/keripy`) ONLY**, never
  WebOfTrust/origin.
- **Live 5-stack federation deploy is gated on explicit user approval.**
- **Locksmith tests run with `--import-mode=importlib`** (the `packaging/`
  shadow), against the main-checkout `.venv`.
- The canonical keripy edit is **`src/keri/app/lambding.py`**; `build_layer.sh`
  (`pip install .`) rebuilds the Lambda layer from it before any deploy.

## Part 2 — Server: `ensure_kever` lazy-load (keripy fork)

A single reusable helper in `src/keri/app/lambding.py` (imported by BOTH the
witness and mailbox handlers, so every serverless KERI service benefits):

```python
def ensure_kever(hby, pre):
    """Return the Kever for `pre`, consulting the SHARED key-state store on an
    in-memory miss.

    Serverless containers load `hby.kevers` once at cold start and never refresh;
    the shared oracle (db.states / stts.) may hold a peer's key-state written by
    ANY federation service. This is the READ/serving path only — call it where a
    stale in-memory "unknown" would wrongly reject a request.

    NEVER call this on the write / first-seen / duplicity path: there,
    `pre not in hby.kevers` must keep meaning "not locally first-seen."

    Returns the Kever, or None if `pre` is unknown to the whole federation.
    """
    if pre in hby.kevers:
        return hby.kevers[pre]
    ksr = hby.db.states.get(keys=(pre,))         # shared key-state record (KeyStateRecord)
    if ksr is None:
        return None                              # genuinely unknown to the federation
    from keri.core.eventing import Kever
    from keri.kering import MissingEntryError
    try:
        kever = Kever(state=ksr, db=hby.db, local=False)   # peer AID; mirrors Baser.reload
    except MissingEntryError:
        return None            # key-state present but this stack lacks the KEL events
    hby.kevers[pre] = kever    # cache for this container's lifetime
    return kever
```

Notes:
- `local=False` because the resolved AID is a peer, not one of the node's own
  habs (`Baser.reload` uses `local=True` for own habs).
- `MissingEntryError` guard mirrors `Baser.reload` (which drops a hab whose
  key-state has no backing KEL event). `evts.` is per-stack, not shared, so a
  DIFFERENT federation stack may hold the state but not the events → return None
  gracefully. For the primary flow (a wallet publishes to the mailbox it
  designated; subscribe/read then hits that SAME stack), the events are in that
  stack's namespace, so reconstruction succeeds.
- Writing `hby.kevers[pre] = kever` mutates the same mapping `Baser.reload`
  populates, so the caller's later `pre in kevers` checks hit the cache.

### Call sites (replace bare `pre in _hby.kevers` reads)
1. **WS subscribe gate** — `keri_cdk/handlers/mailbox/ws_handlers.py:146`
   (`if pre not in hby.kevers:` in `default(event, context)`). THE critical site
   for notify-and-fetch; that Lambda has its own `_hby`. Becomes
   `if ensure_kever(hby, pre) is None:`.
2. **`/oobi` lookup** — `keri_cdk/handlers/mailbox/mailbox_handler.py:541`
   (`if aid not in _hby.kevers:`). Becomes `if ensure_kever(_hby, aid) is None:`.
3. **HTTP mbx-query gate** — `mailbox_handler.py` `_ingest` (the `q["i"]`/`pre`
   validation before serving `_stream_mbx_response`). Same substitution for the
   query's recipient `pre`.

Deposit sender-verify is out of scope: the `/fwd` deposit is verified against
the **sender**, and depositing does not require the recipient in `kevers`; only
the recipient's own subscribe/read does.

## Part 1 — Client: publish KEL on designation (Locksmith)

In `SetRoleDoer.set_role_do` (`src/locksmith/core/remoting.py`), after the
end-role is written and confirmed, when `role == Roles.mailbox`, publish the
designating hab's full KEL to the mailbox's receive endpoint:

```python
# after loadEndRole succeeds, mailbox role only:
if self.role == Roles.mailbox:
    url = hab.fetchUrl(self.remote_id_pre, scheme=Schemes.https) \
          or hab.fetchUrl(self.remote_id_pre, scheme=Schemes.http)
    if url:
        kel = bytes(hab.replay())                 # full KEL from fn=0 (robust to rotations)
        requests.post(url.rstrip("/") + "/", data=kel,
                      headers={"Content-Type": "application/cesr"}, timeout=30)
```

- The mailbox's `_ingest` first-sees the KEL → writes key-state to the **shared**
  namespace → the whole federation can now resolve the AID; combined with Part 2
  it is served regardless of container.
- **Idempotent:** re-publishing an already-known KEL is a no-op at the mailbox.
- **Mailbox-role only:** other roles (gateway/watcher/witness/controller) keep
  today's behavior; the existing `StreamPoster(topic="reply")` KEL-forward is
  left in place (it may be load-bearing for those flows) — this ADDS a publish,
  it does not replace.
- `requests` is already a Locksmith dependency; `Schemes` from `keri.kering`.
- Network failure is non-fatal to role-setting: log and continue (the end-role
  is already written; Part 2 + a future re-publish can recover). Do not fail the
  designation on a mailbox that is temporarily unreachable.

## Data flow (end to end)

Witness-less AID (the hard case, no assumptions):
1. Wallet: OOBI-resolve the mailbox → designate mailbox end-role (`SetRoleDoer`).
2. Wallet (Part 1): `POST hab.replay()` → mailbox `/`.
3. Mailbox `_ingest`: first-see KEL → key-state written to shared `stts.`.
4. Wallet reopens vault → `seed_kel_mailboxes` → poller mounts → ServerlessStrategy
   subscribes over wss.
5. Mailbox WS subscribe gate (Part 2): `ensure_kever` finds the shared key-state
   even on a warm/other container → **accepts**.
6. Deposit `/fwd` → nudge → wallet one-shot fetch → mail delivered.

Witnessed AID: step 2–3 are unnecessary (a federation witness already wrote the
shared key-state at inception); Part 2 alone accepts the subscribe. Part 1 still
runs harmlessly (idempotent).

## Testing

**Server unit (keripy):**
- `ensure_kever`: (a) `pre` in `kevers` → returns cached, no DB read; (b) `pre`
  absent from `kevers` but present in `db.states` → rebuilds, caches, returns
  Kever; (c) absent everywhere → None; (d) state present but events missing →
  `MissingEntryError` caught → None.
- Handler: WS subscribe **accepts** an AID present in `db.states` but absent from
  the in-memory `kevers` (the exact regression); `/oobi` serves it likewise.

**Client unit (Locksmith, `--import-mode=importlib`):**
- `SetRoleDoer` with `role == mailbox` POSTs `hab.replay()` bytes to the resolved
  mailbox URL (mock HTTP; assert endpoint + body).
- Non-mailbox role → no POST.
- Unreachable mailbox URL → role still set, error logged, doer completes.

**E2E (live, deploy-gated):** deploy the keripy server change to the 5 Mailbox
stacks (user OK), relaunch the dev-build wallet, designate the mailbox on the
Carrier, run the `fullloop_hio.py`-pattern `/fwd` deposit, observe retrieval in
the wallet log.

## Repos / branches / deploy gating

- **keripy fork:** new branch off `development`, e.g. `feat/mailbox-kel-lazyload`
  (`src/keri/app/lambding.py` + `keri_cdk/handlers/mailbox/{ws_handlers,mailbox_handler}.py`
  + tests). Push to fork only. Rebuild the layer (`build_layer.sh`) before deploy.
  Live 5-stack deploy gated on explicit user approval.
- **Locksmith:** new branch off `development` (`src/locksmith/core/remoting.py`
  + tests).
- Deploy by stack NAME (never `--all`; witnesses untouched), `AWS_PROFILE=personal`,
  `npx aws-cdk@latest`, `--app "$venv/bin/python app.py"`.

## Risks

- **Cross-stack state-without-events** → `MissingEntryError` → the peer reads as
  "unknown" on a stack that never saw its events. Mitigated for the primary flow
  (publish + read hit the same designated stack). A future enhancement could
  pool a compact event needed for `Kever(state=...)`, but that is out of scope
  and unnecessary for single-mailbox designation.
- **`Kever(state=..., local=False)` kwargs** — confirm exact constructor args
  against the installed keripy during the plan (the reconstruction shape is
  fixed by `Baser.reload`; the `local` flag value is the only judgment call).
- **Duplicity safety** — guaranteed by scoping `ensure_kever` to read/serving
  sites only; the ingest/first-seen path is untouched.
