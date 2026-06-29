"""MailboxDirector.add_poller(extra_topics=...) — per-poller topic extension.

A host that mounts an application AID (e.g. a micro-app Service-AID whose command
exns arrive under their own route-derived mailbox topic, like "insurance") needs
that AID's poller to poll the extra topic WITHOUT widening polling for every
other AID. `extra_topics` is appended to the director's defaults for that poller
only; omitting it preserves today's behavior.
"""
from keri.app import habbing
from keri.core import signing

from locksmith.core import indirecting

BASE_TOPICS = ["/receipt", "/credential", "/reply"]


def _hby():
    return habbing.Habery(name="mbxtopics", temp=True,
                          salt=signing.Salter(raw=b'0123456789abcdef').qb64)


def test_add_poller_appends_extra_topics_for_that_poller_only():
    hby = _hby()
    try:
        hab = hby.makeHab(name="svc")
        mbd = indirecting.MailboxDirector(hby=hby, topics=list(BASE_TOPICS))

        mbd.add_poller(hab=hab, mailbox="BWan", extra_topics=["insurance"])
        gated = mbd.pollers[-1]
        assert "insurance" in gated.topics                 # extra topic polled
        assert all(t in gated.topics for t in BASE_TOPICS)  # base topics kept

        # backward compatible: no extra_topics -> exactly the director defaults
        mbd.add_poller(hab=hab, mailbox="BWil")
        assert mbd.pollers[-1].topics == BASE_TOPICS

        # the director's own topic list is not mutated by per-poller extras
        assert mbd.topics == BASE_TOPICS
    finally:
        hby.close()
