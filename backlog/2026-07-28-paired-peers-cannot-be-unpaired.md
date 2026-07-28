# Paired peers cannot be unpaired — the allowlist only grows

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** medium (fold into the first-contact inbox work — same management surface)

## What we saw

Two dead test records in the usurance-custody allowlist (`tcp://127.0.0.1:5622`) are probed by
the health monitor every ~60s (`refused` each time) and render as permanent red rows in the
settings peer list. Going to remove them: **no affordance exists.**

- The settings peer section (`ui/vault/settings/peer_section.py`) lists paired peers with health
  dots and offers "Pair new peer" — no remove, no context menu.
- `PairedPeersPage.unpair()` exists (`ui/vault/peers/list.py:54`) but nothing calls it, and the
  page is registered nowhere — instantiated only by tests. Dead code.
- `PeerAllowlist.remove()` (`peer/allowlist.py:28`) works; it simply has no UI caller.

Records enter three ways — Add-Peer dialog, HOA bundled-authority auto-pairing, and
`open_inbound` first-contact auto-registration (`core/vaulting.py:313`) — and exit zero ways. The
first live role-request test will auto-register the requester's record on the admin side, and
every requester DHCP change mints another stale row. The list is monotonic.

## The actual work

1. Unpair action on the settings peer list rows (calls `PeerAllowlist.remove`; also drop the
   `db.peerHealth` row so a re-pair starts clean).
2. Decide `PairedPeersPage`'s fate: register it or delete it — an unregistered page with an
   uncalled `unpair()` is a trap for the next reader.
3. Compose with `2026-07-28-first-contact-approval-inbox.md`: its "deny must be durable and
   reversible" requirement needs this same management surface — pending / accepted / denied
   peers belong on one page with consistent actions.

## Evidence / references

- `ui/vault/settings/peer_section.py` (no remove affordance) · `ui/vault/peers/list.py:54`
  (dead `unpair`) · `peer/allowlist.py:28` · `core/vaulting.py:313` (auto-registration)
- Observed: archived session "Fix HOA loopback-only peer endpoint" (2026-07-28) — health monitor
  probing two dead 127.0.0.1:5622 records in usurance-custody.
- Sibling: `2026-07-28-first-contact-approval-inbox.md`
