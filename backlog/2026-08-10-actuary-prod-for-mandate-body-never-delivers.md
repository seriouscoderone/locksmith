# The actuary's prod for a mandate body never reaches the CUO

**Status:** backlog · **Raised:** 2026-08-10 · **Priority:** high (a shipped role cannot fetch the credential body it is meant to attest against)

## What fails

`tests/integration/roles/test_actuary_retrieves_mandate_via_prod.py::
test_the_actuary_retrieves_the_mandate_by_prodding_for_it` — the actuary asks
the CUO for a sealed mandate body over the real pro/bar path and gets nothing.
Reproducible 3/3, not a flake.

**Not a regression from the v0.4.0 keri bump.** Verified by checking out the
previous pin (`1c127b59`) against the same tree: fails identically. The bump to
`dc88ea0d` is exonerated, despite six of its commits touching this exact path.

## What the evidence says

Run with `LOCKSMITH_KEEP_TEST_HOMES=1 LOCKSMITH_LOG_LEVEL=DEBUG`, the actuary's
`peer_sync` counters are:

```
132 peer_sync.queued
123 peer_sync.undelivered
 64 peer_sync.body_ask_refunded
  0 peer_sync.sent / .received
```

Nothing reaches the wire. This is a DELIVERY failure, not the CUO declining to
answer a prod it received — the CUO's log contains zero `prod`/`bare`/`exn`
lines.

Broken down by peer, most of that is expected fixture noise:

| peer | endpoint | undelivered | verdict |
|---|---|---|---|
| `EGjm-X1JMz-y` | `tcp://192.168.1.162:5621` | 77 | expected — the real Usurance authority, not running in a test |
| `EHdNc8llEejN` | `tcp://127.0.0.1:1/` | ~20 | expected — deliberate black-hole sentinel (`conftest.py:424`, "The URL is never dialed") |
| `EIvIIoCGDPv5` | `tcp://127.0.0.1:63548` | 27 | **THE BUG** — this is the CUO, and it IS running with a bound listener |

So the real defect is narrow: prods to a live, paired, correctly-addressed peer
report undelivered. The CUO's advertised eid in the actuary's import
(`BHpGRZ39d5Q_owzXuODfp0X9HrhXXUeTTqiyeV3F--Q3`) matches the eid the CUO minted,
so this is not a stale-PeerRecord/wrong-endpoint case.

## Two things to fix

1. **The delivery itself.** Start at `peer_sync_doer._queue_*` → the worker that
   sets `outcome["delivered"]`, and find why a dial to a bound local listener
   reports undelivered. Confirm the CUO's peer listener is actually accepting on
   the port it advertised (the harness never asserts this).

2. **The observability gap that hid it** (cheap, do it first).
   `peer_sync.undelivered` is `logger.debug` while `peer_sync.queued` beside it
   is `logger.info`, so at default level a wallet appears to prod forever with
   no hint the bytes never left the machine. This is the SAME trap the code
   already documents at `peer_sync_doer.py:316-319` — it used to lie by logging
   `sent`, and now it simply goes quiet. A peer that has been undelivered N
   times running deserves an INFO line naming the endpoint.

## Fixture noise worth separating

A test wallet re-prods the owner's real authority at `192.168.1.162:5621` every
10s because the endpoint is baked into the bundled brand OOBI. Harmless, but it
makes every roles-test log look alarming and pads the undelivered count ~3x.
Consider pointing the harness's brand EGF at a sentinel endpoint the way
`conftest.py:424` already does for the admin.

## Reproduce

```
LOCKSMITH_KEEP_TEST_HOMES=1 LOCKSMITH_LOG_LEVEL=DEBUG \
  .venv/bin/python -m pytest \
  tests/integration/roles/test_actuary_retrieves_mandate_via_prod.py \
  -q --import-mode=importlib -m integration
# logs survive at /tmp/lshoa-*/{actuary,cuo}.log
```

Note the rest of the suite is green: 9 passed, 1 failed — including the
four-window arc and admin-grants-to-both-HOAs.
