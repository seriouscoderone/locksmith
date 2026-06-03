"""Tests for the peer exposure read-side helpers (the source of truth
queried by the UI banner, the toggle initial state, and the toolbar
indicator)."""
from __future__ import annotations

import pytest


@pytest.fixture
def hby():
    from keri.app import habbing
    from keri.core import signing
    h = habbing.Habery(
        name="exposetest", bran="A" * 21,
        salt=signing.Salter(raw=b"0123456789abcdef").qb64, temp=True,
    )
    try:
        yield h
    finally:
        h.close()


def test_no_exposure_when_no_rpy_published(hby):
    from locksmith.peer.exposure import (
        count_exposed, exposed_pres, is_aid_peer_exposed,
    )
    hab = hby.makeHab(name="alice", isith="1", icount=1, transferable=True)
    assert is_aid_peer_exposed(hby, hab.pre) is False
    assert exposed_pres(hby) == []
    assert count_exposed(hby) == 0


def test_exposure_recorded_after_role_rpy_lands(hby):
    """Drive PublishPeerRoleDoer's local parse-back path; afterward,
    the helper should see the AID as exposed.
    """
    from hio.base import doing
    from locksmith.peer.exposure import (
        count_exposed, exposed_pres, is_aid_peer_exposed,
    )
    from locksmith.peer.publishing import PublishPeerRoleDoer

    hab = hby.makeHab(name="bob", isith="1", icount=1, transferable=True)
    # No witnesses → doer takes the local-only branch, parses rpys back
    # into hab.db.ends without trying to send. That's exactly what we
    # want here: confirm db.ends sees the entry.
    doer = PublishPeerRoleDoer(
        hby=hby, hab=hab, url="tcp://127.0.0.1:5621", allow=True,
    )
    doist = doing.Doist(limit=1.0, tock=0.03125, real=False)
    doist.do(doers=[doer])

    assert is_aid_peer_exposed(hby, hab.pre) is True
    assert exposed_pres(hby) == [hab.pre]
    assert count_exposed(hby) == 1


def test_exposure_cleared_after_revoke(hby):
    from hio.base import doing
    from locksmith.peer.exposure import is_aid_peer_exposed
    from locksmith.peer.publishing import PublishPeerRoleDoer

    hab = hby.makeHab(name="charlie", isith="1", icount=1, transferable=True)
    # Expose
    doer = PublishPeerRoleDoer(
        hby=hby, hab=hab, url="tcp://127.0.0.1:5621", allow=True,
    )
    doing.Doist(limit=1.0, tock=0.03125, real=False).do(doers=[doer])
    assert is_aid_peer_exposed(hby, hab.pre) is True

    # Revoke (allow=False) — publishes /end/role/cut
    revoke = PublishPeerRoleDoer(
        hby=hby, hab=hab, url="", allow=False,
    )
    doing.Doist(limit=1.0, tock=0.03125, real=False).do(doers=[revoke])
    assert is_aid_peer_exposed(hby, hab.pre) is False


def test_is_aid_peer_exposed_handles_missing_hab(hby):
    from locksmith.peer.exposure import is_aid_peer_exposed
    assert is_aid_peer_exposed(hby, "EAID_NEVER_EXISTED") is False
