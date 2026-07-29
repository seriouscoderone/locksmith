"""Outbound channel selector with auto-fallback to mailbox.

Per spec §3b: if the recipient has a PeerRecord with a reachable
endpoint, write the exn over TCP. Otherwise (or on connect failure)
fall back to the mailbox path.
"""
from __future__ import annotations

import enum
import socket
from typing import Callable
from urllib.parse import urlparse

from keri import help

from locksmith.peer.allowlist import PeerAllowlist

logger = help.ogler.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 3.0


class SendOutcome(enum.Enum):
    PEER = "peer"
    MAILBOX = "mailbox"
    FALLBACK = "peer→mailbox"


def peer_send(
    allowlist: PeerAllowlist,
    recipient_aid: str,
    exn_bytes: bytes,
    mailbox_send: Callable[[str, bytes], bool],
    *,
    keridb=None,
) -> SendOutcome:
    """Send `exn_bytes` to `recipient_aid` over peer or mailbox.

    Args:
        allowlist: read access to PeerRecords for endpoint lookup.
        recipient_aid: destination AID.
        exn_bytes: framed CESR bytes ready to write.
        mailbox_send: callable that takes (aid, bytes) and returns True
            on successful enqueue to the mailbox path.
        keridb: the keripy Baser holding ends/locs. When provided, the
            recipient's cached route is re-resolved through
            ``peer/resolution.py`` before dialing, so a peer that moved
            (newer signed /loc/scheme) is dialed at its current address
            instead of the one cached at pairing time. None keeps the
            legacy dial-the-cache behavior.

    Returns:
        SendOutcome describing the channel actually used.
    """
    if keridb is not None:
        record = allowlist.refresh_route(keridb, recipient_aid)
    else:
        record = allowlist.get(recipient_aid)
    if record is None or not record.endpoint_url:
        logger.info(
            f"peer.send.attempt recipient={recipient_aid} channel=mailbox reason=no_peer_record"
        )
        mailbox_send(recipient_aid, exn_bytes)
        return SendOutcome.MAILBOX

    logger.info(
        f"peer.send.attempt recipient={recipient_aid} channel=peer endpoint={record.endpoint_url}"
    )
    try:
        host, port = _split_tcp_url(record.endpoint_url)
    except ValueError as e:
        logger.warning(
            f"peer.send.peer_failed recipient={recipient_aid} reason=bad_url url={record.endpoint_url} err={e}"
        )
        mailbox_send(recipient_aid, exn_bytes)
        logger.info(f"peer.send.fallback_mailbox recipient={recipient_aid}")
        return SendOutcome.FALLBACK

    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_SECONDS) as sock:
            sock.sendall(exn_bytes)
    except (OSError, socket.timeout) as e:
        logger.warning(
            f"peer.send.peer_failed recipient={recipient_aid} endpoint={record.endpoint_url} err={e}"
        )
        mailbox_send(recipient_aid, exn_bytes)
        logger.info(f"peer.send.fallback_mailbox recipient={recipient_aid}")
        return SendOutcome.FALLBACK

    logger.info(
        f"peer.send.peer_ok recipient={recipient_aid} endpoint={record.endpoint_url} bytes={len(exn_bytes)}"
    )
    return SendOutcome.PEER


def _split_tcp_url(url: str) -> tuple[str, int]:
    up = urlparse(url)
    if up.scheme != "tcp":
        raise ValueError(f"expected tcp:// scheme, got {up.scheme!r}")
    if not up.hostname or not up.port:
        raise ValueError(f"missing host or port in {url!r}")
    return up.hostname, up.port
