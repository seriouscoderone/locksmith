# keripy `cloneEvtMsg` frames v2 event bodies with v1 attachment codes (breaks OOBI-resolve + peer import on v2)

**Filed:** 2026-07-10 (investigation complete; fix fully specified + proven offline; deferred deliberately — not changing a load-bearing keripy function ad hoc)
**Domain:** keripy fork (`src/keri/db/basing.py`) × KERI-v2 CESR attachment framing
**Severity:** the ONE root cause behind two v2-hold registry rows (`kli oobi resolve` witness-discovery + peer-blob import). Not user-blocking today (the wallet's own AIDs are still v1 — coupled to the upstream ACDC/IPEX hold — so peer mode is v1-to-v1 and existing vaults already have witness discovery). It bites: (a) the **publisher** (v2 AID) — worked around by seeding + by the publisher's own genusified export; (b) any **fresh v2 keystore** resolving a witness/contact OOBI; (c) everything once the wallet's AIDs go v2.

## Symptoms (two, one root)
1. **OOBI witness-discovery:** on the v2 base, `kli oobi resolve <witness-oobi>` into a fresh keystore persists **nothing** — `db.states` (witness key-state) AND `db.locs`/`db.ends` (endpoints) stay empty. (This is why the re-incepted v2 publisher got 0/3 receipts until witness discovery was manually seeded from the old v1 keystore.)
2. **Peer-blob import:** `src/locksmith/peer/cesr_blob.py` — a v2 peer blob's KEL "parses" but the embedded `/end/role` + `/loc/scheme` rpys never route into `db.ends`/`db.locs`.

## Root cause (confirmed, with proof)
`keripy fork src/keri/db/basing.py:1694 cloneEvtMsg` hardcodes `version=Vrsn_1_0` on every attachment `Counter` (lines ~1719-1742, 1786-1796) and on the enclosing `AttachmentGroup` (~1804-1805). So `hab.replay()` / `db.clonePreIter()` / `hab.replyToOobi()` frame a **v2 event body** (`KERICAAC…`) with **v1 attachment codes** — the AttachmentGroup wrapper emits as `-V`.

Code-point collision: `-V` = `AttachmentGroup` under v1, but `BackerRegistrarSealCouples` under v2 (v2's AttachmentGroup is `-C`). On a v2 Parser, `parsing.py:1295 msgParsator` does `getattr(self, self.methods['BackerRegistrarSealCouples'])` where that method is `None` → `TypeError` → wrapped `ExtractionError` → `allParsator` catches it at **parsing.py:558-563 and runs `del ims[:]`**, flushing the entire remaining stream. Net: the KEL never lands (no `db.states`) and the trailing endpoint rpys are discarded (`Revery.processReply` never called).

The route handlers (`eventing.py:4965 processReplyEndRole`→`updateEnd`; `eventing.py:5061 processReplyLocScheme`→`updateLoc`) are version-agnostic and correct — they just never get reached.

This is the **same class** as the publisher KEL-export bug already fixed (`tools/publisher/src/locksmith_publisher/publish.py export_kel` uses `messagize(..., gvrsn=serder.pvrsn, genusify=(sn==0))` precisely to route around `clonePreIter`'s v1 framing). The `Vrsn_1_0` pins are **upstream** (WebOfTrust, from the 2024 CESR-v2 counting migration) — an incomplete v2 migration, not a fork change.

## Fix (keripy fork, one change fixes both symptoms)
In `basing.py cloneEvtMsg`, version-track the attachment framing: derive `pvrsn = serder.pvrsn` and pass `version=pvrsn` to the six hardcoded `Counter(..., version=Vrsn_1_0)` calls; and prepend the KERIACDCGenusVersion code once at stream head (in the `clonePreIter` iterator, ~`basing.py:1649`, genusify only the first event). The head genus code auto-raises any parser to the right version (`parsing.py:1040-1043`), so v1 consumers still work.

**Proven offline** (`messagize(serder, sigers=sigers, framed=True, gvrsn=serder.pvrsn, genusify=(sn==0))` + v2 rpys):
- BROKEN (`replay`/`clonePreIter`), Parser v2: `srcKEL=False ends=0 locs=0` [GAP]
- BROKEN, Parser v1: `srcKEL=False ends=0 locs=0` [GAP]
- FIXED, Parser v1: `srcKEL=True states=2 ends=1 locs=1` [OK]
- FIXED, Parser v2: `srcKEL=True states=2 ends=1 locs=1` [OK]

One fix covers both because both flow through `cloneEvtMsg`/`replay`. The witness `role=witness` OOBI path (`habbing.py:2469 replyEndRole` witness branch) also calls `self.replay(cid)` → same path → covered.

## What it unblocks / lets us delete
- OOBI witness-discovery on fresh v2 keystores (no more manual seeding).
- Peer-blob import on v2 (no Locksmith change needed — `replyToOobi` flows through the fixed `cloneEvtMsg`).
- The publisher's `export_kel` genusify workaround and Locksmith `receipting.replay_with_evidence`'s reimplemented loop could be simplified back onto the fixed `cloneEvtMsg`.

## Cost / why deferred
- It's a **load-bearing keripy-fork function** (used by `replay`, `replyToOobi`, `clonePreIter`, publisher export). Needs TDD + the full `tests/core/test_replay.py` + `tests/app/test_oobiing.py` + `test_eventing`/`test_parsing` suites green.
- The OOBI-resolve symptom is generated **server-side by the witness**, so activating it in the field needs **another witness federation redeploy** (the witnesses were redeployed on v2 2026-07-10; this would be a second cut with the fixed keripy).
- **Not urgent:** the wallet's own AIDs are v1 (coupled to the 🔴 upstream ACDC/IPEX hold), so peer mode is v1-to-v1 and works today; existing vaults already have witness discovery; the publisher is unblocked via seeding. So the deepest v2 work is upstream-gated regardless — this root fix mainly helps the publisher + future v2 AIDs. Decided 2026-07-10 to capture + do deliberately rather than change keripy core ad hoc.

## Tests to add (keripy fork, when done)
- `tests/core/test_replay.py`: a v2 hab's `replay()`/`clonePreIter()` re-parses into a fresh v2 Habery with `pre in kevers`.
- `tests/app/test_oobiing.py`: v2 hby resolves a v2 OOBI → `db.ends`/`db.locs` populate.

## Repro (offline, deterministic; keri 2.0.0-dev6)
Temp v2 hab → produce OOBI stream (KEL + `/end/role/add` + `/loc/scheme` rpys) via `replay`/`clonePreIter` (broken) vs `messagize+genusify` (fixed); parse under v1 and v2 Parsers; check `db.states`/`db.ends`/`db.locs`. See the offline repro results above (all four cases).

## Related
- v2-hold registry rows: "Peer-blob import" and "`kli oobi resolve` (witness discovery)" — both trace to THIS.
- Publisher export fix: `project_publisher_v2_reset_shipped` (the `export_kel` genusify pattern is the proven fix, applied there locally).
