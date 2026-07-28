# Approving a role request is a 10-click manual ceremony on the admin side

**Status:** backlog · **Raised:** 2026-07-28 · **Priority:** medium (UX; the requester side is 2 clicks, this is the asymmetry)

## What we saw

Walking the end-to-end Usurance role-request flow from both sides:

- **Requester:** install → launch (auto-bootstrap, no prompts) → click **Request** → wait → held.
  Two clicks, nothing to understand, no AID/OOBI/address ever surfaced. Genuinely good.
- **Admin:** notification *"New credential application"* → then the stock Locksmith flow —
  Credentials → Issue → pick schema → pick recipient → fill attributes → Issue → find the issued
  credential → Grant → pick recipient → send.

Roughly 8–10 clicks across two dialogs, per request, with the recipient AID selected by hand from
a dropdown. Fine for a handful. A grind at ten, and a live opportunity to grant the wrong
recipient.

This is pure asymmetry, not missing information: the inbound `/ipex/apply` **already carries
everything needed** — the schema SAID and the requesting AID
(`keri_serviceaid.providers.frame_apply_for`, enumerated by `list_sent_applies` on the sender
side). Nothing has to be re-selected.

## The actual work

1. **Approve action on the request notification** that issues the role credential to the
   requesting AID and grants it, in one confirmed step, with schema + recipient pre-resolved from
   the apply exn. Show what will be issued to whom before committing — this is an
   authority-granting action, so it wants a confirmation, just not a re-entry.
2. **Deny/spurn** as a first-class sibling (IPEX has `/ipex/spurn`; the notification formatter
   already renders it — `ui/vault/notifications/list.py:355`).
3. Fold in the first-contact accept from
   `2026-07-28-first-contact-approval-inbox.md` so a new requester is one review, not two.
4. Surface delivery outcome on the same card (the channel is already reported —
   `PeerAwarePoster.last_outcome`), so the admin knows whether the grant actually landed.

## Prerequisite worth stating

The admin vault must have the role schemas loaded and a registry present before any of this can
issue. That is currently manual setup with no guidance — a first-run check ("this authority is
missing schema X") would prevent a confusing mid-approval failure.

## Evidence / references

- `ui/vault/notifications/list.py:355-358` (apply/spurn already formatted)
- `core/serviceaid_bridge.py` (`ServiceaidIssueDoer`, `ServiceaidGrantDoer` — the two halves to
  compose)
- `tests/integration/test_multi_role_e2e.py` (pins the credential-gated role surface the
  requester sees on success)
- Sibling: `2026-07-28-first-contact-approval-inbox.md`
