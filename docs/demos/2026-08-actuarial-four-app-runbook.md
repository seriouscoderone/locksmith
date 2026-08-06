# The actuarial-HOA four-app arc — manual runbook

Four separately-launched Locksmith processes — one **stock** admin wallet and three
Usurance-branded HOAs (CUO, actuary, product designer) — walk the whole
mandate→rate→assembly membrane by hand: admin grants the three role credentials, the
CUO declares a mandate, the actuary watches for it and attests from a real `ipd-parse`
run, the designer receives the rate program and assembles a bundle, and a revoke
removes exactly the revoked surface without a restart.

This is the **manual** pass (parent design's "manual milestone", Plan C2c Task 8 Step
8) — judging whether a surface *reads right* is a human call automation cannot make.
For the headless, CI-safe equivalent that proves the same arc mechanically (minus
that judgment), see `tests/integration/roles/test_four_app_arc_via_ui.py` and its own
module docstring for exactly which leg it drives differently and why.

## Before you start

- **Stage the brand.** `cd ~/code/locksmith && .venv/bin/python scripts/brand_apply.py
  --brand usurance` — writes `src/locksmith/release/usurance/{brand.json,egf/,...}`.
  A frozen build (and every HOA launch below) reads **that staged copy**, never
  `brands/usurance/` directly — `tests/core/test_staged_brand_matches_source.py`
  guards against running a demo against a stage that has drifted from the source
  (skips if nothing is staged yet; fails if what's staged disagrees with
  `brands/usurance/egf/`).
- **Install the UI driver plugin** (`locksmith-ui-tester`) into `~/.locksmith/plugins/`
  if you intend to verify state with `devctl` alongside the manual pass — see fact 8
  and the launch-sequence note below for how to bring it up per HOME. Not required to
  run the demo itself; only to double-check a surface's state without eyeballing it.
- **The `ipd-parse` fixture workbook** the actuary loads needs the parser's own venv:
  `~/code/ugard/insurance-product/parser/.venv` with `openpyxl` installed (`python3 -m
  venv .venv && .venv/bin/pip install -e .` from that directory, if it doesn't already
  exist). The actuary surface shells out to it; it is never invoked from Locksmith's
  own venv, which has no `openpyxl`.
- **The operator passcode is never touched by an agent.** Every step below that opens
  or unlocks a vault is a human action, full stop — this rule holds even though the
  automated arc uses a fixed, non-secret test passcode for its own throwaway,
  isolated-tmpdir vaults (`tests/integration/peer/conftest.py::DEFAULT_TEST_PASSCODE`).

## Environment facts (each one learned the hard way)

1. **Admin is STOCK locksmith, not an HOA.** Locksmith resolves its active brand in
   this order: the `LOCKSMITH_BRAND_CONFIG` env var, then the packaged
   `src/locksmith/release/brand.json` (a **flat**, brand-agnostic path — only the
   reference "locksmith" brand ever lands there; `brand_apply` writes every other
   brand into its own namespaced `release/<brand>/` subdir, see
   `packaging/brandlib.py::brand_release_dir`), then the hardcoded reference `Brand()`
   defaults. So `brand_apply --brand usurance` does **not** overwrite
   `release/brand.json` — launching admin with **no** `LOCKSMITH_BRAND_CONFIG` already
   gets stock Locksmith, *provided* that flat file is either absent or itself holds
   the reference brand. If it has ever been left holding something else (a stale
   manual copy, or a future `brand_apply --brand locksmith` run with different
   content), delete it before the demo so admin falls back cleanly:
   `rm -f src/locksmith/release/brand.json`.
2. **Each HOA launches with `LOCKSMITH_BRAND_CONFIG=<path-to-staged-usurance-brand.json>`**
   — i.e. `src/locksmith/release/usurance/brand.json` after staging. This is what
   turns on the `cuo`/`actuary`/`product_designer` plugins and the bundled EGF; admin
   must **not** set this.
3. **Per-app isolation needs its own `LOCKSMITH_CONTROL_SOCKET` *and* its own `HOME`
   *and* a distinct vault name.** `HOME` isolates the LMDB/keystore files, but the
   vault-open coordinator does **not** key off `HOME` — `vault_server_name()`
   (`src/locksmith/core/instancing.py`) hashes `{bundle-id}\x00{vault-name}` into a
   system-wide `QLocalServer` name. Two processes with the SAME brand (same
   bundle-id) opening the SAME vault name collide even across separate `HOME`s: the
   second process's coordinator claim is denied, it falls back to a modal passcode
   dialog, and that modal freezes its own Qt event loop (and, if `ui_tester` is
   attached, its dev-control socket along with it — the symptom is an opaque
   `TimeoutError` on the *next* `devctl` call, nowhere near the real cause). Give
   every wallet below — including admin — its own `HOME`, its own
   `LOCKSMITH_CONTROL_SOCKET` path, and its own vault name.
4. **The default dev brand has zero plugins and zero EGF.** Launching *any* wallet
   with no `LOCKSMITH_BRAND_CONFIG` shows no role surface at all (no Underwriting /
   Actuarial / Insurance Product Design menu entries) — that is admin's correct,
   expected state, not a bug. If a CUO/actuary/designer window ever shows this same
   bare state, its `LOCKSMITH_BRAND_CONFIG` is missing or points at the wrong file.
5. **Admin's peer listener runs on `:5621`, open-inbound ON, AID exposed.** Settings →
   Peer Mode → enable, port `5621`, advertised host `127.0.0.1` (or the real LAN IP
   for a genuinely cross-machine demo) → Save and restart listener. Then check "Accept
   introductions from verified first-contact senders" (open-inbound) so the three HOAs
   can pair with admin without a prior out-of-band exchange. View admin's identifier →
   toggle "Expose over peer mode" → confirm the toolbar peer indicator is green before
   moving on.
6. **Issue and grant are separate steps.** "Issue Credential" (Credentials → Issued →
   Issue Credential) only mints the credential into admin's own registry — it does
   **not** send anything. Delivery is the Issued Credentials row's own **Grant**
   action (`GrantCredentialDialog`): pick the recipient, leave "Send" selected, click
   Grant. Forgetting this step is the single most common reason a HOA never sees its
   role gate open.
7. **Side-load role schemas with "Use for Credential Issuance" checked** — this is
   what creates the registry inline (Credentials → Schemas → Add Schema → browse to
   the role schema's `.json` under the staged
   `src/locksmith/release/usurance/egf/`, check the box, pick admin's identifier as
   issuer). Do this once per role schema (`cuo_role`, `actuary_role`,
   `product_designer_role`) before the first Issue Credential for that role.
8. **`ui_tester` drives the GUI headlessly for verification** (`current_page` /
   `tree` / `is_visible` / `click`, over the `LOCKSMITH_CONTROL_SOCKET` Unix socket) —
   copy the plugin install (`~/.locksmith/plugins/ui_tester`) into each fresh HOME's
   own `~/.locksmith/plugins` if you want to script-verify a step's outcome instead of
   eyeballing it. Not required for the manual pass itself.
9. **Read keystore state read-only, without blocking the running app**, via
   `Baser`/`Reger` opened `readonly=True, lock=False` against a HOME whose wallet is
   still open — useful for inspecting a running wallet's LMDB (e.g. confirming a
   registry landed) without closing it first. LMDB's MVCC allows this safely; a
   `readonly=False` open against an already-open environment can corrupt or hang.
10. **The operator passcode is never touched by an agent.** Restated from "Before you
    start" because it is the one rule every other step in this runbook defers to: an
    agent may launch processes, click through non-secret UI, and read state, but the
    human enters every passcode, every time.

## Launch sequence

Use four terminals (or four backgrounded launches), each with its own `HOME`:

```bash
cd ~/code/locksmith

# 1. Admin — stock locksmith, no brand config.
rm -f src/locksmith/release/brand.json   # only if it has ever been left non-reference
HOME=/tmp/four-app-admin LOCKSMITH_CONTROL_SOCKET=/tmp/four-app-admin/.locksmith-control.sock \
  .venv/bin/python -m locksmith.main &

# 2. CUO — Usurance HOA.
HOME=/tmp/four-app-cuo \
  LOCKSMITH_BRAND_CONFIG=$PWD/src/locksmith/release/usurance/brand.json \
  LOCKSMITH_CONTROL_SOCKET=/tmp/four-app-cuo/.locksmith-control.sock \
  .venv/bin/python -m locksmith.main &

# 3. Actuary — Usurance HOA.
HOME=/tmp/four-app-actuary \
  LOCKSMITH_BRAND_CONFIG=$PWD/src/locksmith/release/usurance/brand.json \
  LOCKSMITH_CONTROL_SOCKET=/tmp/four-app-actuary/.locksmith-control.sock \
  .venv/bin/python -m locksmith.main &

# 4. Product designer — Usurance HOA.
HOME=/tmp/four-app-designer \
  LOCKSMITH_BRAND_CONFIG=$PWD/src/locksmith/release/usurance/brand.json \
  LOCKSMITH_CONTROL_SOCKET=/tmp/four-app-designer/.locksmith-control.sock \
  .venv/bin/python -m locksmith.main &
```

If verifying with `ui_tester`, first `mkdir -p /tmp/four-app-{admin,cuo,actuary,designer}/.locksmith`
and copy `~/.locksmith/plugins` into each `<HOME>/.locksmith/plugins` before launch
(fact 8) — the plugin only comes up if it's present at process start.

Create/open a vault in each window with a **distinct name** (fact 3) — e.g.
`admin-vault`, `cuo-vault`, `actuary-vault`, `designer-vault` — and one AID per vault,
entering the passcode yourself each time (fact 10).

## The arc

1. **Admin: side-load the three role schemas** (fact 7) — `cuo_role`,
   `actuary_role`, `product_designer_role` — from
   `src/locksmith/release/usurance/egf/`, each with "Use for Credential Issuance"
   checked and admin's identifier as issuer.
2. **Admin: enable the peer listener** on `:5621`, open-inbound on, AID exposed
   (fact 5).
3. **Pair each HOA with admin.** In each of CUO/actuary/designer: Settings → Add Peer
   → paste admin's exported peer blob (from admin's View Identifier → Expose → "Peer
   (offline)", or admin's own listener address if resolving live) → Pair.
4. **Admin issues, then grants, each role credential** (fact 6): Issue Credential
   (schema = the role, recipient = the paired HOA's AID, no attributes) → wait for
   "Credential issued" → Issued Credentials row → Grant → recipient = the same AID →
   Send. Repeat for all three HOAs/roles. Each HOA's Notifications page picks up the
   grant; Admit it there (this step is the one leg
   `test_four_app_arc_via_ui.py` does **not** drive automatically — see that file's
   module docstring for the measured reason). The role's menu entry
   (Underwriting / Actuarial / Insurance Product Design) appears once the gate
   opens.
5. **CUO declares a mandate.** Underwriting → fill in line of business, jurisdiction,
   coverages, effective window, thesis → Submit. A "Declared" banner confirms the
   mandate is anchored to the CUO's own KEL — no send happens here (§ design: a
   mandate is watched, never handed over).
6. **Actuary watches, then attests.** Pair the actuary with the CUO (Settings → Add
   Peer, using the CUO's exported peer blob, re-exported *after* the declare so its
   KEL carries the anchoring event). The Actuarial page's observed-mandates list
   fills in **by itself** — no admit action, nothing was sent to the actuary. Select
   the mandate, point "Parse Directory" at a real `ipd-parse` output tree (see
   "Before you start"), Load Parse, confirm the manifest SAID and workbook digest
   shown as evidence (never a rate table — no HOA surface renders one), then Attest.
7. **Designer receives, then assembles.** Pair the designer with the actuary. The
   actuary grants the freshly-attested `rate_program_attestation` to the designer
   (Issued Credentials → Grant, same mechanic as admin's role grants) — the designer
   Admits it from Notifications. The Received Rate Programs table shows the row (with
   the mandate shown as an edge, not a restated attribute); select it and click
   Assemble. The resulting bundle's SAID is the evidence — there is no publish
   action and no completeness indicator in this slice (out of scope by design).
8. **Revoke, and watch the surface disappear.** Admin revokes the CUO's `cuo_role`
   credential (Issued Credentials → Revoke) and delivers the revocation (send, or a
   fresh peer message if already paired). Within `GateRecheckDoer`'s ~2-second poll
   tock, the CUO's Underwriting entry and page vanish **without restarting the app** —
   confirm this is what you see, not a restart-triggered re-evaluation. Confirm a
   sibling gated role on the same identity (if granted) is untouched — revocation
   removes exactly the revoked surface.

## What to judge, since a test cannot

- Does the CUO's form read like a *declaration* (not a generic data-entry form)?
- Does the actuary's list make the *watch* legible — is it obvious the mandate arrived
  by observation, not by being handed over?
- Does the designer's table make the mandate *link* (the edge) obvious, not buried?
- Does the revocation read as a surface *disappearing*, cleanly, within the ~2s
  window — not a flicker, not a stale entry that still responds to clicks?

Record the outcome honestly, including anything that only worked after a fix — prior
live demos of this stack each surfaced integration bugs no suite had caught; treat
each one as a finding, not a detour.
