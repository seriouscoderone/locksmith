"""Regression-guard for the peer.send.* structured log lines that the UI
channel badge derives from."""
import logging

from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.peer.sending import SendOutcome, peer_send


def test_outbound_badge_records_outcome(baser, caplog):
    """peer_send logs peer.send.peer_ok or peer.send.fallback_mailbox.
    The badge surfaced in UI is derived from these structured log events."""
    al = PeerAllowlist(baser)
    al.add(PeerRecord(
        aid="EAID_BOB", label="Bob",
        endpoint_url="tcp://127.0.0.1:1",  # unreachable
        paired_at=datetime.now(timezone.utc).isoformat(),
    ))

    mailbox_calls = []
    with caplog.at_level(logging.INFO, logger="locksmith.peer.sending"):
        outcome = peer_send(
            allowlist=al,
            recipient_aid="EAID_BOB",
            exn_bytes=b"FAKE",
            mailbox_send=lambda aid, b: mailbox_calls.append((aid, b)) or True,
        )

    assert outcome is SendOutcome.FALLBACK
    assert any("peer.send.fallback_mailbox" in r.message for r in caplog.records)


def test_send_outcome_values_match_badge_strings():
    """The SendOutcome.value strings are the badge text the UI renders."""
    assert SendOutcome.PEER.value == "peer"
    assert SendOutcome.MAILBOX.value == "mailbox"
    assert SendOutcome.FALLBACK.value == "peer→mailbox"
