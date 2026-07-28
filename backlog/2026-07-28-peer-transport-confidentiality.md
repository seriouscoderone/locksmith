# Peer transport has no confidentiality — decide it before "any network" ships

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** medium (decision, not a defect — but it must be a *recorded* decision)

## What we saw

Peer mode writes framed CESR onto a raw TCP socket with no transport encryption
(`peer/sending.py:69` — `socket.create_connection` + `sendall`). That was a deliberate choice:
KERI is silent on transport encryption, so the position was to use CESR payload encryption or
layer plain TLS orthogonally rather than bake it in (memory `feedback_tls_dropped`).

That position is defensible while direct mode is a trusted-LAN fast path. It stops being
defensible the moment the stated requirement is *"works on any network, I want it open"* —
which is now the requirement.

## What is and isn't at risk

**Not at risk.** Every exn is signed, and ACDC/KEL verification is end-to-end. A hostile network
observer or relay **cannot** forge, alter, or authorize anything. The worst a malicious mailbox
does is fail to deliver (availability) or observe metadata — who talks to whom, when, message
sizes. That is the whole point of KERI's untrusted-infrastructure posture and it holds here.

**At risk.** Confidentiality of contents. A role application and the resulting role credential are
employee data. On a plaintext hop — a LAN, or a relay that terminates and stores plaintext — the
observer or operator reads them.

## The options

| Option | Protects against | Cost |
|---|---|---|
| Overlay network (WireGuard/Tailscale) | On-path observers | Enrollment; nothing in-app; **no** protection from the relay if one is used later |
| Mailbox over HTTPS | On-path observers | Relay still sees plaintext at rest — mitigated if you operate it (keri.host is ours) |
| CESR payload encryption | On-path **and** relay | Real work; the KERI-native answer; key management to design |
| Plain TLS on peer TCP | On-path observers | Cert distribution/trust for a P2P mesh is awkward — this is why it was dropped |

## The decision to make

Scope direct TCP explicitly to trusted networks (and *say so* in the docs and UI), or invest in
payload encryption before the flow is used for anything beyond internal role placeholders. The
current Usurance role credentials are deliberately low-stakes ("placeholder persona surface" per
the EGF), so there is room to decide deliberately — but the decision should be written down
rather than inherited by default.

Recommend revisiting when `usurance-internal` stops being `"openness": "closed"`, or when any
real (non-placeholder) attribute enters a role credential — whichever comes first.

## Evidence / references

- `peer/sending.py:69` · memory `feedback_tls_dropped`
- `brands/usurance/egf/…EPyySfoR….json` (`"openness": "closed"`, roles marked placeholder)
- Sibling: `2026-07-28-network-independent-delivery-mailbox-role.md`
