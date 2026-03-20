# -*- encoding: utf-8 -*-
"""
locksmith.core.challenging module


This module contains the peer-to-peer challenge response protocol

"""

from keri.core import coring


def loadHandlers(db, exc, notifier):
    """ Load handlers for the peer-to-peer challenge response protocol

    Parameters:
        db (Baser): database environment
        notifier (Notifier): Signaler for transient messages for the controller of the agent
        exc (Exchanger): Peer-to-peer message router

    """
    chacha = ChallengeHandler(db=db, notifier=notifier)
    exc.addHandler(chacha)


class ChallengeHandler:
    """  Handle challenge response peer to peer `exn` message """

    resource = "/challenge/response"

    def __init__(self, db, notifier):
        """ Initialize peer to peer challenge response messsage """

        self.db = db
        self.notifier = notifier
        super(ChallengeHandler, self).__init__()

    def handle(self, serder, attachments=None):
        """  Do route specific processsing of Challenge response messages

        Parameters:
            serder (Serder): Serder of the exn challenge response message
            attachments (list): list of tuples of pather, CESR SAD path attachments to the exn event

        """
        payload = serder.ked['a']
        signer = serder.pre
        words = payload["words"]
        msg = dict(
            r=serder.ked['r'],
            signer=signer,
            said=serder.said,
            words=words
        )

        # Notify controller of sucessful challenge
        self.notifier.add(msg)

        # Log signer against event to track successful challenges with signed response
        self.db.reps.add(keys=(signer,), val=coring.Saider(qb64=serder.said))
