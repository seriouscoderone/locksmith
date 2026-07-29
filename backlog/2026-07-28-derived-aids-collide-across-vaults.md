# Two vaults with the same passcode mint identical AIDs for the same alias

**Status:** fixed for the peer listener; **unaudited elsewhere** · **Raised:** 2026-07-28 · **Priority:** high (silent cross-vault identity collision)

## What we saw

While adding the peer listener EID (`2026-07-28-peer-endpoint-not-a-real-eid.md`), the
two-wallet integration test showed the sender dialing **its own port**. Both wallets had
minted the same endpoint identifier:

```
a.log: peer.listener.minted alias=peer-listener eid=BOK1SMMQpNdiQpOrpoH0UvK4sb3AgV6HgxHhK-7SmNZe
b.log: peer.listener.minted alias=peer-listener eid=BOK1SMMQpNdiQpOrpoH0UvK4sb3AgV6HgxHhK-7SmNZe
```

Two independent vaults, separate HOMEs, separate keystores, separate vault names — same
AID. Salty key creation derives from `(Habery salt, stem)`, the stem comes from the hab's
alias, and the Habery's salt follows the **passcode**. Same passcode plus same alias means
the same key pair, and for a non-transferable hab the prefix *is* the public key.

The damage is not just a duplicate identifier. `db.locs` is keyed `(eid, scheme)`, so two
different sockets contended for one location record and BADA's datestamp picked a winner.
A peer paired with both vaults resolved **one** address for both and sent traffic to the
wrong one — no error anywhere, the send reported success.

Fixed for the listener by minting it with a fresh random `Salter().qb64` rather than
inheriting the Habery's salt (`src/locksmith/peer/listener_eid.py`); keys still persist in
the keystore so the EID is stable across restarts, just not derivable. Pinned by
`tests/peer/test_listener_eid.py::test_two_vaults_with_the_same_passcode_get_different_listener_eids`.

## Why this needs a wider audit

Two *users* sharing a passcode is unlikely. One user's two vaults sharing a passcode is
ordinary — and multi-instance vaults are a shipped feature
(memory `project_multi_instance_vaults`). Any place that creates a hab from a
well-known alias inherits the same collision:

- `core/vaulting.py:78` — the turret's `ns="settings"` hab, alias
  `f"plugin-{hby.name}"`. Currently varies by vault *name*, so two same-named vaults on
  different machines with the same passcode collide.
- `plugins/kerifoundation/onboarding/service.py:1124` — check what alias it uses.
- Any brand `default_aid_alias` inception: two HOA installs sharing a passcode would mint
  the same "identity", which for a *transferable* AID is worse than for an endpoint —
  duplicate KELs for one prefix is duplicity.

That last case is the one to check first. It is plausible in the field: an operator
setting up several machines from the same written-down passcode.

## The actual work

1. Audit every `makeHab` call site for alias-derived collision risk; the grep is
   `makeHab` across `src/`.
2. Decide the rule and write it down. Candidates: infrastructure identifiers
   (endpoints, plugin-local) always get a random salt; user identities are allowed to be
   passcode-derived *only* if that is a deliberate recovery feature, in which case say so
   where the passcode is collected.
3. If passcode-derived user AIDs are intentional (a "restore from passcode" story), the
   collision is a *feature* and the vault should refuse to open two vaults deriving the
   same AID rather than let both run.

## Evidence / references

- `src/locksmith/peer/listener_eid.py` (the fix and the reasoning)
- `keripy/src/keri/app/habbing.py:2890-2947` (`Hab.incept` — `algo`/`salt`/`tier`)
- `src/locksmith/core/vaulting.py:78`, `src/locksmith/plugins/kerifoundation/onboarding/service.py:1124`
- Memory: `project_multi_instance_vaults`
- Surfaced by `tests/integration/peer/test_send.py` during
  `2026-07-28-peer-endpoint-not-a-real-eid.md`
