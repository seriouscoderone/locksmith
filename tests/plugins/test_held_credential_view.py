from types import SimpleNamespace
from unittest.mock import MagicMock
from locksmith.plugins.manager import PluginManager, HeldCredential


def _reger(et, dt):
    reger = MagicMock()
    creder = SimpleNamespace(schema="ESCHEMA", issuer="EISSUER", regid="EREG")
    reger.creds.get.return_value = creder
    reger.saved.get.return_value = object()   # chain_verified True
    status = SimpleNamespace(et=et, dt=dt)
    reger.tevers = {"EREG": SimpleNamespace(vcState=lambda said: status)}
    return reger


def test_view_carries_revoked_at_when_revoked():
    reger = _reger("rev", "2026-07-19T12:00:00.000000+00:00")
    view = PluginManager._held_credential_view(reger, "ESAID")
    assert view.state == "revoked"
    assert view.revoked_at == "2026-07-19T12:00:00.000000+00:00"


def test_view_revoked_at_empty_when_active():
    reger = _reger("iss", "2026-07-19T12:00:00.000000+00:00")
    view = PluginManager._held_credential_view(reger, "ESAID")
    assert view.state == "active"
    assert view.revoked_at == ""


def test_held_credential_defaults_revoked_at_empty():
    hc = HeldCredential(schema_said="E", issuer_aid="E", state="active",
                        chain_verified=True, said="E")
    assert hc.revoked_at == ""
