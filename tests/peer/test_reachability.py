"""Tests for the peer-mode reachability self-test helper.

The helper runs after the listener restarts: dial out to the advertised
host:port and confirm we can actually reach what we just told peers to
expect. Catches NAT/firewall/DNS misconfiguration at config-time rather
than at first-pair-time.
"""
from __future__ import annotations

import socket

import pytest

from locksmith.peer.reachability import ReachabilityResult, check_reachable


def _bind_random_port() -> tuple[socket.socket, int]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s, s.getsockname()[1]


def test_reachable_when_listener_accepts():
    server, port = _bind_random_port()
    try:
        result = check_reachable("127.0.0.1", port, timeout=0.5)
        assert isinstance(result, ReachabilityResult)
        assert result.ok is True
        assert result.reason == "ok"
    finally:
        server.close()


def test_refused_when_nothing_listening():
    # Pick a port unlikely to be in use; if it ever is, the test will
    # spuriously pass — accept that since refusal is the more interesting
    # negative signal and the chance is negligible.
    result = check_reachable("127.0.0.1", 1, timeout=0.5)
    assert result.ok is False
    assert result.reason == "refused"
    assert "nothing" in result.message.lower() or "listening" in result.message.lower()


def test_timeout_when_unroutable():
    # TEST-NET-1 (RFC 5737) — guaranteed unreachable.
    result = check_reachable("192.0.2.1", 12345, timeout=0.3)
    assert result.ok is False
    assert result.reason in ("timeout", "unreachable")
    # Either "timed out" or "unreachable" wording is acceptable.
    assert any(w in result.message.lower() for w in ("time", "unreach", "firewall"))


def test_dns_failure_named_clearly():
    result = check_reachable("this-host-does-not-exist.invalid", 12345, timeout=0.5)
    assert result.ok is False
    assert result.reason == "dns_failure"
    assert "resolve" in result.message.lower() or "dns" in result.message.lower()


def test_empty_host_rejected():
    """Caller invariant: don't call this with an empty host. Helper should
    return a clear error rather than dialing 0.0.0.0 or raising."""
    result = check_reachable("", 5621, timeout=0.5)
    assert result.ok is False
    assert result.reason == "invalid_host"
