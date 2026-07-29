# Peer endpoint is not a real EID — a vault-scoped socket signed as if it were the AID

**Status:** DONE (code) — one item outstanding, see below · **Raised:** 2026-07-28 · **Priority:** high (BE KERI NATIVE; blocks multi-route and mailbox unification)

## What we saw

Every peer endpoint Locksmith publishes collapses the endpoint identifier into the controller.
From the bundled Usurance OOBI:

```
/loc/scheme   {"eid":"EGjm-X1J…", "scheme":"tcp", "url":"tcp://127.0.0.1:5621"}
/end/role/add {"cid":"EGjm-X1J…", "role":"peer",  "eid":"EGjm-X1J…"}
```

`cid == eid == the AID`. That is hardcoded — `peer/publishing.py:91,96` always sends
`eid=hab.pre`, and `peer/exposure.py:40` reads back `(pre, Roles.peer, pre)`.

Meanwhile the thing actually being addressed is a **per-vault socket**: one listener, one port,
`db.peerSettings` keyed `("default",)`. Exposure and pairing are per-AID, but the address is a
property of the *vault*. So the signature asserts "AID X is reachable here" when the truth is
"the vault containing X is reachable here."

## Why this is the BE KERI NATIVE violation (and the instance coordinator is not)

Raised in discussion: should `InstanceCoordinator` (`core/instancing.py:102`) be KERI-native too?
No. Test: **is there a counterparty who must verify something?** Instance coordination arbitrates
an LMDB write lock between two processes of the *same controller, same machine, same keys* —
no counterparty, no identity claim, nothing to verify, and KERI has no primitive for it. Forcing
one would mean *inventing* a primitive, which inverts the law.

The endpoint is the opposite: a remote wallet must decide "is this really where AID X wants my
exn?" Counterparty exists ⇒ must be native. And it half-is.

`eid == cid` is not spec-illegal (a witness is an EID that controls itself), and for
1-vault-1-AID — every HOA install shipped so far — it is indistinguishable from correct. Nothing
forced the issue until multi-AID, multi-brand, and multi-route showed up. It predates the
directive.

**Supporting evidence that native is the well-trodden path:** keripy already does
`cid → ends[role] → eid → urls` resolution for the mailbox and witness roles
(`keripy/src/keri/app/forwarding.py:343-352`; `ends[role]` is `{eid: urls}`). Locksmith's peer
path is the only one that shortcuts it, reading `db.locs.get(keys=(aid, tcp))` directly.

## What going native buys

- **Multi-route becomes possible at all.** `db.locs` is keyed `(eid, scheme)` — one URL per
  scheme per EID. With `eid == cid` an AID can have exactly **one** tcp address, so
  "Tailscale *and* globally addressable" is structurally impossible today. See
  `2026-07-28-single-route-per-peer.md`.
- **Multi-AID vaults become expressible** instead of accidental: N CIDs authorize 1 EID, which
  is exactly the witness pattern.
- **Address rotates independently of identity** — a new laptop does not touch any AID's KEL.
- **Peer and mailbox become one abstraction.** A peer listener is an EID you host; a mailbox is
  an EID someone else hosts. Same shape, dispatch by role. Without this, mailbox support lands
  as a parallel special case and has to be unified later.

## Known counterpoint — decide it deliberately

A shared EID across AIDs in a vault is a **correlation handle**: anyone seeing two AIDs authorize
the same EID learns they are co-located. `eid == cid` is sometimes *deliberately* chosen for
unlinkability. `usurance-internal` is a closed employee ecosystem so the trade is probably
acceptable — but it should be an explicit decision recorded here, not inherited.

### DECISION (2026-07-28): accept the shared listener EID

**The unlinkability being given up does not currently exist.** Locksmith's listener is one
socket per vault — one port, `db.peerSettings` keyed `("default",)`. Under the old shape two
AIDs in one vault published two different EIDs pointing at *the same* `tcp://host:port`; the
address already linked them. `eid == cid` made the model *look* privacy-preserving while
leaking exactly as much, which is worse than leaking visibly, because it discourages anyone
from fixing the transport. So this is not a privacy regression — it is the same exposure,
now stated honestly in the endpoint model.

Real unlinkability needs distinct *addresses* per AID (separate ports, interfaces, or overlay
identities), which is a transport change rather than an EID-naming one. The design keeps that
reachable: `ensure_listener_hab` takes an alias, so an unlinkable mode is "one listener EID
and one port per AID" with no change to the endpoint model.

Scope: `usurance-internal` is a closed employee ecosystem, where co-location of one
employee's AIDs is not a threat. If a future brand serves mutually anonymous counterparties,
the per-AID-listener variant is the answer, and it should be an explicit brand posture rather
than a silent default.

Full reasoning: `docs/superpowers/specs/2026-07-28-peer-endpoint-real-eid-design.md`.

## The actual work

1. Mint/persist an EID for the vault's peer listener; publish `/loc/scheme` under that EID and
   `/end/role/add` with `cid=<each exposed AID>, eid=<listener EID>`.
2. Change the *read* side to resolve natively: `cid → ends[peer] → eid → locs[eid]`. Call sites:
   `peer/sending.py`, `core/direct_transport.py:111`, `ui/vault/peers/add_dialog.py:333`,
   `peer/exposure.py:40`.
3. **Migration for already-shipped vaults** — this is the part that matters more than the new
   code. Existing installs have `eid == cid` records; they must keep working, and a re-publish
   must not orphan a peer that paired under the old shape.
4. Land **before** re-baking bundled OOBI artifacts (see the sequencing note in
   `2026-07-28-hoa-direct-endpoint-loopback-only.md`) to avoid baking twice.

## Status 2026-07-28 — items 1-3 DONE, item 4 OUTSTANDING (needs the user)

Items 1-3 are implemented (`peer/listener_eid.py`, `peer/resolution.py`, publish-side
migration + recency ordering). Seven read call sites converted, not the four listed above:
`generate_oobi(role="peer")`, `serviceaid_bridge._inband_oobi_msgs`, and
`peer/shim.py::_first_contact_accepted` were also reading `db.locs` directly. `peer/sending.py`
was deliberately **not** converted — it dials a cached `PeerRecord.endpoint_url` for a remote
AID, which is pairing state rather than a resolution of our own KEL; that is the subject of
`2026-07-28-single-route-per-peer.md`.

**OUTSTANDING: re-bake `brands/usurance/egf/oobis/EGjm-X1JMz-….cesr` under the new shape.**
Not blocking — the shipped artifact carries `eid == cid` and native resolution reads it
unchanged (pinned by
`tests/core/test_brand_oobi_endpoints.py::test_bundled_oobi_still_pairs_under_native_resolution`,
and verified by hand: `--inspect-only` on the committed artifact returns
`tcp://192.168.1.162:5621`). The re-bake requires re-signing in the usurance-custody vault,
so **only the user can produce it**; `scripts/bake_authority_oobi.py` accepts either shape
and is ready. Note the endpoint is also still a LAN address, so the re-bake should wait until
the intended reachable address is settled.

## Findings raised while doing this work

- `2026-07-28-derived-aids-collide-across-vaults.md` — two vaults with the same passcode minted
  the SAME listener EID (fixed here with a random salt; needs a wider `makeHab` audit).
- `2026-07-28-endrole-cut-does-not-propagate.md` — `replyEndRole` cannot export a cut, so
  endpoint retirement (and peer-mode revocation) never reaches an already-paired peer.
- `2026-07-28-loc-without-end-authorization.md` — reading `db.locs` without its authorization
  admitted an unvouched address, including at the open-inbound first-contact gate.
- `2026-07-28-modal-dialog-starves-dev-control-socket.md` and
  `2026-07-28-harness-cannot-read-custom-item-widget-rows.md` — test diagnosability.

## Evidence / references

- `peer/publishing.py:91,96` · `peer/exposure.py:40` · `core/instancing.py:102`
- `keripy/src/keri/app/forwarding.py:343-352` (native resolution, already used for mailbox/witness)
- Siblings: `2026-07-28-single-route-per-peer.md`,
  `2026-07-28-network-independent-delivery-mailbox-role.md`
- Law: `../ugard/docs/canon/be-keri-native.md`; memory `feedback_be_keri_native`
