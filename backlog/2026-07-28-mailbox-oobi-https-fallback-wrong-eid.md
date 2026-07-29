# The mailbox OOBI's https fallback looks up the wrong EID

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** low-medium (wrong host in a generated OOBI, or a misleading error)

## What we saw

`src/locksmith/turret/handling.py:337`, in the `Roles.mailbox` branch of OOBI generation:

```python
for (_, _, eid), end in hab.db.ends.getTopItemIter(keys=(hab.pre, kering.Roles.mailbox,)):
    ...
    urls = hab.fetchUrls(eid=eid, scheme=kering.Schemes.http) \
           or hab.fetchUrls(eid=hab.pre, scheme=kering.Schemes.https)
    ...
    oobi = f"{url.rstrip('/')}/oobi/{hab.pre}/mailbox/{eid}"
```

The http lookup correctly asks for the **mailbox's** `eid`. The https fallback asks for
`hab.pre` — the controller's own endpoint. So for a mailbox that publishes only https:

- if the controller has no https endpoint, `urls` is empty and the error says *"identifier
  … does not have any mailbox endpoints"*, which is false — the mailbox has one;
- if the controller *does* have an https endpoint, it is worse: the OOBI is built from the
  **controller's** host while the path still names the mailbox
  (`/oobi/<cid>/mailbox/<eid>`), so the generated OOBI points at the wrong server and
  whoever resolves it gets nothing back for that eid.

Looks like copy-paste from the `controller` branch immediately above, where `eid=hab.pre`
is genuinely correct (a controller *is* its own endpoint provider). Spotted while auditing
`db.locs`/`fetchUrls` call sites for
`2026-07-28-peer-endpoint-not-a-real-eid.md`; not touched by that change, since it is the
mailbox role rather than peer.

Note the whole block is wrapped in a bare `except: oobi = ""` (`:347`), so neither failure
mode raises — the caller just gets an empty OOBI with no reason logged. That swallowing is
arguably the bigger problem.

## The actual work

1. `eid=hab.pre` → `eid=eid` in the https fallback. Better still,
   `hab.fetchUrls(eid=eid, scheme="")` returns all schemes in one call, which is what
   `fetchRoleUrls`/`endsFor` do internally and removes the two-call fallback entirely.
2. A test: a mailbox EID publishing **only** https must produce an OOBI on the mailbox's
   host. There is no coverage of this branch today, which is why it survived.
3. Separately, narrow the bare `except:` at `:347` so a config error is distinguishable
   from "no OOBI available" — an empty string is currently the answer to both.

## Evidence / references

- `src/locksmith/turret/handling.py:332-347`
- `keripy/src/keri/app/habbing.py:2021` (`fetchUrls(eid, scheme="")` — all schemes)
- Sibling in the same file: the `controller` branch at `:325`, where `eid=hab.pre` is correct
