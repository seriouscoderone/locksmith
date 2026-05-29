"""Publish role=peer + loc/scheme tcp rpys for an AID — locally and to
its witnesses.

makeLocScheme/makeEndRole on a Hab return signed rpy bytes but do not
persist anything. To make those rpys discoverable they have to be:

  1. parsed back through the Habery's own Kevery/Revery so they land
     in hab.db.rpys / db.ends / db.locs (this is what makes our local
     replyToOobi serve them and what the witness-less CESR blob path
     reads from), and

  2. pushed to each witness in hab.kever.wits — we drive one
     ``keri.app.agenting.messenger`` per witness directly rather than
     going through ``WitnessPublisher`` so we can read each
     ``HTTPMessenger.sent`` deque and surface the HTTP status to the
     UI / logs. The kerihost #2 / #4 inbox bugs we hit earlier would
     have been a clear ``status=504`` here instead of a silent success.

Without step 2 the witness has nothing peer-role to serve, which is why
the dialog has been falling back to a manual endpoint field.
"""
from __future__ import annotations

from hio.base import doing
from keri import Vrsn_1_0, help, kering
from keri.app.agenting import messenger
from keri.core import parsing

logger = help.ogler.getLogger(__name__)


def _witnesses_for(hab) -> list[str]:
    """Return the AID's current witness prefixes. Wrapped so tests can
    inject a fake list without touching the Kever.
    """
    return list(hab.kever.wits or [])


def _is_ok_status(status) -> bool:
    """Witness inboxes return 200 or 204 on success. Treat any 2xx as OK
    and everything else (including missing/None when the messenger never
    got a response) as rejected.
    """
    try:
        return 200 <= int(status) < 300
    except (TypeError, ValueError):
        return False


class PublishPeerRoleDoer(doing.DoDoer):
    """Land peer role/loc rpys locally and push them to all witnesses.

    allow=True (default): /end/role/add + /loc/scheme(tcp, url=<url>).
    allow=False: /end/role/cut + /loc/scheme(tcp, url="") — the empty url
    nullifies the location per Hab.makeLocScheme docs. Used when the
    user toggles "Expose over peer mode" off, so witnesses learn that
    this AID is no longer reachable in peer mode.

    Emits one of these events via signal_bridge on completion:
      - 'publish_complete' — reached the witness layer; payload includes
        a per-witness list of dicts ``{wit, status, ok}`` so callers can
        distinguish "delivered" from "rejected" without re-curling.
      - 'no_witnesses' — solo AID, nothing to push; local rpys still
        landed.
      - 'publish_failed' — exception we couldn't recover from.
    """

    def __init__(self, hby, hab, url: str, signal_bridge=None,
                 timeout_seconds: float = 30.0, allow: bool = True):
        self.hby = hby
        self.hab = hab
        self.url = url
        self.allow = allow
        self.signal_bridge = signal_bridge
        self.timeout_seconds = timeout_seconds
        self.completed = False
        super().__init__(doers=[doing.doify(self.publish_do)])

    def publish_do(self, tymth, tock=0.0, **opts):
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)

        hab = self.hab
        try:
            loc_url = self.url if self.allow else ""
            loc_msg = hab.reply(
                route="/loc/scheme",
                data=dict(eid=hab.pre, scheme=kering.Schemes.tcp, url=loc_url),
            )
            end_route = "/end/role/add" if self.allow else "/end/role/cut"
            end_msg = hab.reply(
                route=end_route,
                data=dict(cid=hab.pre, role=kering.Roles.peer, eid=hab.pre),
            )

            parsing.Parser(version=Vrsn_1_0).parse(
                ims=bytearray(loc_msg), kvy=hab.kvy, rvy=hab.rvy,
            )
            parsing.Parser(version=Vrsn_1_0).parse(
                ims=bytearray(end_msg), kvy=hab.kvy, rvy=hab.rvy,
            )

            action = "published" if self.allow else "revoked"
            wits = _witnesses_for(hab)
            if not wits:
                logger.info(
                    f"peer.role.{action} aid={hab.pre} witnesses=0 "
                    f"url={self.url}"
                )
                self._emit("no_witnesses", aid=hab.pre, witnesses_count=0,
                           url=self.url, allow=self.allow)
                self.completed = True
                return

            # One messenger per witness; push both rpys onto each.
            witers: list[tuple[str, object]] = []
            for wit in wits:
                witer = messenger(hab, wit)
                witer.msgs.append(bytearray(loc_msg))
                witer.msgs.append(bytearray(end_msg))
                self.extend([witer])
                witers.append((wit, witer))

            elapsed = 0.0
            while not all(w.idle for _, w in witers):
                yield self.tock
                elapsed += self.tock or 0.03125
                if elapsed > self.timeout_seconds:
                    logger.warning(
                        f"peer.role.publish_timeout aid={hab.pre} "
                        f"witnesses={len(wits)} url={self.url}"
                    )
                    self._emit(
                        "publish_failed", aid=hab.pre,
                        witnesses_count=len(wits),
                        error="timed out reaching one or more witnesses",
                        witnesses=self._collect_results(witers),
                    )
                    self.remove([w for _, w in witers])
                    self.completed = True
                    return

            results = self._collect_results(witers)
            rejected = [r for r in results if not r["ok"]]
            for r in results:
                logger.info(
                    f"peer.role.publish.witness aid={hab.pre} wit={r['wit']} "
                    f"status={r['status']} ok={r['ok']}"
                )
            level_msg = (
                f"peer.role.{action} aid={hab.pre} witnesses={len(wits)} "
                f"rejected={len(rejected)} url={self.url}"
            )
            if rejected:
                logger.warning(level_msg)
            else:
                logger.info(level_msg)

            self._emit(
                "publish_complete", aid=hab.pre,
                witnesses_count=len(wits), url=self.url,
                allow=self.allow, witnesses=results,
            )
            self.remove([w for _, w in witers])
            self.completed = True

        except Exception as e:  # noqa: BLE001
            logger.exception(f"peer.role.publish_failed aid={hab.pre} err={e}")
            self._emit("publish_failed", aid=hab.pre,
                       witnesses_count=0, error=str(e))
            self.completed = True

    @staticmethod
    def _collect_results(witers) -> list[dict]:
        """Read each witer's last HTTP response (if any) and return a
        list of ``{wit, status, ok}`` dicts. TCP messengers and any
        messenger that finished without a response surface status=None.
        """
        results = []
        for wit, witer in witers:
            sent = getattr(witer, "sent", None)
            status = None
            if sent:
                # Real HTTPMessenger.sent holds hio Response namedtuples
                # with .status. Our fakes do the same. We want the last
                # response (in case more than one rpy was queued).
                try:
                    last = sent[-1]
                except (IndexError, TypeError):
                    last = None
                if last is not None:
                    status = getattr(last, "status", None)
                    if status is None and isinstance(last, dict):
                        status = last.get("status")
            results.append({
                "wit": wit,
                "status": status,
                "ok": _is_ok_status(status),
            })
        return results

    def _emit(self, event_type: str, **data) -> None:
        if self.signal_bridge is None:
            return
        try:
            self.signal_bridge.emit_doer_event(
                doer_name="PublishPeerRoleDoer",
                event_type=event_type,
                data=data,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"peer.role.signal_failed err={e}")
