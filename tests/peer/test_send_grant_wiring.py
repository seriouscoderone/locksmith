"""Regression guard for the SendGrantDoer → PeerAwarePoster wire-up.

A full schema-and-registry-backed live IPEX test deserves its own
fixture work; this test instead pins the *wire-up* that lets that flow
choose the peer channel at all. If someone later swaps the postman for
``forwarding.StreamPoster`` (the keripy default), the signal payload
would silently lose the channel field and the credential-sent toast
would stop reflecting transport reality.

We assert at two levels:

  1. Source-level — SendGrantDoer.sendGrantDo constructs PeerAwarePoster,
     reads ``postman.last_outcome`` for the channel, and emits a
     ``channel`` field on the success signal.

  2. Behavioral — PeerAwarePoster.deliver() returns 'peer' when a
     reachable PeerRecord is present, 'mailbox' when no record exists,
     and 'peer→mailbox' on connection failure. (Already covered in
     test_posting.py — this test ties those outcomes to the value
     SendGrantDoer ends up signaling.)
"""
from __future__ import annotations

import inspect

from locksmith.core import ipexing
from locksmith.peer.posting import PeerAwarePoster
from locksmith.peer.sending import SendOutcome


def test_send_grant_constructs_peer_aware_poster():
    src = inspect.getsource(ipexing.SendGrantDoer.sendGrantDo)
    # The peer-channel wire-up: must construct PeerAwarePoster, not
    # forwarding.StreamPoster (the keripy default that bypasses peer
    # discovery). The single-sig path is what runs for almost every
    # IPEX grant; lead-only branch checked here.
    assert "PeerAwarePoster(" in src, (
        "SendGrantDoer must instantiate PeerAwarePoster — otherwise "
        "credential grants silently skip the peer channel and always "
        "go through the mailbox."
    )


def test_send_grant_surfaces_channel_on_success_signal():
    """The success signal must carry a `channel` field derived from
    postman.last_outcome. Removing this would break the channel badge
    in the Issue Credential success toast (the user-visible signal that
    direct peer transport is working)."""
    src = inspect.getsource(ipexing.SendGrantDoer.sendGrantDo)
    assert "last_outcome" in src, (
        "SendGrantDoer must read postman.last_outcome — otherwise the "
        "channel badge is decoupled from the actual transport choice."
    )
    assert "'channel'" in src or '"channel"' in src, (
        "SendGrantDoer must emit a channel field on the success signal."
    )


def test_send_outcome_values_match_what_send_grant_signals():
    """SendOutcome enum is the source of truth for channel labels.
    SendGrantDoer reads .value off last_outcome; the strings here are
    what the UI eventually displays.
    """
    assert SendOutcome.PEER.value == "peer"
    assert SendOutcome.MAILBOX.value == "mailbox"
    assert SendOutcome.FALLBACK.value == "peer→mailbox"


def test_send_grant_passes_vault_baser_to_postman():
    """PeerAwarePoster needs the vault's LocksmithBaser (where peerAllowlist
    lives) to make the peer-vs-mailbox decision. Passing the wrong baser
    would silently always-fall-through to mailbox — a regression that
    would be very hard to spot from logs alone.
    """
    src = inspect.getsource(ipexing.SendGrantDoer.sendGrantDo)
    assert "baser=self.app.vault.db" in src, (
        "PeerAwarePoster must receive vault.db as `baser` so it can read "
        "the peerAllowlist Komer."
    )


def test_peer_aware_poster_is_a_drop_in_for_stream_poster():
    """The whole reason PeerAwarePoster exists is to wrap StreamPoster
    transparently — same `.send()` and `.deliver()` surface. If that
    drift, callers that haven't migrated would break or silently miss
    the peer path. Catch surface changes here.
    """
    assert hasattr(PeerAwarePoster, "send")
    assert hasattr(PeerAwarePoster, "deliver")
    # last_outcome is the new attribute the wire-up depends on; pin it.
    instance_attrs = [
        n for n in PeerAwarePoster.__init__.__code__.co_varnames
        if not n.startswith("_")
    ]
    # at minimum the constructor accepts hby + recp + baser
    assert "hby" in instance_attrs
    assert "recp" in instance_attrs
    assert "baser" in instance_attrs


def test_last_outcome_carries_each_send_outcome_through_deliver(baser):
    """SendGrantDoer reads ``postman.last_outcome.value`` to decide the
    channel label — pin that every code path through deliver() sets
    last_outcome to the matching enum value. If a future change makes
    deliver() leave last_outcome None for some path, the user-facing
    "channel=" log line silently falls back to 'mailbox'.
    """
    import socket
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import patch

    from locksmith.peer.allowlist import PeerAllowlist
    from locksmith.peer.records import PeerRecord

    def _serder():
        return SimpleNamespace(raw=b"FAKE", said="SAID", size=4)

    fake_hab = SimpleNamespace(
        kever=SimpleNamespace(prefixer=SimpleNamespace(qb64b=b""))
    )
    hby = SimpleNamespace(habs={}, db=SimpleNamespace())

    # --- mailbox path: no peer record ---
    poster = PeerAwarePoster(
        hby=hby, recp="EAID_NOREC", baser=baser, hab=fake_hab, topic="credential",
    )
    poster.send(serder=_serder())
    with patch.object(poster._inner, "deliver", return_value=[]):
        poster.deliver()
    assert poster.last_outcome is not None
    assert poster.last_outcome.value == "mailbox"

    # --- peer path: paired + reachable listener ---
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        PeerAllowlist(baser).add(PeerRecord(
            aid="EAID_REACHABLE", label="X",
            endpoint_url=f"tcp://127.0.0.1:{port}",
            paired_at=datetime.now(timezone.utc).isoformat(),
        ))
        poster = PeerAwarePoster(
            hby=hby, recp="EAID_REACHABLE", baser=baser, hab=fake_hab,
            topic="credential",
        )
        poster.send(serder=_serder())
        with patch.object(poster._inner, "deliver"):
            poster.deliver()
        assert poster.last_outcome.value == "peer"
    finally:
        server.close()

    # --- fallback path: paired but endpoint unreachable ---
    PeerAllowlist(baser).add(PeerRecord(
        aid="EAID_DEAD", label="Dead",
        endpoint_url="tcp://127.0.0.1:1",  # nothing listening
        paired_at=datetime.now(timezone.utc).isoformat(),
    ))
    poster = PeerAwarePoster(
        hby=hby, recp="EAID_DEAD", baser=baser, hab=fake_hab, topic="credential",
    )
    poster.send(serder=_serder())
    with patch.object(poster._inner, "deliver", return_value=[]):
        poster.deliver()
    assert poster.last_outcome.value == "peer→mailbox"


def test_send_grant_goes_loud_when_fallback_has_nowhere_to_deliver():
    """The silent-loss guard from the first live two-machine test
    (backlog/2026-07-29-grant-send-reports-success-while-undeliverable.md):
    when the channel is not "peer" AND the recipient has no mailbox/agent/
    witness ends, the fallback delivered nowhere — SendGrantDoer must emit
    send_failed (the grant dialog's error banner) instead of send_complete.
    The policy predicate is `locksmith.peer.posting.undeliverable`, shared
    verbatim with ServiceaidGrantDoer (behaviorally covered in
    tests/core/test_serviceaid_bridge.py); this pins the legacy doer's use
    of it."""
    src = inspect.getsource(ipexing.SendGrantDoer.sendGrantDo)
    assert "undeliverable(" in src, (
        "SendGrantDoer must consult the shared deliverability policy — "
        "otherwise an unreachable peer with no mailbox ends reports "
        "'sent successfully' while the grant went nowhere."
    )
    assert "send_failed" in src, (
        "SendGrantDoer must emit send_failed on the undeliverable path so "
        "the grant dialog surfaces a visible failure."
    )
    assert "recipient_label(" in src, (
        "The failure copy must name the peer (pairing label / contact "
        "alias) — an AID prefix is not operator-readable."
    )
