# -*- encoding: utf-8 -*-
"""
Directing for turret. Modified from keripy directing, now accepts queues.
"""
import itertools
import json

from hio.base import doing
from hio.help import decking

from keri import help, kering
from keri.core import eventing, routing
from keri.core import parsing
from keri.app import prodding
from keri.vdr.eventing import Tevery

logger = help.ogler.getLogger(__name__)


class Director(doing.Doer):
    """
    Base class for Direct Mode KERI Controller Doer with habitat and TCP Client

    Attributes:
        hab (Habitat: local controller's context)
        client (serving.Client): hio TCP client instance.
            Assumes operated by another doer.

    Inherited Properties:
        tyme (float): relative cycle time of associated Tymist, obtained
            via injected .tymth function wrapper closure.
        tymth (function): function wrapper closure returned by Tymist .tymeth()
            method.  When .tymth is called it returns associated Tymist .tyme.
            .tymth provides injected dependency on Tymist tyme base.
        tock (float): desired time in seconds between runs or until next run,
            non-negative, zero means run asap

    Properties:

    Inherited Methods:
        .__call__ makes instance callable return generator
        .do is generator function returns generator

    Methods:

    Hidden:
       ._tymth is injected function wrapper closure returned by .tymen() of
            associated Tymist instance that returns Tymist .tyme. when called.
       ._tock is hidden attribute for .tock property
    """

    def __init__(self, hab, client, **kwa):
        """
        Initialize instance.

        Inherited Parameters:
            tymist is  Tymist instance
            tock is float seconds initial value of .tock

        Parameters:
            hab is Habitat instance
            client is TCP Client instance. Assumes opened/closed elsewhere

        """
        super(Director, self).__init__(**kwa)
        self.hab = hab
        self.client = client  # use client to initiate comms
        if self.tymth:
            self.client.wind(self.tymth)

    def wind(self, tymth):
        """
        Inject new tymist.tymth as new ._tymth. Changes tymist.tyme base.
        Updates winds .tymer .tymth
        """
        super(Director, self).wind(tymth)
        self.client.wind(tymth)

    def sendOwnEvent(self, sn):
        """
        Utility to send own event at sequence number sn
        """
        msg = self.hab.msgOwnEvent(sn=sn)
        # send to connected remote
        self.client.tx(msg)
        logger.info("%s: %s sent event:\n%s\n\n", self.hab.name, self.hab.pre, bytes(msg))

    def sendOwnInception(self):
        """
        Utility to send own inception on client
        """
        self.sendOwnEvent(sn=0)


class Reactor(doing.DoDoer):
    """
    Reactor Subclass of DoDoer with doers list from do generator methods:
        .msgDo, .cueDo, and  .escrowDo.
    Enables continuous scheduling of doers (do generator instances or functions)

    Implements Doist like functionality to allow nested scheduling of doers.
    Each DoDoer runs a list of doers like a Doist but using the tyme from its
       injected tymist as injected by its parent DoDoer or Doist.

    Scheduling hierarchy: Doist->DoDoer...->DoDoer->Doers

    Inherited Attributes:
        .done is Boolean completion state:
            True means completed
            Otherwise incomplete. Incompletion maybe due to close or abort.
        .opts is dict of injected options for its generator .do
        .doers is list of Doers or Doer like generator functions

    Attributes:
        .hab is Habitat instance of local controller's context
        .client is TCP Client instance.
        .kevery is Kevery instance


    Inherited Properties:
        .tyme is float relative cycle time of associated Tymist .tyme obtained
            via injected .tymth function wrapper closure.
        .tymth is function wrapper closure returned by Tymist .tymeth() method.
            When .tymth is called it returns associated Tymist .tyme.
            .tymth provides injected dependency on Tymist tyme base.
        .tock is float, desired time in seconds between runs or until next run,
                 non-negative, zero means run asap

    Properties:

    Inherited Methods:
        .wind  injects ._tymth dependency from associated Tymist to get its .tyme
        .__call__ makes instance callable
            Appears as generator function that returns generator
        .do is generator method that returns generator
        .enter is enter context action method
        .recur is recur context action method or generator method
        .clean is clean context action method
        .exit is exit context method
        .close is close context method
        .abort is abort context method

    Overidden Methods:

    Hidden:
       ._tymth is injected function wrapper closure returned by .tymen() of
            associated Tymist instance that returns Tymist .tyme. when called.
       ._tock is hidden attribute for .tock property

    """

    def __init__(self, hab, client, verifier=None, exchanger=None, direct=True, doers=None, **kwa):
        """
        Initialize instance.

        Inherited Parameters:
            tymist is  Tymist instance
            tock is float seconds initial value of .tock
            doers is list of doers (do generator instances, functions or methods)

        Parameters:
            hab is Habitat instance of local controller's context
            client is TCP Client instance
            verifier is Verifier instance of local controller's TEL context
            direct is Boolean, True means direct mode so process cue'd receipts
                    False means indirect mode so don't process cue'ed receipts

        """
        self.hab = hab
        self.client = client  # use client for both rx and tx
        self.verifier = verifier
        self.exc = exchanger
        self.direct = True if direct else False
        doers = doers if doers is not None else []
        doers.extend([doing.doify(self.msgDo),
                      doing.doify(self.escrowDo),
                      doing.doify(self.cueDo)])

        self.kevery = eventing.Kevery(db=self.hab.db,
                                      lax=False,
                                      local=False,
                                      direct=self.direct)

        if self.verifier is not None:
            self.tvy = Tevery(reger=self.verifier.reger,
                              db=self.hab.db,
                              local=False)
        else:
            self.tvy = None

        # keripy v2 still emits KERI 1.0 attachment counters on streams.
        # Keep this parser on v1 until keripy supports mixed versions per frame.
        self.parser = parsing.Parser(ims=self.client.rxbs,
                                     framed=True,
                                     kvy=self.kevery,
                                     tvy=self.tvy,
                                     exc=self.exc,
                                     version=kering.Vrsn_1_0)

        super(Reactor, self).__init__(doers=doers, **kwa)
        if self.tymth:
            self.client.wind(self.tymth)

    def wind(self, tymth):
        """
        Inject new tymist.tymth as new ._tymth. Changes tymist.tyme base.
        Updates winds .tymer .tymth
        """
        super(Reactor, self).wind(tymth)
        self.client.wind(tymth)

    def msgDo(self, tymth=None, tock=0.0, **opts):
        """
        Returns doifiable Doist compatibile generator method (doer dog) to process
            incoming message stream of .kevery

        Doist Injected Attributes:
            g.tock = tock  # default tock attributes
            g.done = None  # default done state
            g.opts

        Parameters:
            tymth is injected function wrapper closure returned by .tymen() of
                Tymist instance. Calling tymth() returns associated Tymist .tyme.
            tock is injected initial tock value
            opts is dict of injected optional additional parameters


        Usage:
            add result of doify on this method to doers list
        """
        yield  # enter context
        if self.parser.ims:
            logger.info("Client %s received:\n%s\n...\n", self.hab.name, self.parser.ims[:1024])
        done = yield from self.parser.parsator(local=True)  # process messages continuously
        return done  # should nover get here except forced close

    def cueDo(self, tymth=None, tock=0.0, **opts):
        """
         Returns doifiable Doist compatibile generator method (doer dog) to process
            .kevery.cues deque

        Doist Injected Attributes:
            g.tock = tock  # default tock attributes
            g.done = None  # default done state
            g.opts

        Parameters:
            tymth is injected function wrapper closure returned by .tymen() of
                Tymist instance. Calling tymth() returns associated Tymist .tyme.
            tock is injected initial tock value
            opts is dict of injected optional additional parameters

        Usage:
            add result of doify on this method to doers list
        """
        yield  # enter context
        while True:
            for msg in self.hab.processCuesIter(self.kevery.cues):
                self.sendMessage(msg, label="chit or receipt")
                yield  # throttle just do one cue at a time
            yield

    def escrowDo(self, tymth=None, tock=0.0, **opts):
        """
         Returns doifiable Doist compatibile generator method (doer dog) to process
            .kevery escrows.

        Doist Injected Attributes:
            g.tock = tock  # default tock attributes
            g.done = None  # default done state
            g.opts

        Parameters:
            tymth is injected function wrapper closure returned by .tymen() of
                Tymist instance. Calling tymth() returns associated Tymist .tyme.
            tock is injected initial tock value
            opts is dict of injected optional additional parameters

        Usage:
            add result of doify on this method to doers list
        """
        yield  # enter context
        while True:
            self.kevery.processEscrows()
            if self.tvy is not None:
                self.tvy.processEscrows()
            yield

    def sendMessage(self, msg, label=""):
        """
        Sends message msg and loggers label if any
        """
        self.client.tx(msg)  # send to remote
        logger.info("%s sent %s:\n%s\n\n", self.hab.name, label, bytes(msg))


class Directant(doing.DoDoer):
    """
    Directant class with TCP Server.
    Responds to initiated connections from a remote Director by creating and
    running a Reactant per connection. Each Reactant has TCP remoter.

    Directant Subclass of DoDoer with doers list from do generator methods:
        .serviceDo

    Enables continuous scheduling of doers (do generator instances or functions)

    Implements Doist like functionality to allow nested scheduling of doers.
    Each DoDoer runs a list of doers like a Doist but using the tyme from its
       injected tymist as injected by its parent DoDoer or Doist.

    Scheduling hierarchy: Doist->DoDoer...->DoDoer->Doers

    Inherited Attributes:
        .done is Boolean completion state:
            True means completed
            Otherwise incomplete. Incompletion maybe due to close or abort.
        .opts is dict of injected options for its generator .do
        .doers is list of Doers or Doer like generator functions

    Attributes:
        .hab is Habitat instance of local controller's context
        .server is TCP client instance. Assumes operated by another doer.
        .rants is dict of Reactants indexed by connection address

    Inherited Properties:
        .tyme is float relative cycle time of associated Tymist .tyme obtained
            via injected .tymth function wrapper closure.
        .tymth is function wrapper closure returned by Tymist .tymeth() method.
            When .tymth is called it returns associated Tymist .tyme.
            .tymth provides injected dependency on Tymist tyme base.
        .tock is desired time in seconds between runs or until next run,
                 non-negative, zero means run asap

    Properties:

    Inherited Methods:
        .wind  injects ._tymth dependency from associated Tymist to get its .tyme
        .__call__ makes instance callable
            Appears as generator function that returns generator
        .do is generator method that returns generator
        .enter is enter context action method
        .recur is recur context action method or generator method
        .clean is clean context action method
        .exit is exit context method
        .close is close context method
        .abort is abort context method

    Methods:

    Hidden:
       ._tymth is injected function wrapper closure returned by .tymen() of
            associated Tymist instance that returns Tymist .tyme. when called.
       ._tock is hidden attribute for .tock property
    """

    def __init__(self, hab, server, verifier=None, exchanger=None, doers=None, cues=None,
                 disclosable=None, prodPolicy=None, **kwa):
        """
        Initialize instance.

        Inherited Parameters:
            tymist is  Tymist instance
            tock is float seconds initial value of .tock

        Parameters:
            db is database instance of local controller's context
            verifier (optional) is Verifier instance of local controller's TEL context
            server is TCP Server instance
        """
        self.hab = hab
        self.verifier = verifier
        self.exchanger = exchanger
        self.server = server  # use server for cx
        # Forwarded verbatim to every per-connection Reactant, which is where
        # the ProdResponder lives (only the Reactant owns a kevery and a way to
        # write back on the connection the prod arrived on).
        self.disclosable = disclosable
        self.prodPolicy = prodPolicy
        self.rants = dict()
        self.cues = cues if cues is not None else decking.Deck()

        doers = doers if doers is not None else []
        doers.extend([doing.doify(self.serviceDo)])
        super(Directant, self).__init__(doers=doers, **kwa)
        if self.tymth:
            self.server.wind(self.tymth)

    def wind(self, tymth):
        """
        Inject new tymist.tymth as new ._tymth. Changes tymist.tyme base.
        Updates winds .tymer .tymth
        """
        super(Directant, self).wind(tymth)
        self.server.wind(tymth)

    def serviceDo(self, tymth=None, tock=0.0, **opts):
        """
        Returns doifiable Doist compatibile generator method (doer dog) to service
            connections on .server. Creates remoter and rant (Reactant) for each
            open connection and adds rant to running doers.

        Doist Injected Attributes:
            g.tock = tock  # default tock attributes
            g.done = None  # default done state
            g.opts

        Parameters:
            tymth is injected function wrapper closure returned by .tymen() of
                Tymist instance. Calling tymth() returns associated Tymist .tyme.
            tock is injected initial tock value
            opts is dict of injected optional additional parameters


        Usage:
            add result of doify on this method to doers list
        """
        yield  # enter context
        while True:
            for ca, ix in list(self.server.ixes.items()):
                # Drain any buffered bytes via a Reactant FIRST, even if
                # the remote already closed. peer_send opens, writes, and
                # closes in sub-millisecond; by the next directant tick
                # ix.rxbs has the payload but ix.cutoff is already True.
                # The old order (skip-if-cutoff) silently dropped those
                # bytes — every short-lived peer connection lost data.
                if ca not in self.rants and (ix.rxbs or not ix.cutoff):
                    rant = Reactant(tymth=self.tymth, hab=self.hab, verifier=self.verifier,
                                    exchanger=self.exchanger, remoter=ix, cues=self.cues,
                                    disclosable=self.disclosable,
                                    prodPolicy=self.prodPolicy)
                    self.rants[ca] = rant
                    # add Reactant (rant) doer to running doers
                    self.extend(doers=[rant])  # open and run rant as doer

                # Now reap cutoff connections that have no remaining
                # buffered bytes for the Reactant to chew on.
                if ix.cutoff and not ix.rxbs:
                    self.closeConnection(ca)
                    continue

                if ix.tymeout > 0.0 and ix.tymer.expired:
                    self.closeConnection(ca)  # also removes rant

            yield

    def closeConnection(self, ca):
        """
        Close and remove connection given by ca and remove associated rant at ca.
        """
        if ca in self.server.ixes:  # remoter still there
            self.server.ixes[ca].serviceSends()  # send final bytes to socket
        self.server.removeIx(ca)
        if ca in self.rants:  # remove rant (Reactant) if any
            self.remove([self.rants[ca]])  # close and remove rant from doers list
            del self.rants[ca]


class Reactant(doing.DoDoer):
    """
    Reactant Subclass of DoDoer with doers list from do generator methods:
        .msgDo, .cueDo, and .escrowDo.
    Enables continuous scheduling of doers (do generator instances or functions)

    Implements Doist like functionality to allow nested scheduling of doers.
    Each DoDoer runs a list of doers like a Doist but using the tyme from its
       injected tymist as injected by its parent DoDoer or Doist.

    Scheduling hierarchy: Doist->DoDoer...->DoDoer->Doers

    Attributes:
        .hab is Habitat instance of local controller's context
        .kevery is Kevery instance
        .remoter is TCP Remoter instance for connection from remote TCP client.

    Inherited Attributes:
        .done is Boolean completion state:
            True means completed
            Otherwise incomplete. Incompletion maybe due to close or abort.
        .opts is dict of injected options for its generator .do
        .doers is list of Doers or Doer like generator functions


    Inherited Properties:
        .tyme is float relative cycle time of associated Tymist .tyme obtained
            via injected .tymth function wrapper closure.
        .tymth is function wrapper closure returned by Tymist .tymeth() method.
            When .tymth is called it returns associated Tymist .tyme.
            .tymth provides injected dependency on Tymist tyme base.
        .tock is float, desired time in seconds between runs or until next run,
                 non-negative, zero means run asap

    Properties:

    Inherited Methods:
        .wind  injects ._tymth dependency from associated Tymist to get its .tyme
        .__call__ makes instance callable
            Appears as generator function that returns generator
        .do is generator method that returns generator
        .enter is enter context action method
        .recur is recur context action method or generator method
        .clean is clean context action method
        .exit is exit context method
        .close is close context method
        .abort is abort context method

    Overidden Methods:

    Hidden:
       ._tymth is injected function wrapper closure returned by .tymen() of
            associated Tymist instance that returns Tymist .tyme. when called.
       ._tock is hidden attribute for .tock property

    """

    def __init__(self, hab, remoter, verifier=None, exchanger=None, doers=None, cues=None,
                 disclosable=None, prodPolicy=None, **kwa):
        """
        Initialize instance.

        Inherited Parameters:
            tymist is  Tymist instance
            tock is float seconds initial value of .tock
            doers is list of doers (do generator instancs or functions)

        Parameters:
            hby is Habitat instance of local controller's context
            verifier is Verifier instance of local controller's TEL context
            remoter is TCP Remoter instance
            doers is list of doers (do generator instances, functions or methods)
            disclosable (dict|None): said -> SAD this controller consents to
                disclose when prodded. Built by a RULE over its own
                credentials (keri_serviceaid.providers.disclosure), never
                hand-curated -- a hand-kept map is an ACL keyed by SAID.
                None means disclose nothing.
            prodPolicy (callable|None): ProdResponder audience gate
                (source, said, route, serder) -> bool.

        """
        self.hab = hab
        self.verifier = verifier
        self.exchanger = exchanger
        self.remoter = remoter  # use remoter for both rx and tx
        self.cues = cues if cues is not None else decking.Deck()

        doers = doers if doers is not None else []

        #  needs unique kevery with ims per remoter connnection
        rvy = routing.Revery(db=hab.db)
        self.kevery = eventing.Kevery(db=self.hab.db,
                                      lax=False,
                                      local=False,
                                      rvy=rvy)

        if self.verifier is not None:
            self.tevery = Tevery(reger=self.verifier.reger,
                                 db=self.hab.db,
                                 local=False, rvy=rvy)
            self.tevery.registerReplyRoutes(router=rvy.rtr)
        else:
            self.tevery = None

        self.kevery.registerReplyRoutes(router=rvy.rtr)

        # keripy v2 still emits KERI 1.0 attachment counters on streams.
        # Keep this parser on v1 until keripy supports mixed versions per frame.
        #
        # vry=self.verifier: without it a bare ACDC message (ilk is None, the
        # SerderACDC branch of Parser.msgProcess) has nowhere to route -- vry
        # defaults to None, `vry.processACDC(**exts)` raises AttributeError, and
        # Parser turns that into "No verifier to process so dropped ACDC=..." --
        # silently, the same failure mode the sibling `tvy=None` comment already
        # documents for TEL events. self.verifier is already threaded in for the
        # per-connection Tevery two lines above; it was just never also given to
        # the Parser. Found driving a real credential-over-peer-transport delivery
        # (actuarial HOA C2c Task 5): an untargeted credential's own ACDC message
        # is exactly this shape, so every peer connection dropped it before this.
        self.parser = parsing.Parser(ims=self.remoter.rxbs,
                                     framed=True,
                                     kvy=self.kevery,
                                     tvy=self.tevery,
                                     exc=self.exchanger,
                                     rvy=rvy,
                                     vry=self.verifier,
                                     version=kering.Vrsn_1_0)

        # -- answering a `pro` -------------------------------------------
        # ORDER IS THE FIX, not merely the wiring. cueDo drains
        # self.kevery.cues through hab.processCuesIter, which pull()s every cue
        # unconditionally and dispatches on kind -- and it has no `prod` branch
        # and no else, so a prod cue is pulled and silently DISCARDED. A
        # ProdResponder scheduled after cueDo is handed an empty deck and
        # produces zero bars, which on the wire is byte-identical to having no
        # responder at all. A DoDoer runs its doers in list order, one recur per
        # pass, so the responder must sit between msgDo (which parses the prod
        # and pushes the cue) and cueDo (which would destroy it).
        #
        # pvrsn must match the Parser pin below (Vrsn_1_0): a bar built at a
        # different major version is dropped by the asker's parser without an
        # error, which is the same silent-zero again.
        # A CALLABLE, snapshotted per connection. A dict fixed at listener
        # startup would never contain a credential issued afterwards -- the
        # mandate a CUO declares mid-session is exactly that case. Each
        # inbound connection gets its own Reactant, and the asker opens a new
        # connection per request, so snapshotting here is current.
        if callable(disclosable):
            try:
                bodies = disclosable() or {}
            except Exception:               # noqa: BLE001 -- disclose nothing on error
                logger.exception("prod.disclosable_provider_failed")
                bodies = {}
        else:
            bodies = disclosable if disclosable is not None else {}

        self.prodder = prodding.ProdResponder(
            hab=self.hab,
            kvy=self.kevery,
            disclosable=bodies,
            policy=prodPolicy,
            pvrsn=kering.Vrsn_1_0,
        )

        doers.extend([doing.doify(self.msgDo),
                      prodding.ProdResponderDoer(
                          responder=self.prodder,
                          send=lambda msg: self.sendMessage(msg, label="bar")),
                      doing.doify(self.cueDo),
                      doing.doify(self.escrowDo)])

        super(Reactant, self).__init__(doers=doers, **kwa)
        if self.tymth:
            self.remoter.wind(self.tymth)

    def wind(self, tymth):
        """
        Inject new tymist.tymth as new ._tymth. Changes tymist.tyme base.
        Updates winds .tymer .tymth
        """
        super(Reactant, self).wind(tymth)
        self.remoter.wind(tymth)

    def msgDo(self, tymth=None, tock=0.0, **opts):
        """
        Returns doifiable Doist compatibile generator method (doer dog) to process
            incoming message stream of .kevery

        Doist Injected Attributes:
            g.tock = tock  # default tock attributes
            g.done = None  # default done state
            g.opts

        Parameters:
            tymth is injected function wrapper closure returned by .tymen() of
                Tymist instance. Calling tymth() returns associated Tymist .tyme.
            tock is injected initial tock value
            opts is dict of injected optional additional parameters


        Usage:
            add result of doify on this method to doers list
        """
        yield  # enter context
        if self.parser.ims:
            logger.info("Server %s: received: %s", self.hab.name,
                        self.parser.ims[:1024])
        done = yield from self.parser.parsator(local=True)  # process messages continuously
        return done  # should never get here except forced close

    def cueDo(self, tymth=None, tock=0.0, **opts):
        """
         Returns doifiable Doist compatibile generator method (doer dog) to process
            .kevery.cues deque

        Doist Injected Attributes:
            g.tock = tock  # default tock attributes
            g.done = None  # default done state
            g.opts

        Parameters:
            tymth is injected function wrapper closure returned by .tymen() of
                Tymist instance. Calling tymth() returns associated Tymist .tyme.
            tock is injected initial tock value
            opts is dict of injected optional additional parameters

        Usage:
            add result of doify on this method to doers list
        """
        yield  # enter context
        while True:
            for msg in self.hab.processCuesIter(self.kevery.cues):
                if isinstance(msg, list):
                    msg = bytearray(itertools.chain(*msg))

                self.sendMessage(msg, label="chit or receipt or replay")
                yield  # throttle just do one cue at a time
            while self.cues:
                msg = self.cues.popleft()
                data = json.dumps(msg).encode("utf-8")

                self.sendMessage(data, label="exn response")
                yield  # throttle just do one cue at a time
            yield

    def escrowDo(self, tymth=None, tock=0.0, **opts):
        """
         Returns doifiable Doist compatibile generator method (doer dog) to process
            .kevery escrows.

        Doist Injected Attributes:
            g.tock = tock  # default tock attributes
            g.done = None  # default done state
            g.opts

        Parameters:
            tymth is injected function wrapper closure returned by .tymen() of
                Tymist instance. Calling tymth() returns associated Tymist .tyme.
            tock is injected initial tock value
            opts is dict of injected optional additional parameters

        Usage:
            add result of doify on this method to doers list
        """
        yield  # enter context
        while True:
            self.kevery.processEscrows()
            if self.tevery is not None:
                self.tevery.processEscrows()
            yield

    def sendMessage(self, msg, label=""):
        """
        Sends message msg and loggers label if any
        """
        self.remoter.tx(msg)  # send to remote
        logger.info("Server %s: sent %s:\n%d\n\n", self.hab.name,
                    label, len(msg))


def runController(doers, expire=0.0):
    """
    Utiitity Function to create doist to run doers
    """
    tock = 0.03125
    doist = doing.Doist(limit=expire, tock=tock, real=True)
    doist.do(doers=doers)
