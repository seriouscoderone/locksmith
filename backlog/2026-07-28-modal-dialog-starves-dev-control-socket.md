# A modal dialog blocks the dev-control socket, so UI tests fail pointing at the wrong call

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** medium (test diagnosability; costs real debugging time)

## What we saw

`tests/integration/peer/test_pair_via_ui.py` and `test_send.py` failed with a bare
`TimeoutError: timed out` raised from the fixture's own socket `recv`
(`tests/integration/peer/conftest.py`), with no wallet-side error and no indication of
which UI state was wrong. Both tests had been failing on `development`.

The actual cause was three steps upstream. Both wallets opened a vault of the **same
name**, the instance coordinator correctly denied the second claim, and the wallet fell
back to the modal `OpenVaultDialog` passcode prompt. Wallet B's log shows the whole
chain:

```
instance.raise.requested vault=ptest
instance.claim.denied vault=ptest
OpenVaultDialog shown; focused passcode field for vault=ptest
```

A modal dialog's `exec()` runs its own event loop and blocks the wallet's main loop, so
`DevControlServer` stops servicing its socket. Every subsequent devctl call — regardless
of what it asks for — times out at the socket layer. The exception surfaces at whatever
call happened to be next, which in these tests was a `wait_for` on a nav button: a
target with nothing to do with vault claiming, passcodes, or instance coordination.

The vault-name collision is fixed (`8663c1d6`). This entry is about the diagnosability
failure that made a five-minute bug cost an hour: **a blocked wallet is
indistinguishable from a slow one, and reports as a failure of the wrong operation.**

## The actual work

1. Make the blockage self-reporting. The dev-control server should be reachable while a
   modal is up, or say so. Options, cheapest first:
   - Have `wait_for`/`click` failures include the wallet's current top-level modal
     widget (name + visible text) in the error payload, so "blocked by
     OpenVaultDialog" is in the failure the test prints.
   - Run the dev-control socket on a thread that survives a nested event loop, so ops
     answer (or explicitly refuse with `{"error": "blocked by modal <name>"}`) instead
     of hanging.
2. On socket timeout, the fixture's `_devctl` should dump the tail of that wallet's log
   into the assertion message. Wallet B's log named the cause on the line before the
   hang, and nothing surfaced it.
3. Consider a fixture-level guard: assert the wallets never open a same-named vault,
   since HOME isolation does not cover the coordinator's system-wide local-socket
   namespace.

## Evidence / references

- `tests/integration/peer/conftest.py` `_devctl` (socket `recv` with a 5s timeout)
- `core/instancing.py:70` `vault_server_name(base, vault)` — name derives from
  `(config.base, vault)` only; `base` is identical across test wallets
- `ui/vaults/open.py` — modal passcode dialog on the denied-claim fallback
- Harness: `~/code/locksmith-ui-tester/src/locksmith_ui_tester/server.py`
  (`DevControlServer`); memory `reference_harness`, `feedback_harness_human_only`
- Surfaced while fixing `2026-07-28-peer-integration-tests-worktree-venv.md`
