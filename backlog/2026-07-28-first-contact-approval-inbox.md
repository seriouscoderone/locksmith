# `open_inbound` is all-or-nothing — an authority has no way to approve one requester

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** high (hardening — **not** a live-test blocker)

> **Correction (2026-07-28):** first raised as "required for the first live role request." That was
> overstated. An authority running vanilla Locksmith can simply tick `open_inbound` in vault settings
> today, which is enough to prove the flow end to end. This item is what makes that posture *safe and
> sane* for real use — it is not on the critical path to the first live test.

## What we saw

For a co-worker's role request to reach the usurance-custody admin, the admin's shim must accept
an exn from an AID it has never seen. Gate 1 is the paired-peers allowlist
(`peer/shim.py:57`); an unknown sender is dropped as `peer.gate.sender_rejected` unless
`open_inbound` is set (`peer/shim.py:76-93`).

So today the admin's only choices are:

- **`open_inbound` off** — nothing works; every first contact is silently dropped.
- **`open_inbound` on** — accept from *anyone* who can verify a KEL and publish a tcp loc, and
  auto-register them in the allowlist + contacts (`core/vaulting.py:313`).

There is no middle. And the requester side cannot help: an HOA build has no peer-OOBI blob export
(`ui/vault/hoa_page.py:38` peels the identifier page), so the admin cannot pre-pair a co-worker
out-of-band even if they want to.

Worth noting the existing gate is not weak — first contact already requires a **verified KEL in
kevers** plus a published tcp loc, both arriving in-band with the request
(`core/serviceaid_bridge.py:144`). The problem is that acceptance is automatic and permanent, not
that it is unauthenticated.

## The actual work

1. **Pending first-contact inbox.** An unknown, KEL-verified sender lands in a pending queue
   rather than the allowlist. The admin sees who (AID, any self-asserted label), what they asked
   for, and when — then accepts or denies. Acceptance is what writes the `PeerRecord`.
2. Deny should be durable (do not re-prompt on every retry) and reversible.
3. Keep `open_inbound` as an explicit "auto-accept" posture for demo/dev, but stop making it the
   only path to a working flow.
4. **Peer-OOBI blob export in HOA builds** so out-of-band pre-pairing is possible at all —
   the mechanism exists (`peer/cesr_blob.py`, consumed by `ui/vault/peers/add_dialog.py:181`),
   it is just unreachable behind the peel.

## Evidence / references

- `peer/shim.py:57,76-93` · `core/vaulting.py:313` (`_register_first_contact_peer`)
- `core/serviceaid_bridge.py:144` (`_inband_oobi_msgs` — what a first contact actually carries)
- `ui/vault/hoa_page.py:38` (the peel that removes the export affordance)
- Sibling: `2026-07-28-admin-approve-issues-and-grants.md` (the natural place to put Accept)
