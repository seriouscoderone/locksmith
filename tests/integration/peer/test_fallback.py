"""Integration test — peer_send auto-fallback to mailbox.

A is paired with a fake B endpoint pointing at an unreachable port.
A drives peer_send; connect fails; the stub mailbox callback is hit.
Asserts outcome=peer→mailbox and the structured logs reflect both the
peer attempt and the mailbox fallback.
"""
import socket
import time

import pytest

from tests.integration.peer.conftest import (
    create_aid_via_ui, expose_aid_via_ui, free_port,
    open_test_vault_via_ui, set_peer_mode_via_ui,
)


def _free_port():
    return free_port()


@pytest.mark.integration
def test_peer_send_falls_back_to_mailbox_when_peer_unreachable(two_wallets):
    devctl = two_wallets["devctl"]
    a = two_wallets["a"]

    open_test_vault_via_ui(devctl, a["sock"], name="ptest")
    create_aid_via_ui(devctl, a["sock"], alias="alice")
    set_peer_mode_via_ui(devctl, a["sock"], port=free_port())
    expose_aid_via_ui(devctl, a["sock"], "alice")

    # Pair Alice with a fake AID at an unbound port.
    bad_port = _free_port()
    fake_aid = "EFAKE_BOB_FOR_FALLBACK_TEST_" + "A" * 16
    r = devctl(a["sock"], "peer_force_pair",
               aid=fake_aid,
               endpoint_url=f"tcp://127.0.0.1:{bad_port}",
               label="UnreachableBob")
    assert r.get("ok") is True

    r = devctl(a["sock"], "peer_test_send",
               recipient_aid=fake_aid, payload="will-fallback")
    assert r.get("ok") is True
    assert r["outcome"] == "peer→mailbox", r
    # JSON-roundtrips tuples to lists
    assert r["mailbox_calls"] == [[fake_aid, len(b"will-fallback")]]

    time.sleep(0.5)
    log_a = a["log"].read_text()
    assert "peer.send.attempt" in log_a
    assert "peer.send.peer_failed" in log_a
    assert "peer.send.fallback_mailbox" in log_a
