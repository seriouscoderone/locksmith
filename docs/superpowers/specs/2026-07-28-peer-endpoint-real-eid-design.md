# Peer endpoints get a real EID — design

**Date:** 2026-07-28 · **Backlog:** `backlog/2026-07-28-peer-endpoint-not-a-real-eid.md`
**Law:** BE KERI NATIVE (`CLAUDE.md`, `../ugard/docs/canon/be-keri-native.md`)

## Problem

Every peer endpoint Locksmith publishes collapses the endpoint identifier into the
controller: `/loc/scheme` carries `eid = hab.pre` and `/end/role/add` carries
`cid == eid == hab.pre` (`peer/publishing.py:91,96`). The read side matches, going
straight to `db.locs.get(keys=(aid, tcp))` and skipping the authorization record
entirely (`peer/exposure.py:40`, `core/direct_transport.py:134`,
`ui/vault/peers/add_dialog.py:333`).

What is actually being addressed is a **per-vault socket** — one listener, one port,
`db.peerSettings` keyed `("default",)`. So the signed rpy asserts "AID X is reachable
here" when the truth is "the vault containing X is reachable here."

keripy already does the native `cid → ends[role] → eid → locs[eid]` resolution for the
mailbox and witness roles (`keripy/src/keri/app/forwarding.py:340-352`,
`habbing.endsFor`/`fetchRoleUrls`). Locksmith's peer path is the only one that shortcuts
it.

## Non-target

`core/instancing.py` `InstanceCoordinator` is correctly **not** KERI. It arbitrates an
LMDB write lock between two processes of the same controller, same machine, same keys.
There is no counterparty and nothing to verify, so there is no KERI primitive for it and
forcing one would mean inventing one. Untouched by this work.

## Findings that shaped the design (spiked against real keripy)

Two facts came out of spiking before design, and both narrowed the option space to one
real choice.

**The listener EID must be non-transferable.** `processReplyLocScheme`
(`keripy/src/keri/core/eventing.py:5148`) sets `aid = eid` and BADA's `acceptReply`
rejects any signature not from that `aid`. So the `/loc/scheme` rpy has to be signed by
the EID itself, not by the controller. Meanwhile `replyEndRole` does **not** replay the
EID's KEL — it emits only `replay(cid)` plus each EID's loc/end records. A transferable
EID would therefore ship indexed signatures the importer has no key state to verify,
and the endpoint would silently fail to land. A non-transferable prefix carries its
public key *in* the prefix, so the attached cigar verifies standalone. This is exactly
why witnesses are non-transferable, and it makes the choice structural rather than
stylistic.

**Reading `locs` without checking `ends` can pair an unauthorized address.** In the
corruption spike, damage in the last third of a stream landed the `/loc/scheme` while
the `/end/role/add` was dropped. Today's read side (`locs` only) returns that URL as a
success — an endpoint nobody authorized. Native resolution requires the authorization
record first, so this stops being reachable. Filed as
`backlog/2026-07-28-loc-without-end-authorization.md`.

## Design

### 1. The listener EID

One non-transferable hab per vault, in the `peer` namespace:

```python
PEER_NS = "peer"
PEER_LISTENER_ALIAS = "peer-listener"
ensure_listener_hab(hby, alias=PEER_LISTENER_ALIAS)   # idempotent
```

- `transferable=False` → `B…` prefix, cigar-signed replies (required, see above).
- **Minted with a fresh random salt, not the Habery's.** Found the hard way: salty key
  creation derives from `(salt, stem)`, the Habery's salt follows the passcode, and the
  stem comes from the alias — so two vaults opened with the same passcode minted the
  *identical* listener prefix. Because `db.locs` is keyed `(eid, scheme)`, two different
  sockets then contended for one location record and BADA's datestamp picked a winner: a
  peer paired with both resolved one address for both and sent to the wrong vault,
  reporting success. Caught by the two-wallet integration test, where the sender dialed
  its own port. The keys still persist in the keystore, so the EID remains stable across
  restarts — it just is not derivable. Wider audit filed as
  `backlog/2026-07-28-derived-aids-collide-across-vaults.md`, because the same collision
  applies to any alias-derived hab, including transferable user identities where it would
  be duplicity rather than a mixed-up address.
- `ns="peer"` keeps it out of the Identifiers page, which filters `ns != ""`
  (`ui/vault/identifiers/list.py:106`), and out of the group surfaces. Precedent: the
  turret's `ns="settings"` hab (`core/vaulting.py:77`).
- `version=Vrsn_1_0` — the TRANSITIONAL v1-hold every other Locksmith hab is pinned to.
- The keystore is the single source of truth. No `listener_eid` field on
  `PeerModeSettings`: a cached copy of a keystore fact is a staleness bug waiting to
  happen, and `habByName` is cheap.
- `alias` is a parameter, not a constant baked into callers, so the multi-route
  follow-on (`backlog/2026-07-28-single-route-per-peer.md`) can mint a second listener
  EID without touching this function's contract.

### 2. Publish side

`PublishPeerRoleDoer` with `allow=True` emits:

| rpy | signer | payload |
|---|---|---|
| `/loc/scheme` | listener hab | `eid=<listener>, scheme=tcp, url=<url>` |
| `/end/role/add` | controller hab | `cid=<aid>, role=peer, eid=<listener>` |

With `allow=False` it emits `/end/role/cut` for `(cid, peer, listener)` only. It no
longer nullifies the location, and that is a deliberate change: the location now
belongs to the vault's shared listener, so nullifying it because *one* AID stopped
exposing would silently break every other exposed AID in the same vault. The cut is the
authorization statement, and the read side honours it — a cut end record means the AID
is not reachable regardless of what `locs` still holds.

### 3. Read side — one resolver, four call sites

New `src/locksmith/peer/resolution.py`:

```python
def resolve_peer_endpoints(db, cid, scheme=tcp) -> list[tuple[str, str]]
def resolve_peer_endpoint(db, cid, scheme=tcp) -> str | None      # first, or None
def peer_role_eids(db, cid) -> list[str]
```

`resolve_peer_endpoints` walks `db.ends.getTopItemIter(keys=(cid, Roles.peer))`, keeps
records where `enabled or allowed`, looks up `db.locs.get(keys=(eid, scheme))`, and
returns the `(eid, url)` pairs with a non-empty url. It returns a **list** so the
multi-route follow-on has nothing to unwind; today's callers take the first.

Call sites converted — the four the backlog entry listed (`peer/exposure.py:40`,
`core/direct_transport.py:134`, `ui/vault/peers/add_dialog.py:333`,
`peer/oobi_import.py`) plus three it did not:

- `core/habbing.py:944` `generate_oobi(role="peer")` hardcoded
  `/oobi/{hab.pre}/peer/{hab.pre}`; the final segment must name the listener EID, since
  the witness's OOBI handler filters by it.
- `core/serviceaid_bridge.py` `_inband_oobi_msgs` re-signed `eid=hab.pre` on every send,
  which would have **resurrected the legacy self-authorization the migration retires**.
  It now loads the already-published rpys back out of the db
  (`loadLocScheme`/`loadEndRole`) instead of minting new ones — which is also the only
  way to get a listener-signed `/loc/scheme` from a function that holds just the `hab`.
- `peer/shim.py` `_first_contact_accepted` — the open-inbound gate deciding whether to
  talk to a stranger. Its stated rule is "KEL verified AND published a reachable tcp
  loc-scheme", but reading `db.locs` directly meant the authorization half was never
  actually checked. This was the most consequential instance of the
  unauthorized-location hole.

`peer/sending.py` is deliberately **not** converted. It dials
`PeerRecord.endpoint_url`, which is a *pairing* record for a remote AID, not a
resolution of our own KEL. Rewriting it to resolve from `db.ends` would require the
remote's authorization records to be present for every send, which is a behavioural
change well beyond this task and is the actual subject of the multi-route entry.
`direct_transport` remains the thing that writes `endpoint_url` from native resolution.

### 4. Migration for already-shipped vaults

The load-bearing property: **the old shape is a degenerate case of the general one.**
An `eid == cid` install has `ends[(cid, peer, cid)]` and `locs[(cid, tcp)]`; native
resolution walks `ends` for `cid`, finds `eid = cid`, and resolves `locs[(cid, tcp)]`.
It works with no migration code and no version flag. That is the payoff for going
native rather than inventing a parallel lookup.

Three consequences, only one of which needs code:

1. **Reading old-shape records — free.** Includes the already-shipped Usurance bundled
   artifact: it still carries `eid == cid`, and native resolution reads it unchanged.
   Pinned by a test.
2. **Peers paired under the old shape — free.** Their `PeerRecord.endpoint_url` is
   untouched, and `peer_send` still dials it. When they upgrade and re-publish, the
   `direct_transport` re-pin path (extended by task 1) picks up the new address.
3. **Our own stale self-authorization — needs code.** A vault that previously published
   `eid == cid` still holds `ends[(cid, peer, cid)] allowed=True`. Re-publishing under
   the new shape would leave it advertising *two* endpoints, and a remote could resolve
   the stale one first. So when publishing `allow=True`, if a legacy
   `ends[(cid, peer, cid)]` record exists, also emit `/end/role/cut` for it and a
   nullifying empty-url `/loc/scheme` for `(cid, tcp)`. Conditional and one-time;
   harmless if it re-fires.

The mechanism is the one task 1 already proved against real keripy in
`tests/core/test_oobi_import.py::test_reparse_supersedes_a_changed_endpoint`: a
later-dated rpy supersedes what an install already learned (BADA). The migration tests
extend that file.

**But the cut does not travel, so ordering carries the migration.** `replyEndRole`
exports only *currently authorized* records (`habbing.py:2480-2483`, and `loadEndRole`
has the same guard), so a `/end/role/cut` is structurally unable to appear in an exported
OOBI. An install that learned the old endpoint keeps holding it and ends up with two
routes; the retirement above cleans up the publisher's own vault and its witnesses, and
nothing more. What makes the upgrade land anyway is preference order: `peer_role_eids`
sorts by the datestamp keripy recorded for each authorization (`db.eans` → `db.sdts`, the
same pair BADA compares in `acceptReply`), newest first, so the current address is the one
dialed and the retired one degrades to a fallback instead of shadowing it. LMDB key order
is by EID and bears no relation to recency, so the sort is doing real work.

This has a consequence past this task: **peer-mode revocation is not observable to an
already-paired counterparty.** Turning exposure off publishes a cut that no re-exported
blob can carry, while the counterparty dials a cached `PeerRecord.endpoint_url`. Local
enforcement (`PeerDoer`'s `is_destination_exposed`) is the real control. Filed as
`backlog/2026-07-28-endrole-cut-does-not-propagate.md`.

### 5. OOBI parse: damaged stream vs no peer role

Folding in `backlog/2026-07-28-oobi-parse-misleading-no-peer-role.md`.
`parse_oobi_cesr` currently reports `no_peer_role` — *"The peer may not have 'Expose
over peer mode' enabled"* — for byte corruption, sending the operator to toggle
settings on a machine that did nothing wrong. keripy's `Parser.parse` swallows
per-message framing errors, so a damaged stream desynchronizes and lands nothing
**without raising**.

Spiked behaviour, corrupting a known-good blob:

| damage | result |
|---|---|
| duplicate a char near the front | nothing lands, no exception |
| duplicate a char in the last third | KEL lands, rpys dropped |
| truncate to 60% | KEL lands, rpys dropped |

So the outcomes are ordered:

1. **Resolvable** → success. Checked first, which preserves idempotent re-parse: a
   second parse of a good blob changes nothing (BADA rejects the same date) but still
   resolves.
2. **Nothing landed at all** — no new kever, no change to `ends` or `locs` → new
   `damaged_stream` reason: the blob appears damaged in transit, re-copy the whole
   token.
3. **Otherwise** → `no_peer_role`, now truthful, with a second sentence naming transit
   damage as the other possibility (case 2 in the table above is genuinely ambiguous
   between "not exposed" and "damaged", and the message should not pretend otherwise).

"Nothing landed" is measured by snapshotting `(keys, value)` pairs of `ends` and `locs`
plus the kever key set — not counts, since a BADA supersede changes a value in place.
These stores hold a handful of records per vault.

## Correlation trade-off — DECISION: accept the shared listener EID

A single listener EID authorized by several of a vault's AIDs is a correlation handle:
anyone who sees two AIDs authorize the same EID learns they are co-located. `eid == cid`
is sometimes chosen deliberately for unlinkability, so this is a real question and the
backlog entry was right to demand it be decided rather than inherited.

**Decision: accept it as the default.** Recorded in the backlog entry and here.

The decisive argument is that the unlinkability being given up does not currently
exist. Locksmith's listener is one socket per vault — one port, `db.peerSettings` keyed
`("default",)`. Under the old shape, two AIDs in one vault published two different EIDs
pointing at *the same* `tcp://host:port`. The address already linked them. `eid == cid`
made the model look privacy-preserving while leaking exactly as much, which is worse
than leaking visibly, because it discourages anyone from fixing the transport.

Real unlinkability needs distinct *addresses* per AID — separate ports, interfaces, or
overlay identities — which is a transport change, not an EID-naming one. This design
keeps that reachable: `ensure_listener_hab` takes an alias, so an unlinkable mode is
"one listener EID and one port per AID" with no change to the endpoint model.

Scope: `usurance-internal` is a closed employee ecosystem. Co-location of one
employee's AIDs is not a threat there. Should a future brand serve mutually anonymous
counterparties, the per-AID-listener variant above is the answer, and it should be an
explicit brand posture rather than a silent default.

## Testing

- Publish side: real Habery. Listener minted, non-transferable, `ns="peer"`; both rpys
  land in `db.ends`/`db.locs` under the listener EID; the export/import round-trip
  resolves natively in a fresh Habery.
- Read side: each converted call site against both shapes, old and new.
- Migration: extends `tests/core/test_oobi_import.py` — legacy-shape blob still
  resolves; a new-shape re-publish supersedes; the legacy self-authorization is cut.
- Parse: byte-corruption regression (duplicate one char inside a couple of a known-good
  blob) asserting `damaged_stream`, not `no_peer_role`.
- The bundled Usurance artifact, still old-shape, must keep pairing.

## Not in this change

- The Usurance bundled artifact re-bake under the new shape. The `/loc/scheme` is signed
  in the usurance-custody vault, so **only the user can produce it**; fabricating a blob
  is not possible and a prior session corrupted one by retyping it (memory
  `feedback_never_retype_long_blobs`). `scripts/bake_authority_oobi.py` is updated to
  validate both shapes so it is ready when the user re-signs. The old artifact keeps
  working until then.
- Multi-route selection (`backlog/2026-07-28-single-route-per-peer.md`) — unblocked by
  this work, not implemented. Nothing here assumes one EID per AID or one route per
  `PeerRecord`.
