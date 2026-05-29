"""Reachability self-test for the peer-mode listener.

After Save & restart on the settings card, dial out from the local
process to the advertised host:port and confirm we can actually reach
what we just told peers to expect. The check runs from the same host
that just started the listener, so it primarily catches:

  - Listener didn't actually bind (refused)
  - Advertised host is wrong / unreachable on this network (timeout)
  - Advertised host is a name that doesn't resolve (dns_failure)
  - User left the advertised field empty / set it to 0.0.0.0 which
    means nothing to a remote (invalid_host)

It does NOT prove a remote peer on a different machine can reach us —
NAT loopback, asymmetric firewall rules, and split-horizon DNS can all
let this test pass while a real peer still fails. The check exists to
surface obvious misconfiguration at config-time, not to certify
reachability for all callers.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass

from keri import help

logger = help.ogler.getLogger(__name__)


@dataclass(frozen=True)
class ReachabilityResult:
    ok: bool
    reason: str           # machine-stable: ok | refused | timeout | unreachable | dns_failure | invalid_host | other
    message: str          # human-readable, surfaced verbatim in the UI

    def __bool__(self) -> bool:
        return self.ok


def check_reachable(host: str, port: int, timeout: float = 2.0) -> ReachabilityResult:
    """Open a TCP connection to host:port and report what happened.

    Closes the connection immediately on success — this is a probe, not
    a sustained client. Returns a ReachabilityResult; never raises.
    """
    if not host or host in ("0.0.0.0", "::", ""):
        return ReachabilityResult(
            ok=False,
            reason="invalid_host",
            message=(
                "Advertised host is empty or a wildcard address. Set it to "
                "a routable address (LAN IP, public IP, or hostname)."
            ),
        )

    try:
        with socket.create_connection((host, port), timeout=timeout):
            logger.info(f"peer.reachability.ok host={host} port={port}")
            return ReachabilityResult(
                ok=True, reason="ok",
                message=f"{host}:{port} is reachable from this machine.",
            )
    except socket.gaierror as e:
        logger.info(f"peer.reachability.dns_failure host={host} err={e}")
        return ReachabilityResult(
            ok=False, reason="dns_failure",
            message=(
                f"Couldn't resolve '{host}'. Check the advertised hostname "
                f"or use an IP address instead."
            ),
        )
    except ConnectionRefusedError:
        logger.info(f"peer.reachability.refused host={host} port={port}")
        return ReachabilityResult(
            ok=False, reason="refused",
            message=(
                f"{host}:{port} responded but nothing is listening on that "
                f"port. The listener may have failed to bind — check the "
                f"status line above."
            ),
        )
    except (socket.timeout, TimeoutError):
        logger.info(f"peer.reachability.timeout host={host} port={port} after={timeout}s")
        return ReachabilityResult(
            ok=False, reason="timeout",
            message=(
                f"{host}:{port} didn't respond within {timeout:g}s. Likely "
                f"a firewall, NAT, or the wrong advertised address."
            ),
        )
    except OSError as e:
        # ENETUNREACH, EHOSTUNREACH, etc. — surface as 'unreachable'.
        # On macOS, ENETUNREACH for TEST-NET-1 lands here rather than
        # raising socket.timeout, so we treat both as "remote-side failure
        # of network reachability" with a unified user-facing message.
        logger.info(f"peer.reachability.unreachable host={host} port={port} err={e}")
        return ReachabilityResult(
            ok=False, reason="unreachable",
            message=(
                f"{host}:{port} is unreachable from this machine "
                f"({e.strerror or str(e) or 'no route'}). Likely a "
                f"firewall, NAT, or wrong advertised address."
            ),
        )
    except Exception as e:  # noqa: BLE001 — never propagate; UI must stay alive
        logger.warning(f"peer.reachability.other host={host} port={port} err={e}")
        return ReachabilityResult(
            ok=False, reason="other",
            message=f"Reachability check failed: {e}",
        )
