# Every vault's root key salt is the same hardcoded constant

**Status:** open · **Raised:** 2026-07-28 · **Priority:** high (latent cross-install key collision; no current exploit path)

## What we saw

While auditing AID derivation
(`2026-07-28-derived-aids-collide-across-vaults.md`) the root salt turned out not
to be random and not to be passcode-derived. It is a literal:

```python
# core/configing.py
salt: str = "0123456789abcdef"  # Default salt for key derivation
```

`core/habbing.open_hby` special-cases exactly that string into raw bytes and
hands it to every `Habery` it opens, and `ui/vaults/create.py:177` does the same
for vault creation. keripy persists it as the keystore's root salt on first init
(`keeping.Manager.setup`: `if self.salt is None: self.salt = salt`).

Two consequences:

* **Every Locksmith vault on every machine shares one root salt.** keripy's own
  default when `salt=None` is `Salter().qb64` — random per keystore. Locksmith
  overrides that with a constant. `"0123456789abcdef"` is the salt keripy uses
  throughout its *test* suite, which is where this looks copied from.
* **Any `makeHab` that omits an explicit salt is derivable from its alias
  alone.** `keeping.Manager.incept` with `rooted=True` (the default) falls back
  to the root salt, and the stem is the alias, so "same alias" becomes "same key
  pair" across unrelated installs regardless of passcode. This is the mechanism
  behind the peer listener collision
  (`2026-07-28-peer-endpoint-not-a-real-eid.md`) and the turret settings hab.

Pinned by `tests/core/test_derived_aid_collisions.py`:
`test_the_locksmith_root_salt_is_a_hardcoded_constant` and
`test_a_hab_minted_without_an_explicit_salt_collides_across_vaults` (which
asserts the collision *happens*, deliberately, to document the hazard).

No AID shipping today is exposed: every current call site either passes an
explicit random salt or uses `algo="randy"` — see the audit entry's verdict
table. The finding is that the safety rests entirely on every future call site
remembering to pass a salt, over a root salt that guarantees a collision when
one forgets.

The Defaults settings panel offers a "Key Salt" field and a resalt button
(`ui/dialogs/defaults_settings_widget.py`), but `LocksmithConfig` is an
in-memory singleton and nothing persists the value — so a resalt lasts until the
app restarts, and the constant is back.

## The actual work

1. Decide whether the root salt should be random per vault (keripy's default) or
   stay a user-supplied constant. Random is the safer default and costs nothing:
   the root salt is persisted per keystore at creation, so existing vaults are
   unaffected either way — only newly created vaults change behavior.
2. If it goes random, drop the `"0123456789abcdef"` special case in
   `open_hby` and let `salt=None` reach keripy, and decide what the Defaults
   panel's Key Salt field then means (it currently implies a knob that survives
   a restart, and it does not).
3. If it stays user-supplied, persist it, and say in the UI what setting it
   does — a shared salt across two installs is a shared key derivation, which is
   only meaningful as a recovery story, and there is no recovery story today
   (see the rule doc).
4. Either way, keep the explicit-salt requirement for infrastructure habs. It is
   the rule regardless of what the root salt becomes, because a random root salt
   still collides for two vaults restored from one backup.

## Evidence / references

- `src/locksmith/core/configing.py:72` (the constant), `core/habbing.py:118-134`
  (the special case), `ui/vaults/create.py:177`
- `keripy/src/keri/app/keeping.py:746-763` (`Manager.setup` persists it),
  `:997-1011` (`Manager.incept` root fallback), `:522-550`
  (`SaltyCreator.create` — `(salt, stem)`)
- `docs/superpowers/specs/2026-07-28-aid-salt-derivation-rule.md` (the rule)
- `backlog/2026-07-28-derived-aids-collide-across-vaults.md` (the audit that
  found this), `backlog/2026-07-28-peer-endpoint-not-a-real-eid.md` (the
  collision that started it)
