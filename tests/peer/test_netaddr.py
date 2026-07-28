"""Primary-interface address discovery for the peer listener's advertised host."""
import ipaddress
import socket

import pytest

from locksmith.peer import netaddr


def test_detect_primary_host_returns_a_routable_ipv4_or_none():
    """Real call, no mocks: on a host with a default route this returns the
    address of the interface that route uses; on an isolated host it returns
    None. It must NEVER return a loopback or wildcard address — those are
    exactly the values that make an advertised endpoint undialable."""
    got = netaddr.detect_primary_host()
    if got is None:
        return
    addr = ipaddress.ip_address(got)
    assert not addr.is_loopback
    assert not addr.is_unspecified


def test_detect_primary_host_returns_none_when_there_is_no_route(monkeypatch):
    def _boom(*a, **kw):
        raise OSError("network is unreachable")

    monkeypatch.setattr(socket.socket, "connect", _boom)
    assert netaddr.detect_primary_host() is None


def test_env_override_wins_over_detection(monkeypatch):
    monkeypatch.setenv(netaddr.ADVERTISED_HOST_ENV_VAR, "100.64.0.7")
    monkeypatch.setattr(netaddr, "detect_primary_host", lambda: "192.168.1.20")
    assert netaddr.resolve_advertised_host() == "100.64.0.7"


def test_brand_override_wins_over_detection(monkeypatch):
    monkeypatch.delenv(netaddr.ADVERTISED_HOST_ENV_VAR, raising=False)
    monkeypatch.setattr(netaddr, "_brand_advertised_host", lambda: "hoa.internal")
    monkeypatch.setattr(netaddr, "detect_primary_host", lambda: "192.168.1.20")
    assert netaddr.resolve_advertised_host() == "hoa.internal"


def test_env_override_wins_over_brand(monkeypatch):
    monkeypatch.setenv(netaddr.ADVERTISED_HOST_ENV_VAR, "100.64.0.7")
    monkeypatch.setattr(netaddr, "_brand_advertised_host", lambda: "hoa.internal")
    assert netaddr.resolve_advertised_host() == "100.64.0.7"


def test_detected_primary_host_is_used_when_no_override(monkeypatch):
    monkeypatch.delenv(netaddr.ADVERTISED_HOST_ENV_VAR, raising=False)
    monkeypatch.setattr(netaddr, "_brand_advertised_host", lambda: "")
    monkeypatch.setattr(netaddr, "detect_primary_host", lambda: "192.168.1.20")
    assert netaddr.resolve_advertised_host() == "192.168.1.20"


def test_falls_back_to_loopback_when_nothing_is_detectable(monkeypatch):
    monkeypatch.delenv(netaddr.ADVERTISED_HOST_ENV_VAR, raising=False)
    monkeypatch.setattr(netaddr, "_brand_advertised_host", lambda: "")
    monkeypatch.setattr(netaddr, "detect_primary_host", lambda: None)
    assert netaddr.resolve_advertised_host() == "127.0.0.1"


@pytest.mark.parametrize("bad", ["", "   ", "0.0.0.0", "::"])
def test_unusable_override_values_are_ignored(monkeypatch, bad):
    """A wildcard or blank override means nothing to a remote peer; it must
    not shadow a perfectly good detected address."""
    monkeypatch.setenv(netaddr.ADVERTISED_HOST_ENV_VAR, bad)
    monkeypatch.setattr(netaddr, "_brand_advertised_host", lambda: "")
    monkeypatch.setattr(netaddr, "detect_primary_host", lambda: "192.168.1.20")
    assert netaddr.resolve_advertised_host() == "192.168.1.20"
