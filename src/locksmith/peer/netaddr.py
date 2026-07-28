"""What address to tell a peer to dial back on.

The peer listener binds ``0.0.0.0``, but the address it *advertises* — in
the ``/loc/scheme`` rpy that goes out in-band and in every exported peer
OOBI — has to be one a remote wallet can actually reach. A hardcoded
``127.0.0.1`` makes the counterparty dial its own loopback, which is the
one failure mode that looks exactly like "the other app isn't running".

Resolution order (``resolve_advertised_host``):

1. ``$LOCKSMITH_ADVERTISED_HOST`` — per-install escape hatch.
2. the brand's ``[peer] advertised_host`` — per-deployment pin.
3. auto-detection of the interface that owns the default route.
4. ``127.0.0.1``, loudly logged — same-machine dev still works, and a
   remote failure is at least explicable from the log.

There is deliberately no overlay-specific (Tailscale/WireGuard) code path:
an overlay interface is just an interface, and once one carries the default
route step 3 returns its address on its own. The overrides exist for the
ambiguous case — a host with both a LAN and an overlay address, where only
the operator knows which one the peers are on.
"""
from __future__ import annotations

import os
import socket

from keri import help

logger = help.ogler.getLogger(__name__)

ADVERTISED_HOST_ENV_VAR = "LOCKSMITH_ADVERTISED_HOST"

LOOPBACK = "127.0.0.1"

# Any of these advertised to a remote peer is a dead endpoint, so they are
# rejected as override values rather than shadowing a usable detection.
_UNUSABLE_HOSTS = frozenset({"", "0.0.0.0", "::", "*"})

# Route-selection probe target. A UDP "connect" sends no packets — it only
# asks the kernel which local address a datagram to this destination would
# leave from — so this address is never contacted and need not exist. It
# just has to be off-link so the answer is the default route's interface.
_ROUTE_PROBE_TARGET = ("8.8.8.8", 53)


def detect_primary_host() -> str | None:
    """Local address of the interface that owns the default route, or None.

    Returns None when the host has no route out (airplane mode, isolated
    CI container) or when the kernel hands back something unusable.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(_ROUTE_PROBE_TARGET)
        host = sock.getsockname()[0]
    except OSError as e:
        logger.debug(f"peer.netaddr.detect_failed err={e}")
        return None
    finally:
        sock.close()
    if not host or host in _UNUSABLE_HOSTS or host.startswith("127."):
        return None
    return host


def _brand_advertised_host() -> str:
    """The active brand's ``[peer] advertised_host``, or "" if unset."""
    from locksmith.core.branding import brand
    return (brand().peer_advertised_host or "").strip()


def _usable(host: str | None) -> str:
    host = (host or "").strip()
    return "" if host in _UNUSABLE_HOSTS else host


def resolve_advertised_host() -> str:
    """The address to advertise to peers. Never empty; see module docstring."""
    env = _usable(os.environ.get(ADVERTISED_HOST_ENV_VAR))
    if env:
        logger.info(f"peer.netaddr.advertised host={env} source=env")
        return env

    pinned = _usable(_brand_advertised_host())
    if pinned:
        logger.info(f"peer.netaddr.advertised host={pinned} source=brand")
        return pinned

    detected = _usable(detect_primary_host())
    if detected:
        logger.info(f"peer.netaddr.advertised host={detected} source=detected")
        return detected

    logger.warning(
        "peer.netaddr.advertised host=127.0.0.1 source=fallback — no routable "
        f"interface was detected and no override is set. Peers on other "
        f"machines will NOT be able to reach this wallet; set "
        f"${ADVERTISED_HOST_ENV_VAR} to a reachable address."
    )
    return LOOPBACK
