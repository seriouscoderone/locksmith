import os
import sys

import certifi

from locksmith.main import parse_vault_arg, parse_window_pos, _bootstrap_ssl_certs


def test_parse_vault_arg_present():
    assert parse_vault_arg(["prog", "--vault", "treasurer"]) == "treasurer"


def test_parse_vault_arg_absent():
    assert parse_vault_arg(["prog"]) is None


def test_parse_vault_arg_ignores_trailing_flag_without_value():
    assert parse_vault_arg(["prog", "--vault"]) is None


def test_parse_window_pos_present():
    assert parse_window_pos(["prog", "--win-pos", "120,340"]) == (120, 340)


def test_parse_window_pos_absent():
    assert parse_window_pos(["prog"]) is None


def test_parse_window_pos_malformed_returns_none():
    assert parse_window_pos(["prog", "--win-pos", "nope"]) is None
    assert parse_window_pos(["prog", "--win-pos"]) is None


def test_bootstrap_ssl_certs_sets_cert_file_when_frozen(monkeypatch):
    """Frozen app with no caller-set SSL_CERT_FILE -> points OpenSSL at certifi's
    bundled CA file, so the default ssl context (keri/hio TLS) can verify certs."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    _bootstrap_ssl_certs()
    assert os.environ.get("SSL_CERT_FILE") == certifi.where()


def test_bootstrap_ssl_certs_noop_when_not_frozen(monkeypatch):
    """Source checkout (not frozen): leave the env alone — system CA paths are valid."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    _bootstrap_ssl_certs()
    assert "SSL_CERT_FILE" not in os.environ


def test_bootstrap_ssl_certs_does_not_override_caller_value(monkeypatch):
    """A caller/user-set SSL_CERT_FILE must win (setdefault, not override)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("SSL_CERT_FILE", "/custom/ca.pem")
    _bootstrap_ssl_certs()
    assert os.environ["SSL_CERT_FILE"] == "/custom/ca.pem"
