# KERI v2 v1-hold registry

**What this is.** Locksmith runs on the KERI-**v2** keripy base (`keri 2.0.0-dev6` = full-CESR,
KERI-spec-v1 compliance). Several code paths are deliberately **held at v1** (`Vrsn_1_0` +
`kind=Kinds.json`) because v2 full-CESR rejects a construct, or because the v2 primitive does not
exist yet. This file is the **single source of truth** for every such hold: why it exists and what
it takes to lift it. The inline `# TRANSITIONAL (KERI v2 v1-hold)` comments say "grep TRANSITIONAL" —
this doc is the index they point at.

**Principle (per the reporter):** v2 is the default. A v1 hold is a tracked debt, not a resting
state. We put in the effort to go v2 **unless it is not currently possible** (e.g. v2 ACDC issuance
that the keri core team has not built yet). When you add a v1 pin, add a row here.

**Two orthogonal axes (do not conflate):**
- **Event serialization** — HELD v1 (the wallet emits its own events as v1 JSON).
- **DB schema** — ADOPTED v2 (`keri.__version__` drives the Baser; migrate-on-open upgrades old
  vaults). *Not* a hold — listed under ✅ so it is not mistaken for pending.

Base: keripy fork `development @ 6ab5019e`. Related: `docs/superpowers/specs/2026-07-07-*v2*`,
memory `project_keri_v2_migration`.

## Status legend
- 🔴 **BLOCKED-UPSTREAM** — cannot go v2 until the keri core team ships the v2 primitive.
- 🟡 **COUPLED** — rides on the event-serialization / serviceaid hold; lifts *jointly* when the
  🔴 items unblock (not independently actionable).
- 🟢 **ACTIONABLE** — v2 is achievable now with our own effort. **Do these.**
- ✅ **ON-V2** — already migrated; listed so it is not mistaken for a pending hold.

---

## 🔴 BLOCKED-UPSTREAM (wait for keri core)

| Hold | Location | Why v1 | Exit criteria |
|---|---|---|---|
| ACDC issuance / TEL registry | `src/locksmith/core/credentialing.py:379`; `core/habbing.py:427` | keripy `vc/proving.py` hardcodes `ri` (no v2 branch); `vdr/credentialing.py`/Reger/Tever/`vcp`/`iss`/`rev` are v1-pinned; v2 ACDC issuance **not implemented** | keri core ships v2 ACDC issuance + TEL registry |
| IPEX grant / admit | `src/locksmith/core/ipexing.py:359,768` | keripy `acdc/ipexing.py` is an empty stub; v2 IPEX machinery not implemented | keri core ships v2 IPEX |
| `keri_serviceaid` v1-hold | keripy fork: `tests/serviceaid` conftest `_hold_serviceaid_v1`, `runtime.py`, `_exn.py`; `Credentialer.create(version=)` seam | Rides on v2 ACDC/IPEX being absent | Lifts with the two rows above |

## 🟡 COUPLED — event-serialization hold (lifts jointly with serviceaid)

The wallet emits its **own** KEL/exn events as v1 so its parser, receipts, and peers stay
self-consistent while its ACDC/IPEX layer is still v1. These are not independently liftable —
they come off together when the 🔴 items unblock and the wallet's event layer flips to v2.

| Hold | Location | Why v1 |
|---|---|---|
| Habery pin (the central hold) | `src/locksmith/core/habbing.py:155` (`open_hby`) | `hby.psr`/`hby.kvy` must read the wallet's own v1 events + v1 witness receipts; v2 default misreads them |
| `makeHab` per-call pins | `core/vaulting.py:80`; KF `onboarding/service.py:1133,1176` | `makeHab` does not inherit `hby.version` |
| challenge exn / `exchange` | `core/remoting.py:920` | `exchange(sender=pre)` defaults v2; v1 for peer interop + no pathed-embed restriction |
| receipt propagation | `core/receipting.py:248` | v2 `eventing.receipt` is CESR-native → `ColdStartError`; pin v1 JSON |
| credential attachment framing | `core/credentialing.py:224` | v1 CESR attachment framing vs v2 |

## 🟢 ACTIONABLE — go v2 now (our own effort)

| Hold | Location | Why v1 today | What it takes to go v2 |
|---|---|---|---|
| **Release seal** (publisher↔verifier) | `tools/publisher/src/locksmith_publisher/seal.py` `build_release_seal`, `publish.py`; verifier `src/locksmith/update/kel_replay.py` `extract_release_seal`, `update/verify.py` | v2 full-CESR cannot serialize the nested-dict / list-of-dicts seal in the ixn `a` field (`mapping.py` `SerializeError`) | Anchor a **SAID/digest** of the release payload (KERI-native — a seal references a digest, not free-form app data), publish the full payload where the verifier can resolve it, keep brand/version/artifact-digest binding. This is **our** contract (not keripy's protocol) → fully in our control. Also unblocks the v0.2.20 publish. See `backlog/2026-07-09-release-seal-not-v2-cesr-serializable.md`. **← in progress** |
| Peer-blob import | `src/locksmith/peer/cesr_blob.py:86` | v2 Revery does not route embedded `/end/role` + `/loc/scheme` rpys into `db.ends`/`db.locs` on a combined-stream import (the KEL parses; only the endpoint rpys don't route) | Investigate: is this a Revery wiring fix on our side, or an upstream v2 gap? If ours, route the rpys explicitly on import. (Peer export already works; this is the import leg.) |

## 🟡 COUPLED-TO-KERIPY-PROTOCOL (not an isolated wallet fix)

| Hold | Location | Why v1 | What it takes to go v2 |
|---|---|---|---|
| Mailbox `/mbx` query topics | `keri-serverless-mailbox` `fetch.py:84`, `serverless.py:113` | v2 CESR `Labeler` rejects the slash-prefixed `/receipt` map **labels** in `q.topics` | The `/mbx` `q.topics` slash-keyed map is **keripy's own mailbox-protocol convention** — both the client and the **deployed federation server** parse it. A v2-native topic representation must be defined with/by keripy and redeployed federation-wide (touches live infra). The v1-JSON pin is correct and stable meanwhile; revisit when keripy defines a v2 mailbox query shape. |

## ✅ ON-V2 (already migrated — not a hold)

| Item | Location | Note |
|---|---|---|
| Vault DB schema | `src/locksmith/core/migrating.py` (`ensure_migrated`) | Adopted v2 (`keri.__version__` → Baser `2.0.0-dev6`); migrate-on-open with backup upgrades old (pre-v2) vaults |
| Inbound parsing / receipts landing | `core/remoting.py` `message_version`, `hby.psr`/`hby.rvy` | Version-aware; v2-ready |

---

## How to lift a hold
1. Confirm the exit criterion is met (upstream primitive shipped, or the actionable effort is done).
2. Remove the `# TRANSITIONAL (KERI v2 v1-hold)` pin(s) for that row (`version=Vrsn_1_0, kind=Kinds.json`).
3. Run the affected tests on the v2 base; add/adjust a v2 round-trip test.
4. Update this row (move to ✅ or delete) in the same change.
5. For 🟡 event-serialization rows: they lift as a set with serviceaid — do not lift one in isolation.
