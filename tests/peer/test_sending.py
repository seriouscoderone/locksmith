import logging
import socket
from types import SimpleNamespace

from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.peer.sending import peer_send, SendOutcome


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _make_recipient(aid="EAID_BOB", url="tcp://127.0.0.1:5621"):
    return PeerRecord(aid=aid, label="Bob", endpoint_url=url,
                      paired_at=datetime.now(timezone.utc).isoformat())


def test_no_peer_record_falls_through_to_mailbox(baser):
    al = PeerAllowlist(baser)
    mailbox_calls = []

    def mailbox_send(recipient_aid, exn_bytes):
        mailbox_calls.append((recipient_aid, exn_bytes))
        return True

    outcome = peer_send(
        allowlist=al,
        recipient_aid="EAID_BOB",
        exn_bytes=b"FAKE-CESR",
        mailbox_send=mailbox_send,
    )

    assert outcome is SendOutcome.MAILBOX
    assert mailbox_calls == [("EAID_BOB", b"FAKE-CESR")]


def test_peer_endpoint_unreachable_falls_back_to_mailbox(baser, caplog):
    al = PeerAllowlist(baser)
    # Point at a port nothing is listening on
    bad_port = _free_port()
    al.add(_make_recipient(url=f"tcp://127.0.0.1:{bad_port}"))

    mailbox_calls = []

    def mailbox_send(recipient_aid, exn_bytes):
        mailbox_calls.append((recipient_aid, exn_bytes))
        return True

    with caplog.at_level(logging.INFO, logger="locksmith.peer.sending"):
        outcome = peer_send(
            allowlist=al,
            recipient_aid="EAID_BOB",
            exn_bytes=b"FAKE-CESR",
            mailbox_send=mailbox_send,
        )

    assert outcome is SendOutcome.FALLBACK
    assert mailbox_calls == [("EAID_BOB", b"FAKE-CESR")]
    assert any("peer.send.peer_failed" in r.message for r in caplog.records)
    assert any("peer.send.fallback_mailbox" in r.message for r in caplog.records)


def test_peer_endpoint_reachable_returns_peer_outcome(baser, caplog):
    al = PeerAllowlist(baser)
    port = _free_port()

    # Stand up a real listening socket that just accepts and discards
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)

    al.add(_make_recipient(url=f"tcp://127.0.0.1:{port}"))

    mailbox_calls = []

    def mailbox_send(recipient_aid, exn_bytes):
        mailbox_calls.append((recipient_aid, exn_bytes))
        return True

    try:
        with caplog.at_level(logging.INFO, logger="locksmith.peer.sending"):
            outcome = peer_send(
                allowlist=al,
                recipient_aid="EAID_BOB",
                exn_bytes=b"FAKE-CESR",
                mailbox_send=mailbox_send,
            )
    finally:
        server.close()

    assert outcome is SendOutcome.PEER
    assert mailbox_calls == []
    assert any("peer.send.peer_ok" in r.message for r in caplog.records)
