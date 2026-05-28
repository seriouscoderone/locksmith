"""Smoke test: verify the two-wallet fixture brings both processes up
and both dev-control sockets answer a ping."""
import pytest


@pytest.mark.integration
def test_both_wallets_respond_to_ping(two_wallets):
    devctl = two_wallets["devctl"]
    pong_a = devctl(two_wallets["a"]["sock"], "ping")
    pong_b = devctl(two_wallets["b"]["sock"], "ping")
    assert pong_a.get("ok") is True
    assert pong_b.get("ok") is True
