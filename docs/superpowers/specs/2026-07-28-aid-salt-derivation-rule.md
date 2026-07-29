# The AID salt derivation rule

**Status:** adopted 2026-07-28 · **Applies to:** every `makeHab` / `create_identifier` call site in `src/`

## The rule

**1. Infrastructure identifiers ALWAYS mint with a fresh random salt.**

An endpoint, a plugin-local hab, a hidden auth principal — anything the user
never sees in the Identifiers page (anything with a non-empty `ns=`) — passes
`salt=Salter().qb64` explicitly:

```python
hab = hby.makeHab(name=alias, ns="peer", transferable=False,
                  salt=Salter().qb64, version=Vrsn_1_0)
```

The keys still persist in the keystore, so the identifier is stable across
restarts. It is simply not *derivable* from anything two installs could share.
Reference implementation: `src/locksmith/peer/listener_eid.py`.

Uniqueness that comes from the alias instead — a uuid4 in the name, a vault name
in the stem — does not satisfy this rule. It is uniqueness by accident: correct
until someone shortens the alias or two vaults are given the same name, with no
test failing when it breaks. Pass the salt.

**2. User identities are passcode-derived only as a deliberate, documented
recovery feature — and Locksmith has no such feature.**

Today every user-identity path mints with a fresh random salt
(`core/bootstrapping.py` for the brand default AID, the Key Salt field in
`ui/vault/identifiers/create.py` for manual creation). That is the intended
behavior and it is pinned by `tests/core/test_derived_aid_collisions.py`.

If a "restore your identity from your passcode" feature is ever wanted, it may
not simply arrive by making the derivation deterministic. It requires, in the
same change:

* saying so where the passcode is collected — a passcode that reconstructs an
  identity is a very different secret from one that merely unlocks a file; and
* **refusing to open two vaults that derive the same AID.** Deterministic
  derivation makes a colliding prefix reachable *by design*, so the vault must
  detect it and refuse, rather than let two instances write two KELs under one
  prefix. Duplicity is the failure KERI exists to prevent, and it is
  unrecoverable — a watcher that sees both KELs treats the identity as
  compromised.

## Why the salt and not the alias

Salty key creation derives from `(salt, stem)`. The stem is the hab's alias
(`keeping.SaltyCreator.create`), and when a call site passes no salt,
`keeping.Manager.incept` falls back to the keystore's **root** salt
(`rooted=True` → `salt = self.salt`). So for any hab minted without an explicit
salt, the alias is the only varying input.

In Locksmith the root salt is worse than passcode-derived: it is the hardcoded
literal `"0123456789abcdef"` (`core/configing.py`), fed to every Habery by
`core/habbing.open_hby`. It is the same value in every vault on every machine —
so two installs that mint the same alias without an explicit salt get the
*identical* prefix regardless of passcode. Tracked as
`backlog/2026-07-28-vault-root-salt-is-a-hardcoded-constant.md`.

Note what the passcode does *not* do: `Habery.setup` stretches `bran` into the
keystore's `aeid` (the encryption identity) and never into the signing-key salt.
A passcode protects the keystore at rest. It contributes nothing to key
derivation, so it can neither cause nor prevent a collision.

## How this was established

`backlog/2026-07-28-derived-aids-collide-across-vaults.md` — the audit, its
per-call-site verdicts, and the empirical answers for the empty-passcode and
shared-passcode cases. The collision that started it:
`backlog/2026-07-28-peer-endpoint-not-a-real-eid.md`.
