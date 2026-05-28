"""Witness-less peer-OOBI blob — export/import round-trip."""
import base64
from unittest.mock import MagicMock

import pytest

from locksmith.peer.cesr_blob import (
    BLOB_PREFIX,
    PeerBlobError,
    export_peer_blob,
    import_peer_blob,
    is_peer_blob,
)


def test_is_peer_blob_recognizes_prefix():
    assert is_peer_blob(f"{BLOB_PREFIX}abc==")
    assert is_peer_blob(f"  {BLOB_PREFIX}abc==  ")  # whitespace tolerated
    assert not is_peer_blob("https://witness.example.com/oobi/EAID/peer/EWIT")
    assert not is_peer_blob("")


def test_export_peer_blob_uses_replyToOobi():
    """export_peer_blob delegates to hab.replyToOobi for the peer role."""
    hab = MagicMock()
    hab.pre = "EAID_ALICE"
    fake_cesr = b"FAKE-CESR-EVENTS-AND-ROLE-AUTH"
    hab.replyToOobi.return_value = fake_cesr

    token = export_peer_blob(hab)
    assert token.startswith(BLOB_PREFIX)
    decoded = base64.b64decode(token[len(BLOB_PREFIX):])
    assert decoded == fake_cesr
    hab.replyToOobi.assert_called_once()
    # First positional or keyword `aid` argument should be the controller pre
    call = hab.replyToOobi.call_args
    assert call.kwargs.get("aid") == "EAID_ALICE"


def test_export_peer_blob_empty_raises():
    hab = MagicMock()
    hab.pre = "EAID_ALICE"
    hab.replyToOobi.return_value = b""

    with pytest.raises(ValueError, match="not exposed"):
        export_peer_blob(hab)


def test_import_peer_blob_rejects_bad_prefix():
    hby = MagicMock()
    with pytest.raises(PeerBlobError) as exc:
        import_peer_blob(hby, "https://witness.example.com/oobi/EAID/peer/EWIT")
    assert exc.value.reason == "bad_prefix"


def test_import_peer_blob_rejects_bad_base64():
    hby = MagicMock()
    with pytest.raises(PeerBlobError) as exc:
        import_peer_blob(hby, f"{BLOB_PREFIX}not!!!!valid!!!base64")
    assert exc.value.reason == "bad_base64"


def test_import_peer_blob_no_peer_endpoint_raises(tmp_path):
    """Parser runs but no AID has a peer-role tcp endpoint in locs.
    Uses a real Habery so the Revery/Kevery wiring inside import_peer_blob
    can actually run.
    """
    from keri.app import habbing
    from keri.core import signing

    hby = habbing.Habery(
        name="blobtest",
        bran="A" * 21,
        salt=signing.Salter(raw=b"0123456789abcdef").qb64,
        temp=True,
    )
    try:
        # An empty (non-CESR) payload parses to nothing — no AID is
        # added to kevers, so the post-parse "find a peer-tcp endpoint"
        # check fails.
        payload = base64.b64encode(b"").decode("ascii")
        blob = f"{BLOB_PREFIX}{payload}"
        with pytest.raises(PeerBlobError) as exc:
            import_peer_blob(hby, blob)
        assert exc.value.reason == "no_peer_role"
    finally:
        hby.close()
