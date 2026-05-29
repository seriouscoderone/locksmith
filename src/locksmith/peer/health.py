"""Background probe of paired-peer TCP endpoints.

Runs as a doer on the vault's doist. Every ``interval_seconds`` it
walks ``allowlist.list()`` and calls ``check_reachable`` on each peer's
endpoint, writing the outcome into ``db.peerHealth`` keyed by AID. The
UI then has a stable place to read each peer's current reachability
without re-probing on every refresh.

This is the read-side companion to the reachability self-test
(``locksmith.peer.reachability``); both call the same low-level
``check_reachable`` helper so the failure-mode classifications stay
in sync.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from urllib.parse import urlparse

from hio.base import doing
from keri import help

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.reachability import check_reachable
from locksmith.peer.records import PeerHealth

logger = help.ogler.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_tcp_endpoint(endpoint_url: str) -> tuple[str | None, int | None]:
    """Return (host, port) from a tcp://host:port URL, or (None, None)
    if the URL can't be parsed into both. Used both for the reachability
    probe and to drive the invalid_host outcome when the stored
    endpoint_url is malformed.
    """
    try:
        u = urlparse(endpoint_url)
    except Exception:  # noqa: BLE001
        return None, None
    if u.scheme not in ("tcp", "tls", ""):
        return None, None
    host = u.hostname
    port = u.port
    if not host or not port:
        return None, None
    return host, port


class PeerHealthMonitorDoer(doing.DoDoer):
    """Periodically probe each paired peer's TCP endpoint.

    Parameters:
        allowlist: read-only source of paired peers (read fresh each cycle
            so additions / removals take effect without restart).
        db: LocksmithBaser instance — writes go to ``db.peerHealth``.
        interval_seconds: base sleep between probe cycles. Jittered by
            ±25% so a flock of wallets started at the same time don't
            herd-probe a shared endpoint in lockstep.
        probe_timeout: per-peer TCP connect timeout in seconds. Total
            cycle wall-time scales with the number of peers in the worst
            case — keep this small (the UX value is the periodic refresh,
            not blocking forever on a dead host).
    """

    def __init__(self, allowlist: PeerAllowlist, db, *,
                 interval_seconds: float = 60.0,
                 probe_timeout: float = 1.5):
        self.allowlist = allowlist
        self.db = db
        self.interval_seconds = interval_seconds
        self.probe_timeout = probe_timeout
        super().__init__(doers=[doing.doify(self.monitor_do)])

    def monitor_do(self, tymth=None, tock=0.0, **opts):
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)
        while True:
            try:
                self.probe_all_once()
            except Exception as e:  # noqa: BLE001 — never let the loop die
                logger.warning(f"peer.health.cycle_failed err={e}")
            # ±25% jitter around interval_seconds
            jitter = random.uniform(0.75, 1.25)
            sleep_left = self.interval_seconds * jitter
            while sleep_left > 0:
                yield self.tock
                sleep_left -= max(self.tock or 0.03125, 0.001)

    def probe_all_once(self) -> None:
        """One synchronous pass over the allowlist. Exposed for tests
        and for any future "probe now" UI button.
        """
        for peer in self.allowlist.list():
            self._probe_one(peer.aid, peer.endpoint_url)

    def _probe_one(self, aid: str, endpoint_url: str) -> None:
        host, port = _parse_tcp_endpoint(endpoint_url)
        if host is None or port is None:
            outcome = "invalid_host"
            message = (
                f"Stored endpoint_url={endpoint_url!r} could not be parsed "
                f"as tcp://host:port."
            )
            ok = False
        else:
            result = check_reachable(host, port, timeout=self.probe_timeout)
            outcome = result.reason
            message = result.message
            ok = result.ok

        prior = self.db.peerHealth.get(keys=(aid,)) or PeerHealth(aid=aid)
        updated = PeerHealth(
            aid=aid,
            last_probed_at=_now_iso(),
            last_outcome=outcome,
            last_message=message,
            consecutive_failures=0 if ok else prior.consecutive_failures + 1,
            consecutive_successes=prior.consecutive_successes + 1 if ok else 0,
            probed_count=prior.probed_count + 1,
        )
        self.db.peerHealth.pin(keys=(aid,), val=updated)

        # One structured log per probe; INFO when state changes, DEBUG
        # otherwise would be ideal but the volume of paired peers in
        # practice is tiny — INFO on outcome changes only, otherwise skip.
        if prior.last_outcome != outcome:
            logger.info(
                f"peer.health.changed aid={aid} from={prior.last_outcome or 'none'} "
                f"to={outcome} consecutive={updated.consecutive_failures if not ok else updated.consecutive_successes}"
            )
