# Serverless-mailbox v2 query SerializeError tears down the vault db

**Filed:** 2026-07-09 (found while diagnosing the KERI Foundation onboarding crash —
`backlog/2026-07-09-kerifoundation-plugin-brand-leak-and-onboarding-crash.md` Issue 2).
Live repro on vault `carrier2`, current `development` (KERI-v2 keripy base,
`keri 2.0.0-dev6`).

**Severity:** high — breaks mailbox notify-and-fetch for **every** vault on the v2 base,
not just KF, and leaves the vault in a db-closed state that degrades all db-reading UI.

---

## Symptom

On vault open, ~1s after "Vault opened successfully", a `QtTask exception` is logged and
the vault's Habery db silently closes (`hby.db.env` → `None`). The UI stays up but every
db-reading action then fails (the KF onboarding crash was the first one hit; it is now
guarded — see the KF backlog — but the vault is still non-functional: mailbox
notify-and-fetch never runs).

## Root cause (two layers)

### Layer 1 — v2 query serialization rejects the `/receipt` label
`keri_serverless_mailbox` polls the mailbox by building a `qry` event over the poll
topics (`/receipt`, `/multisig`, `/replay`, `/delegate`, `/credential`, `/challenge`,
`/reply`). On the v2 CESR-native base, serializing a map whose **label** is `/receipt`
raises:

```
keri.core.coring.Labeler(label=b'/receipt') -> InvalidValueError: Invalid label=b'/receipt'
  -> keri.core.mapping._serialize / _exhale -> SerializeError: Invalid value while serializing
```

Call path (from the live traceback):
```
keri_serverless_mailbox/client.py:50   runDo
keri_serverless_mailbox/strategy.py:30 run
keri_serverless_mailbox/serverless.py:127 run_serverless
keri_serverless_mailbox/fetch.py:111  fetch_once
keri_serverless_mailbox/fetch.py:83   build_and_post
keri/app/habbing.py:1572              query
keri/core/eventing.py:1089            query
keri/core/mapping.py:693              _serialize -> Labeler(label='/receipt')
```
The mailbox `query`/`build_and_post` path is not pinned to v1 (`Vrsn_1_0`), so on the v2
default it goes through v2 CESR-native serialization, which forbids a `/`-prefixed map
label. This is the same "v2-hold" class as the Locksmith/serviceaid migration
(grep `TRANSITIONAL`), but it lives in the `keri_serverless_mailbox` package
(usuranceai repo) and/or the Locksmith mailbox wiring.

### Layer 2 — a background doer's exception tears down the whole vault db
When the `SerializeError` propagates out of the vault's Doist, hio's Doist teardown
closes **all** doers, including `HaberyDoer` → `hby.close()` → `db.env = None`.
`QtTask.run` (`src/locksmith/core/tasking.py:82`) only logs the exception; the orderly
`AppCore.close_vault()` never runs, so `app.vault` keeps referencing a vault whose db is
now closed. One background doer's failure should not silently kill the entire vault's
database and leave a live-but-dead `app.vault`.

## Fix directions (design before implementing)

1. **Layer 1 (primary):** pin the serverless-mailbox `query`/`build_and_post` path to
   `Vrsn_1_0` (v1 JSON), mirroring the Locksmith/serviceaid v1-hold, OR represent poll
   topics so their map labels are v2-legal. Lands in the `keri_serverless_mailbox`
   package (usuranceai) — coordinate the version-hold with the Locksmith side. This is
   the fix that restores mailbox notify-and-fetch on the v2 base.
2. **Layer 2 (robustness, Locksmith):** a doer exception should degrade that doer, not
   nuke the vault db. Options: isolate the mailbox poller so its failure doesn't abort
   the vault Doist; or on a QtTask exception run the orderly `close_vault()` (so
   `app.vault` is cleared and the UI reflects a closed vault) instead of leaving a
   live-but-dead reference.

## Relationship to the KF onboarding crash
The KF onboarding crash (separate backlog) is a **downstream symptom** of Layer 2:
`list_eligible_local_identifiers` hit the closed db. That is now guarded
(returns `[]` gracefully), but the guard only stops the crash — it does **not** restore
the vault. Fixing Layer 1 (and ideally Layer 2) is what makes the vault usable again.

## Repro
```
.venv/bin/python -m locksmith.main   # dev build on development (v2 base)
```
Open `carrier2` (passcode `noble`). Watch the log: ~1s after open, `QtTask exception:
Invalid value while serializing`. Then any db-reading action (e.g. clicking "KERI
Foundation") finds `hby.db.env is None`.
