"""The MailboxDirector mounts a keri-serverless-mailbox MailboxClient whose on_message feeds
the director's existing parse pipeline (self.msgs -> msgDo -> parser). Verifies wiring, not
live SSE: a fake delivered message lands in self.msgs as raw bytes."""
from keri.app import habbing
from keri.core import signing
from locksmith.core import indirecting
from locksmith.core.mailbox_cursor import DbTopsCursorStore

BASE_TOPICS = ["/receipt", "/credential", "/reply"]


def test_director_mounts_client_and_on_message_feeds_msgs():
    hby = habbing.Habery(name="mbxclient", temp=True,
                         salt=signing.Salter(raw=b'0123456789abcdef').qb64)
    try:
        hab = hby.makeHab(name="svc")
        mbd = indirecting.MailboxDirector(hby=hby, topics=list(BASE_TOPICS))
        mbd.add_poller(hab=hab, mailbox="BWan", extra_topics=["insurance"])
        client_doer = mbd.pollers[-1]
        # The mounted doer is the package client doer (not the retired Poller).
        assert client_doer.__class__.__name__ == "MailboxClientDoer"
        # Its on_message feeds the director's msgs deque as raw bytes.
        client_doer.client.on_message("/credential", b"AAAA-cesr")
        assert b"AAAA-cesr" in list(mbd.msgs)
    finally:
        hby.close()


def test_db_tops_cursor_store_round_trips():
    hby = habbing.Habery(name="curs", temp=True,
                         salt=signing.Salter(raw=b'0123456789abcdef').qb64)
    try:
        hab = hby.makeHab(name="svc")
        cs = DbTopsCursorStore(hby.db, hab.pre)
        assert cs.get("BWan", "/credential") is None
        cs.set("BWan", "/credential", 3)
        assert cs.get("BWan", "/credential") == 3
    finally:
        hby.close()
