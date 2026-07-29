# The Windows MSI registers no inbound firewall rule — direct peer mode is dead on Windows by default

**Status:** backlog · **Raised:** 2026-07-29 · **Priority:** low-medium (packaging; PUBLISHER-agent territory; mailbox makes it non-blocking)

## What we saw

First live test: Windows Defender Firewall silently drops unsolicited inbound TCP to the HOA's
peer listener — the app has no firewall exception, and the WiX MSI does not create one. Even
with routable networking (bridged VM, real LAN PC), the direct return leg cannot work on a
default Windows install. Outbound is unaffected (the apply leg worked from the VM).

## The actual work

1. Add a WiX `FirewallException` for the app executable (WixFirewallExtension) scoped to
   private/domain profiles, so LAN peer mode works out of the box on Windows.
2. Decide posture deliberately: an inbound exception is a real security surface — the peel-only
   HOA build arguably should ship it (its whole flow needs it), while stock Locksmith could
   leave it to the user. Brand-conditional packaging fits the existing per-brand WiX rendering.
3. This is a fast-path nicety once the mailbox role lands
   (`2026-07-28-network-independent-delivery-mailbox-role.md`) — never a substitute for it:
   NAT (the Parallels case) defeats a firewall rule anyway.

## Evidence / references

- Live test 2026-07-29: VM→Mac apply delivered; Mac→VM grant blocked (NAT + firewall).
- `packaging/wix/` (brand-rendered WiX sources) — route to the PUBLISHER agent alongside its
  current WiX brand-leak work.
