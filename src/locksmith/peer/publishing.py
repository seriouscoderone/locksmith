"""Publish role=peer + loc/scheme tcp rpys for an AID — locally and to
its witnesses.

makeLocScheme/makeEndRole on a Hab return signed rpy bytes but do not
persist anything. To make those rpys discoverable they have to be:

  1. parsed back through the Habery's own Kevery/Revery so they land
     in hab.db.rpys / db.ends / db.locs (this is what makes our local
     replyToOobi serve them and what the witness-less CESR blob path
     reads from), and

  2. pushed to each witness in hab.kever.wits via WitnessPublisher so
     remote wallets resolving a witness-served peer-OOBI get the role
     + loc rpys back inline with the KEL.

Without step 2 the witness has nothing peer-role to serve, which is why
the dialog has been falling back to a manual endpoint field.
"""
from __future__ import annotations

from hio.base import doing
from keri import Vrsn_1_0, help, kering
from keri.app.agenting import WitnessPublisher
from keri.core import parsing

logger = help.ogler.getLogger(__name__)


def _witnesses_for(hab) -> list[str]:
    """Return the AID's current witness prefixes. Wrapped so tests can
    inject a fake list without touching the Kever.
    """
    return list(hab.kever.wits or [])


class PublishPeerRoleDoer(doing.DoDoer):
    """Land peer role/loc rpys locally and push them to all witnesses.

    Emits one of these events via signal_bridge on completion:
      - 'publish_complete' (witnesses_count > 0, all sent)
      - 'no_witnesses' (witnesses_count == 0, local-only)
      - 'publish_failed' (unexpected error)
    """

    def __init__(self, hby, hab, url: str, signal_bridge=None,
                 timeout_seconds: float = 30.0):
        self.hby = hby
        self.hab = hab
        self.url = url
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
            loc_msg = hab.reply(
                route="/loc/scheme",
                data=dict(eid=hab.pre, scheme=kering.Schemes.tcp, url=self.url),
            )
            end_msg = hab.reply(
                route="/end/role/add",
                data=dict(cid=hab.pre, role=kering.Roles.peer, eid=hab.pre),
            )

            parsing.Parser(version=Vrsn_1_0).parse(
                ims=bytearray(loc_msg), kvy=hab.kvy, rvy=hab.rvy,
            )
            parsing.Parser(version=Vrsn_1_0).parse(
                ims=bytearray(end_msg), kvy=hab.kvy, rvy=hab.rvy,
            )

            wits = _witnesses_for(hab)
            if not wits:
                logger.info(
                    f"peer.role.published aid={hab.pre} witnesses=0 "
                    f"url={self.url}"
                )
                self._emit("no_witnesses", aid=hab.pre, witnesses_count=0,
                           url=self.url)
                self.completed = True
                return

            publisher = WitnessPublisher(hby=self.hby)
            self.extend([publisher])

            publisher.msgs.append(dict(pre=hab.pre, msg=bytes(loc_msg)))
            publisher.msgs.append(dict(pre=hab.pre, msg=bytes(end_msg)))

            elapsed = 0.0
            while not publisher.idle:
                yield self.tock
                elapsed += self.tock or 0.03125
                if elapsed > self.timeout_seconds:
                    logger.warning(
                        f"peer.role.publish_timeout aid={hab.pre} "
                        f"witnesses={len(wits)} url={self.url}"
                    )
                    self._emit("publish_failed", aid=hab.pre,
                               witnesses_count=len(wits),
                               error="timed out reaching one or more witnesses")
                    self.remove([publisher])
                    self.completed = True
                    return

            logger.info(
                f"peer.role.published aid={hab.pre} witnesses={len(wits)} "
                f"url={self.url}"
            )
            self._emit("publish_complete", aid=hab.pre,
                       witnesses_count=len(wits), url=self.url)
            self.remove([publisher])
            self.completed = True

        except Exception as e:  # noqa: BLE001
            logger.exception(f"peer.role.publish_failed aid={hab.pre} err={e}")
            self._emit("publish_failed", aid=hab.pre,
                       witnesses_count=0, error=str(e))
            self.completed = True

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
