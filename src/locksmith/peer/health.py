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


def summarize_health_for_ui(health: PeerHealth | None) -> tuple[str, str]:
    """Return (color_key, status_phrase) for rendering on the peers list.

    color_key is one of: gray | green | amber | red — matches the status
    dot palette used elsewhere in the peer section.

    The phrase is short (fits inline next to the peer label). Time is
    rendered as a coarse relative interval since fine precision is
    noise at the UX layer — what the user cares about is "currently
    reachable" vs "recently unreachable" vs "long-down".
    """
    if health is None or not health.last_probed_at:
        return "gray", "not yet probed"

    age = _relative_age(health.last_probed_at)
    if health.last_outcome == "ok":
        return "green", f"reachable ({age} ago)"

    # Non-ok: classify down-state severity by streak length. At default
    # probe cadence (60s ±jitter) 3 misses ≈ 2-4 minutes — long enough
    # to treat as a real outage worth a red dot. Shorter streaks stay
    # amber so a single transient timeout doesn't alarm.
    streak = health.consecutive_failures
    if streak >= 3:
        return "red", f"down for {streak} probes ({age} ago)"
    if streak >= 1:
        return "amber", f"unreachable: {health.last_outcome} ({streak} in a row)"
    # streak == 0 but last_outcome != ok — shouldn't really happen, but
    # keep the UI honest with whatever's there.
    return "amber", f"{health.last_outcome} ({age} ago)"


def _relative_age(iso_ts: str) -> str:
    """Best-effort 'N s/m/h/d ago' from an ISO-8601 timestamp."""
    try:
        then = datetime.fromisoformat(iso_ts)
    except ValueError:
        return "unknown"
    now = datetime.now(timezone.utc)
    delta = (now - then).total_seconds()
    if delta < 90:
        return f"{int(delta)}s"
    if delta < 90 * 60:
        return f"{int(delta // 60)}m"
    if delta < 36 * 3600:
        return f"{int(delta // 3600)}h"
    return f"{int(delta // 86400)}d"


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
        keridb: the keripy Baser holding ends/locs. When provided, a
            probe FAILURE triggers a route refresh through
            ``peer/resolution.py`` (``allowlist.refresh_route``): a peer
            that moved has already landed its newer signed /loc/scheme
            in this db, and probing the stale cached address forever
            renders red for a peer that is perfectly reachable
            (backlog/2026-07-29-peer-record-endpoint-never-refreshes.md).
            If the refresh moves the record, the fresh address is
            re-probed immediately so the UI recovers on this cycle, not
            the next one. None disables refresh (legacy shape).
        interval_seconds: base sleep between probe cycles. Jittered by
            ±25% so a flock of wallets started at the same time don't
            herd-probe a shared endpoint in lockstep.
        probe_timeout: per-peer TCP connect timeout in seconds. Total
            cycle wall-time scales with the number of peers in the worst
            case — keep this small (the UX value is the periodic refresh,
            not blocking forever on a dead host).
    """

    def __init__(self, allowlist: PeerAllowlist, db, *, keridb=None,
                 interval_seconds: float = 60.0,
                 probe_timeout: float = 1.5):
        self.allowlist = allowlist
        self.db = db
        self.keridb = keridb
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

        if not ok and self.keridb is not None:
            # Failure is the cue to check whether the peer moved: re-resolve
            # its freshest authorized route and, if the record changed,
            # re-probe the fresh address so this cycle reports the peer's
            # actual reachability rather than the stale cache's.
            refreshed = self.allowlist.refresh_route(self.keridb, aid)
            if refreshed is not None and refreshed.endpoint_url != endpoint_url:
                logger.info(
                    f"peer.health.route_refreshed aid={aid} "
                    f"from={endpoint_url} to={refreshed.endpoint_url}"
                )
                self._probe_one(aid, refreshed.endpoint_url)
                return

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
