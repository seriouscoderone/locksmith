# -*- encoding: utf-8 -*-
"""
locksmith.core.challenging module


This module contains the peer-to-peer challenge response protocol

"""
import os

from hio.base import doing
from hio.help import decking
from keri import help
from keri.peer import exchanging
from locksmith.turret import directing
from locksmith.turret.handling import IdentifiersHandler, CredentialsHandler, IPEXGrantRequestHandler
from locksmith.turret.uxd import Server, ServerDoer

logger = help.ogler.getLogger(__name__)


def load_handlers(hby, rgy, exc, cues):

    ids = IdentifiersHandler(hby=hby, cues=cues)
    exc.addHandler(ids)

    chs = CredentialsHandler(hby=hby, rgy=rgy, cues=cues)
    exc.addHandler(chs)

    igr = IPEXGrantRequestHandler(hby=hby, rgy=rgy, cues=cues)
    exc.addHandler(igr)


FORMAT = '%(asctime)s [turret] %(levelname)-8s %(message)s'

class TurretDoer(doing.DoDoer):
    """ Doer for turret"""
    def __init__(self, hby, rgy, locksmith_alias, plugin_identifier, **kwa):
        """  Initialize the TurretDoer

        Args:
            hby: Habitat database instance used for retrieving settings and configurations.
            locksmith_alias: Alias of the locksmith, used to retrieve the habitat settings.
            plugin_identifier: Identifier for the plugin that this doer will utilize.
            **kwa: Additional keyword arguments passed to the base class constructor.
        """
        hab = hby.habByName(locksmith_alias, ns="settings")
        cues = decking.Deck()

        if os.path.exists("/tmp/keripy_kli.s"):
            os.remove("/tmp/keripy_kli.s")

        server = Server(path="/tmp/keripy_kli.s", bufsize=8069)
        server_doer = ServerDoer(server=server)

        exc = exchanging.Exchanger(hby, handlers=[])
        load_handlers(hby, rgy, exc, cues)

        self.shim = ExchangerShim(aid=plugin_identifier, exc=exc)
        directant = directing.Directant(hab=hab, server=server, exchanger=self.shim, cues=cues)

        doers =  [directant, server_doer]

        super(TurretDoer, self).__init__(doers=doers, **kwa)

    def set_plugin_identifier(self, plugin_identifier):
        self.shim.aid = plugin_identifier


class ExchangerShim:

    def __init__(self, aid, exc):
        logger.debug(f"creating with {aid}")
        self.aid = aid
        self.exchanger = exc

    def processEvent(self, serder, tsgs=None, cigars=None, **kwargs):
        print(serder.pretty())
        sender = serder.ked["i"]
        if sender == self.aid:
            self.exchanger.processEvent(serder, tsgs, cigars, **kwargs)
        else:
            logger.info(f"Received an exn message from invalid signer={sender}")

