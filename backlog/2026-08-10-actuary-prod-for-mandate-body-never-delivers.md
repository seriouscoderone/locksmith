# The actuary's prod for a mandate body never reaches the CUO — cause UNDETERMINED

**Status:** backlog · **Raised:** 2026-08-10 · **Priority:** medium — see "Why this is not a shipping blocker"

## Why this is not a shipping blocker

Two facts, established after this item was first written, argue the product is
probably fine and the TEST's premise is not met:

* `test_the_admin_issues_and_grants_both_roles_live` **passes** — live IPEX
  issue → grant → admit between two real wallets over peer TCP. Delivery to a
  reachable wallet demonstrably works.
* This test fails on the **old** keri pin too, so nothing in v0.4.0 caused it.

And the decisive gap: **`direct_transport` logs no bind/listen event at all**
(its whole vocabulary is `no_hab` / `paired` / `pair_failed` /
`refresh_failed` / `repaired`). So the logs CANNOT distinguish
"delivery is broken" from "the fixture's responder was never accepting on the
port it advertised". The original version of this item asserted the former;
that was not supported by the evidence. Fix the observability first (below),
then re-read the failure.

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
| `EIvIIoCGDPv5` | `tcp://127.0.0.1:63548` | 27 | **the only interesting ones** — this is the CUO, and it is running |

So the question is narrow: 27 prods to a live, paired, correctly-addressed peer
report undelivered. Addressing is definitely right — the CUO logged
`peer.role.published aid=EIvIIoCGDPv5… url=tcp://127.0.0.1:63548` and the
actuary dialed exactly that, with a matching listener eid
(`BHpGRZ39d5Q_owzXuODfp0X9HrhXXUeTTqiyeV3F--Q3`; the harness uses a fixed salt,
so eids are deterministic across runs). What is NOT established is whether the
CUO's listener ever accepted on that port — nothing logs it.

## Two things to fix

1. **The observability gap, FIRST — it is why the cause is undetermined.**
   Two holes:

   * `direct_transport` never logs that it bound (or failed to bind) a peer
     listener, so "is the responder actually accepting?" is unanswerable from a
     log. Add a bind/failed-to-bind line naming host:port. Without it, every
     future prod-silence investigation stalls exactly here.
   * `peer_sync.undelivered` is `logger.debug` while `peer_sync.queued` beside it
     is `logger.info`, so at default level a wallet appears to prod forever with
     no hint the bytes never left the machine. This is the SAME trap the code
     already documents at `peer_sync_doer.py:316-319` — it used to lie by logging
     `sent`, and now it simply goes quiet. A peer undelivered N times running
     deserves an INFO line naming the endpoint.

2. **Then re-read the failure**, and only if it survives: start at
   `peer_sync_doer`'s worker that sets `outcome["delivered"]` and find why a dial
   to a bound local listener reports undelivered. Note the harness never asserts
   the responder is accepting, so an unmet precondition is the leading
   hypothesis — the test docstring records EIGHT prior defects in this path,
   "every one of which produced identical silence on the wire".

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
