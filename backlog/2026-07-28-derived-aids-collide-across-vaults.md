# Two vaults with the same passcode mint identical AIDs for the same alias

**Status:** audited 2026-07-28 — **the default-identity path is safe**; two infra habs fixed; root-salt finding filed separately · **Raised:** 2026-07-28 · **Priority:** was high (silent cross-vault identity collision)

## What we saw

While adding the peer listener EID (`2026-07-28-peer-endpoint-not-a-real-eid.md`), the
two-wallet integration test showed the sender dialing **its own port**. Both wallets had
minted the same endpoint identifier:

```
a.log: peer.listener.minted alias=peer-listener eid=BOK1SMMQpNdiQpOrpoH0UvK4sb3AgV6HgxHhK-7SmNZe
b.log: peer.listener.minted alias=peer-listener eid=BOK1SMMQpNdiQpOrpoH0UvK4sb3AgV6HgxHhK-7SmNZe
```

Two independent vaults, separate HOMEs, separate keystores, separate vault names — same
AID. Salty key creation derives from `(salt, stem)`, the stem comes from the hab's
alias, and a call site that passes no salt falls back to the keystore's root salt.

The damage is not just a duplicate identifier. `db.locs` is keyed `(eid, scheme)`, so two
different sockets contended for one location record and BADA's datestamp picked a winner.
A peer paired with both vaults resolved **one** address for both and sent traffic to the
wrong one — no error anywhere, the send reported success.

Fixed for the listener by minting it with a fresh random `Salter().qb64` rather than
inheriting the Habery's salt (`src/locksmith/peer/listener_eid.py`); keys still persist in
the keystore so the EID is stable across restarts, just not derivable. Pinned by
`tests/peer/test_listener_eid.py::test_two_vaults_with_the_same_passcode_get_different_listener_eids`.

## Audit result

### The headline: the default identity is safe, and the passcode was a red herring

**The brand `default_aid_alias` inception path does NOT collide.**
`core/bootstrapping.py:180` mints the default AID with a fresh random
`signing.Salter().qb64[2:23]` per bootstrap, so two HOA installs sharing a
passcode get different identities. The imminent two-machine test is valid on this
axis and the release is not gated by it.

**The passcode never entered key derivation at all.** The original diagnosis
above — "the Habery's salt follows the passcode" — is wrong. `Habery.setup`
stretches `bran` into the keystore's *aeid* (the at-rest encryption identity) and
never into the signing-key salt. A passcode can therefore neither cause nor
prevent a collision.

**What actually collides is worse than passcode-derived.** The root salt is the
hardcoded literal `"0123456789abcdef"` (`core/configing.py:72`), handed to every
Habery by `open_hby`. It is the same value in every vault on every machine, so
any hab minted *without* an explicit salt collides across installs regardless of
passcode. Filed as
`backlog/2026-07-28-vault-root-salt-is-a-hardcoded-constant.md`.

### Per-call-site verdicts

| Call site | Mints | Salt source | Verdict |
|---|---|---|---|
| `core/bootstrapping.py:180` → `create_identifier` (brand `default_aid_alias`) | user identity, transferable | explicit fresh `Salter().qb64[2:23]` per bootstrap | **safe** (proven empirically) |
| `ui/vault/identifiers/create.py:137,362` → `create_identifier` | user identity | explicit; field default is a fresh `Salter()` per dialog open | **safe** (user may override — a deliberate act) |
| `core/habbing.py:544` (`create_identifier` local-delegation branch) | user identity | caller's explicit salt; salty branch *rejects* a missing/short salt (`:443`) | **safe** |
| `core/habbing.py:700` (`InceptDoer`) | user identity | same explicit salt, via `creation_kwargs` | **safe** |
| `create_identifier` `key_type="randy"` | user identity | `salt=None` + random algo | **safe** |
| `create_identifier` `key_type="group"`, `core/grouping.py:260,458` | group AID | derived from `smids`/thresholds, no salt | **safe by design** (deterministic group AIDs are intended KERI) |
| `peer/listener_eid.py:70` | infra EID | explicit `Salter().qb64` | **safe** (fixed by the peer-EID work) |
| `plugins/kerifoundation/onboarding/service.py:1124` (KF account AID) | user identity | `algo="randy"` | **safe** |
| `core/vaulting.py:78` (turret `ns="settings"` hab) | infra hab | **no salt** → root salt; stem `f"plugin-{hby.name}"` | **was alias-derived risk — FIXED** (dormant: `ENABLE_TURRET_BROWSER_PLUGIN` is False) |
| `plugins/kerifoundation/onboarding/service.py:1166` (hidden onboarding auth) | infra hab, non-transferable | **no salt** → root salt; alias carried a uuid4 | **was safe only by accident — FIXED** |
| `turret/existing.py:38` | nothing — opens an existing keystore | n/a | **n/a** |
| `ui/vaults/create.py:184`, `core/habbing.py:163` (`Habery`) | the keystore root salt | hardcoded `config.salt` | **finding, filed separately** |

### Empirical answers

`tests/core/test_derived_aid_collisions.py`, 10 tests, all passing. They drive
real Haberies built with the arguments `open_hby` really passes and mint through
real production code (`bootstrap_default_environment`, `create_identifier`'s
synchronous salty branch).

* **Empty passcode** (Usurance's `default_passcode = ""`), two fresh vaults, same
  alias → **different AIDs**. The bootstrap's AID salt is random per run.
* **Same non-empty passcode** (the written-down-company-passcode scenario), two
  fresh vaults, same alias → **different AIDs**.
* The AID salt is **not** a function of the passcode (three bootstraps, two
  passcodes, three distinct salts).
* The collision mechanism is real and reproducible: two vaults minting one alias
  with *no* explicit salt produce the identical prefix, asserted as equal on
  purpose to document the hazard. Same for the turret's `f"plugin-{hby.name}"`
  alias across two vaults that happen to share a name.

The three passing collision tests were verified against a mutant — bootstrapping
patched to derive the AID salt from the passcode — and all three failed, so they
genuinely catch the bug rather than passing vacuously.

## The rule (adopted)

`docs/superpowers/specs/2026-07-28-aid-salt-derivation-rule.md`:

1. **Infrastructure identifiers always mint with a fresh random salt** — anything
   with a non-empty `ns=`, passing `salt=Salter().qb64` explicitly. Uniqueness
   that comes from the alias instead (a uuid4, a vault name) does not count: it
   is correct by accident and no test fails when it breaks.
2. **User identities may be passcode-derived only as a deliberate, documented
   recovery feature**, and Locksmith has none. Adding one requires, in the same
   change, saying so where the passcode is collected *and* refusing to open two
   vaults that derive the same AID — deterministic derivation makes duplicity
   reachable by design.

## Fixed here

* `core/vaulting.py` — the turret settings hab extracted into
  `ensure_turret_settings_hab`, minting with `salt=Salter().qb64` (mirrors
  `listener_eid.py`, and the extraction is what makes it testable).
* `plugins/kerifoundation/onboarding/service.py:1166` — the hidden onboarding
  auth hab now passes an explicit random salt instead of relying on its uuid4
  alias.
* `tests/test_kerifoundation_onboarding_service.py` — the exact-kwargs assertion
  on that call now requires a valid salt rather than freezing a random value.

## Deferred

* The hardcoded root salt →
  `backlog/2026-07-28-vault-root-salt-is-a-hardcoded-constant.md`.
* The Defaults panel's Key Salt field does not persist (in-memory singleton), so
  a resalt lasts until restart — covered by the same entry.

## Evidence / references

- `src/locksmith/peer/listener_eid.py` (the fix and the reasoning)
- `tests/core/test_derived_aid_collisions.py` (the empirical answers)
- `keripy/src/keri/app/habbing.py:267-281` (`bran` → aeid, salt is separate),
  `keripy/src/keri/app/keeping.py:997-1011` (`Manager.incept` root-salt
  fallback), `:522-550` (`SaltyCreator.create` — `(salt, stem)`)
- Memory: `project_multi_instance_vaults`
- Surfaced by `tests/integration/peer/test_send.py` during
  `2026-07-28-peer-endpoint-not-a-real-eid.md`
