from unittest.mock import MagicMock

from locksmith.core import habbing


def test_generate_oobi_peer_role_uses_witness_serving():
    """The peer-role OOBI URL is witness-served (spec §4a.i). The witness
    hostname is used to address the server, but the eid in the URL path
    is the controller's own AID — not the witness — because in peer mode
    the controller IS the endpoint provider, and that's the eid carried
    in the /end/role/add rpy that PublishPeerRoleDoer publishes.
    """
    hab = MagicMock()
    hab.pre = "EAID_ALICE"
    hab.kever.wits = ["BWIT1"]
    hab.fetchUrls.return_value = {"http": "http://witness.keri.host:5642"}

    app = MagicMock()
    result = habbing.generate_oobi(app, hab, role="peer")

    assert result["success"] is True
    assert result["oobi"].endswith("/oobi/EAID_ALICE/peer/EAID_ALICE")
    assert "http://witness.keri.host" in result["oobi"]


def test_generate_oobi_peer_role_with_no_witness_returns_failure():
    """No witness means no host to serve the OOBI — gracefully fails."""
    hab = MagicMock()
    hab.pre = "EAID_ALICE"
    hab.kever.wits = []

    app = MagicMock()
    result = habbing.generate_oobi(app, hab, role="peer")

    assert result["success"] is False
    assert result["oobi"] is None
