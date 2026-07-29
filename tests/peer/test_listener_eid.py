"""The vault's peer listener gets its own EID.

The thing a peer dials is a per-vault socket, not an AID. So the endpoint
identifier has to be its own identifier, authorized by each AID that wants to be
reachable there — the shape KERI already uses for witnesses and mailboxes.

These tests run against a real Habery: the constraints being pinned here
(non-transferable so the signature verifies without a KEL, `ns="peer"` so the
listener never shows up as a user identity) are keripy's, not ours, and a mock
would assert nothing about them.
"""
from __future__ import annotations

import pytest
from keri import Vrsn_1_0
from keri.app import habbing

from locksmith.peer.listener_eid import (
    PEER_LISTENER_ALIAS, PEER_NS, ensure_listener_hab, listener_eid,
)


@pytest.fixture()
def hby():
    with habbing.openHby(name="lsn", temp=True, version=Vrsn_1_0) as h:
        yield h


def test_mints_a_listener_hab_when_none_exists(hby):
    hab = ensure_listener_hab(hby)
    assert hab is not None
    assert hab.pre


def test_listener_is_non_transferable(hby):
    """Not a style choice — a requirement.

    ``/loc/scheme`` is authenticated as coming from the *eid* itself
    (``processReplyLocScheme`` sets ``aid = eid``), while ``replyEndRole`` never
    replays the eid's KEL. A transferable listener would attach indexed
    signatures the receiving wallet has no key state to verify, and the endpoint
    would silently fail to land. A non-transferable prefix carries its public key,
    so the attached cigar verifies standalone.
    """
    hab = ensure_listener_hab(hby)
    assert hab.kever.prefixer.transferable is False
    assert hab.pre.startswith("B")


def test_listener_lives_in_the_peer_namespace(hby):
    """The listener is infrastructure, not an identity the user manages.

    The Identifiers page enumerates ``db.names`` and skips everything whose
    namespace isn't "" (ui/vault/identifiers/list.py), so the namespace is what
    keeps a socket out of the user's identifier list.
    """
    ensure_listener_hab(hby)
    namespaces = {ns for (ns, _alias), _pre in hby.db.names.getTopItemIter(keys=())}
    assert PEER_NS in namespaces
    assert PEER_NS != ""
    assert hby.habByName(PEER_LISTENER_ALIAS, ns=PEER_NS) is not None


def test_is_idempotent_and_stable_across_calls(hby):
    """Re-minting on every publish would hand every peer a new EID and orphan
    every authorization already published."""
    first = ensure_listener_hab(hby)
    second = ensure_listener_hab(hby)
    assert first.pre == second.pre


def test_listener_eid_reports_none_before_minting(hby):
    """Callers on the read path must be able to ask without creating one —
    a vault that has never exposed anything has no listener."""
    assert listener_eid(hby) is None
    hab = ensure_listener_hab(hby)
    assert listener_eid(hby) == hab.pre


def test_a_second_alias_mints_a_second_distinct_eid(hby):
    """Multi-route needs multi-EID: db.locs is keyed (eid, scheme), so a second
    tcp route is only expressible as a second EID. Nothing here may assume one
    listener per vault (backlog/2026-07-28-single-route-per-peer.md)."""
    first = ensure_listener_hab(hby)
    second = ensure_listener_hab(hby, alias="peer-listener-overlay")
    assert second.pre != first.pre
    assert second.kever.prefixer.transferable is False
