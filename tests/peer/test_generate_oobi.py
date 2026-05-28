from unittest.mock import MagicMock

from locksmith.core import habbing


def test_generate_oobi_peer_role_with_tcp_endpoint():
    """When an AID has a witness-served tcp peer endpoint, generate_oobi
    returns the witness-served URL with role=peer.
    """
    hab = MagicMock()
    hab.pre = "EAID_ALICE"
    # fetchRoleUrls returns {role: {eid: {scheme: url}}}
    hab.fetchRoleUrls.return_value = {
        "peer": {
            "EWIT1": {
                "http": "http://witness.keri.host:5642"
            }
        }
    }

    app = MagicMock()
    result = habbing.generate_oobi(app, hab, role="peer")

    assert result["success"] is True
    assert result["oobi"].endswith("/oobi/EAID_ALICE/peer/EWIT1")
    assert "http://witness.keri.host" in result["oobi"]


def test_generate_oobi_peer_role_no_authorization_returns_failure():
    hab = MagicMock()
    hab.pre = "EAID_ALICE"
    hab.fetchRoleUrls.return_value = {}

    app = MagicMock()
    result = habbing.generate_oobi(app, hab, role="peer")

    assert result["success"] is False
    assert result["oobi"] is None
