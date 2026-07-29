"""Publish role=peer + loc/scheme tcp rpys for an AID — locally and to
its witnesses.

The location is published under the **vault's listener EID**, not under the AID
(``peer.listener_eid``): what a peer dials is a per-vault socket, so the AID
authorizes that endpoint provider rather than claiming to be one. Two signers are
therefore involved — the listener signs ``/loc/scheme`` for itself (BADA
authenticates a loc as coming from its own eid), the AID signs
``/end/role/add`` — and that is why the listener has to exist before publishing.

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
from keri import help, kering
from keri.app.agenting import messenger
from keri.core import parsing

from locksmith.core.remoting import message_version
from locksmith.peer.listener_eid import ensure_listener_hab

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

    allow=True (default): /loc/scheme(tcp, url=<url>) signed by the vault's
    listener EID, plus /end/role/add authorizing that EID for this AID.

    allow=False: /end/role/cut for (cid, peer, listener) only. It does NOT
    nullify the location, unlike the old eid == cid version: the location now
    belongs to the vault's shared listener, so voiding it because one AID stopped
    exposing would silently unreach every other exposed AID in the same vault.
    The cut is the authorization statement and the read side honours it
    (peer.resolution) — a cut end record means not reachable whatever db.locs
    still holds.

    Migration for already-shipped vaults: an install that published the old
    shape holds ``ends[(cid, peer, cid)]`` allowed plus ``locs[(cid, tcp)]``.
    Publishing with allow=True retires that record — a later-dated /end/role/cut
    and a nullifying /loc/scheme — because leaving it standing would advertise
    two endpoints and let a remote resolve the stale one. Conditional on the
    record actually existing, and harmless if it re-fires. ``.migrated`` reports
    whether it happened.

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
        self.migrated = False
        super().__init__(doers=[doing.doify(self.publish_do)])

    def publish_do(self, tymth, tock=0.0, **opts):
        self.wind(tymth)
        self.tock = tock
        _ = (yield self.tock)

        hab = self.hab
        try:
            msgs = self._build_msgs()

            # Parse each rpy back at the version it was BUILT at. hab.reply
            # inherits the hab's protocol version (v1 under the KERI v2 v1-hold,
            # v2 for a v2-native AID), so a hardcoded Vrsn_1_0 parser silently
            # fails to route a v2 rpy — nothing lands in db.ends/db.locs. Detect
            # the version from the bytes (same message_version() pattern used in
            # ipexing/remoting/adjudication) so the round-trip is self-consistent
            # regardless of the hab's version.
            for msg in msgs:
                parsing.Parser(version=message_version(msg)).parse(
                    ims=bytearray(msg), kvy=hab.kvy, rvy=hab.rvy,
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

            # One messenger per witness; push every rpy onto each.
            witers: list[tuple[str, object]] = []
            for wit in wits:
                witer = messenger(hab, wit)
                for msg in msgs:
                    witer.msgs.append(bytearray(msg))
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

    def _build_msgs(self) -> list[bytes]:
        """Signed rpys for this publish, in the order they must be parsed.

        On allow: the listener's own ``/loc/scheme`` first (so the location exists
        before anything authorizes it), then the AID's ``/end/role/add``, then any
        migration rpys retiring a legacy ``eid == cid`` authorization.

        On revoke: just the ``/end/role/cut``. See the class docstring for why the
        location is deliberately left alone.
        """
        hab = self.hab
        listener = ensure_listener_hab(self.hby)
        msgs: list[bytes] = []

        if self.allow:
            # Signed by the LISTENER, not by hab: processReplyLocScheme
            # authenticates a /loc/scheme as coming from its own eid, so a
            # controller-signed loc for someone else's eid is dropped.
            msgs.append(listener.reply(
                route="/loc/scheme",
                data=dict(eid=listener.pre, scheme=kering.Schemes.tcp,
                          url=self.url),
            ))
        msgs.append(hab.reply(
            route="/end/role/add" if self.allow else "/end/role/cut",
            data=dict(cid=hab.pre, role=kering.Roles.peer, eid=listener.pre),
        ))
        if self.allow:
            msgs.extend(self._legacy_retirement_msgs())
        return msgs

    def _legacy_retirement_msgs(self) -> list[bytes]:
        """Rpys retiring a pre-listener-EID ``eid == cid`` authorization, if any.

        Vaults shipped before the listener EID published themselves as their own
        endpoint. Those records stay valid until superseded, so re-publishing
        without retiring them leaves the AID advertising two endpoints — and a
        remote resolving the stale address gets an unreachable one. BADA gives us
        supersedure for free: these rpys are later-dated than the originals and
        carry the same (cid, role, eid) / (eid, scheme) keys.
        """
        hab = self.hab
        try:
            legacy = hab.db.ends.get(
                keys=(hab.pre, kering.Roles.peer, hab.pre))
        except Exception:  # noqa: BLE001 — db can race shut during vault flips
            return []
        if legacy is None or not (legacy.enabled or legacy.allowed):
            return []

        self.migrated = True
        logger.info(
            f"peer.role.legacy_self_endpoint_retired aid={hab.pre} "
            f"(published before the listener EID existed)"
        )
        return [
            hab.reply(
                route="/end/role/cut",
                data=dict(cid=hab.pre, role=kering.Roles.peer, eid=hab.pre),
            ),
            # Nullify the orphaned location too (empty url nullifies, per
            # Hab.makeLocScheme) so the vault holds no stale address for the AID.
            hab.reply(
                route="/loc/scheme",
                data=dict(eid=hab.pre, scheme=kering.Schemes.tcp, url=""),
            ),
        ]

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
