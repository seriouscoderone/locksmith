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


#: How long to wait for a peer's reply before giving up on this round. A watch
#: is a background loop -- a peer that is slow this tick is asked again next
#: tick, so waiting longer buys nothing and costs a blocked thread.
REPLY_READ_TIMEOUT_SECONDS = 2.0


def peer_request(allowlist, recipient_aid: str, raw: bytes,
                 *, endpoint_url: str | None = None,
                 read_timeout: float = REPLY_READ_TIMEOUT_SECONDS) -> bytes:
    """Send `raw` to a paired peer and RETURN ITS REPLY bytes.

    Deliberately NOT part of `peer_send`. Every other outbound message on this
    transport is genuinely fire-and-forget, and `peer_send` closes the socket
    the instant the write completes -- correct for a grant, fatal for a query.
    The Reactant answers a `qry`/`pro` on the same connection
    (`sendMessage` -> `remoter.tx`, logged "chit or receipt or replay"), so the
    reply is already being written; it was simply going into a socket the
    asker had hung up on. Measured live: 459-byte replays sent every 5s, zero
    of them ever read.

    PURE SOCKET I/O, returning bytes and touching no KERI state, so a caller
    may run it OFF the GUI thread. That matters: this blocks for up to
    `read_timeout`, and the hio doer loop that drives the watch also drives the
    UI. Parsing the returned bytes belongs on the owning thread -- see
    `keri_serviceaid.providers.peer_sync.ingest_response`.

    Returns b"" on any failure (no peer record, bad URL, unreachable, timeout
    with nothing read). There is no mailbox fallback: a mailbox cannot answer
    a query, and the next tick will ask again.
    """
    # `endpoint_url` lets a caller resolve the peer record on ITS OWN thread and
    # hand this function nothing but a URL -- so a GUI can run the blocking part
    # in a worker without ever touching LMDB off the thread that owns it.
    url = endpoint_url
    if url is None:
        record = allowlist.get(recipient_aid)
        url = record.endpoint_url if record is not None else None
    if not url:
        return b""
    try:
        host, port = _split_tcp_url(url)
    except ValueError:
        return b""

    chunks = []
    try:
        with socket.create_connection((host, port),
                                      timeout=CONNECT_TIMEOUT_SECONDS) as sock:
            sock.sendall(raw)
            # The responder needs no EOF to act: its Parser is framed and each
            # message carries its own size in `v`. So do NOT half-close here --
            # shutdown(SHUT_WR) risks the hio Remoter treating the FIN as a
            # closed connection and tearing down before it replies.
            sock.settimeout(read_timeout)
            while True:
                try:
                    buf = sock.recv(65536)
                except (socket.timeout, TimeoutError):
                    break           # answered what it was going to answer
                if not buf:
                    break           # peer closed
                chunks.append(buf)
    except (OSError, socket.timeout) as e:
        logger.debug(f"peer.request.failed recipient={recipient_aid} err={e}")
        return b""

    reply = b"".join(chunks)
    logger.debug(
        f"peer.request.reply recipient={recipient_aid} sent={len(raw)} got={len(reply)}"
    )
    return reply
