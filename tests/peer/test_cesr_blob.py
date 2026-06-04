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


def test_import_peer_blob_roundtrips_v1_kel():
    """Real-Habery round-trip: export a blob from a hab with peer role
    published, import into a fresh Habery, confirm the AID + tcp loc
    populate.

    Regression: Parser defaults to Vrsn_2_0. `hab.replyToOobi` serializes
    v1 events. Without `version=Vrsn_1_0`, Parser.allParsator loops
    forever inside the call — the dialog froze the wallet at 100% CPU.
    This test would hang (and fail the suite's timeout) without the fix.
    """
    from hio.base import doing
    from keri.app import habbing
    from keri.core import signing

    from locksmith.peer import publishing

    hby_export = habbing.Habery(
        name="exporter",
        bran="A" * 21,
        salt=signing.Salter(raw=b"export0123456789").qb64,
        temp=True,
    )
    hby_import = habbing.Habery(
        name="importer",
        bran="B" * 21,
        salt=signing.Salter(raw=b"import0123456789").qb64,
        temp=True,
    )
    try:
        hab = hby_export.makeHab(
            name="alice", isith="1", icount=1, transferable=True
        )

        # Publish peer role locally (no wits — skips the messenger path).
        from unittest.mock import patch
        with patch.object(publishing, "_witnesses_for", return_value=[]):
            doer = publishing.PublishPeerRoleDoer(
                hby=hby_export, hab=hab, url="tcp://127.0.0.1:5622",
                signal_bridge=None, allow=True,
            )
            doist = doing.Doist(limit=2.0, tock=0.03125, real=False)
            doist.do(doers=[doer])

        blob = export_peer_blob(hab)
        assert blob.startswith(BLOB_PREFIX)

        imported_pre = import_peer_blob(hby_import, blob)
        assert imported_pre == hab.pre

        loc = hby_import.db.locs.get(keys=(hab.pre, "tcp"))
        assert loc is not None
        assert loc.url == "tcp://127.0.0.1:5622"
    finally:
        hby_export.close()
        hby_import.close()


def test_import_peer_blob_returns_imported_aid_not_local_peer():
    """Regression: when the importer already has a LOCAL AID exposed for
    peer (its own AID with a tcp loc), import_peer_blob used to walk all
    hby.kevers and return whichever AID came first that had a peer-role
    tcp endpoint — often the importer's own. Demo bug: pairing reported
    success but with the wrong AID + wrong endpoint, so peer_send
    couldn't reach the actual remote.

    Fix: snapshot hby.kevers before parse, only consider freshly-added
    AIDs.
    """
    from hio.base import doing
    from keri.app import habbing
    from keri.core import signing
    from unittest.mock import patch

    from locksmith.peer import publishing

    # Importer has its own exposed AID at port 5621
    hby_importer = habbing.Habery(
        name="imp", bran="A" * 21,
        salt=signing.Salter(raw=b"importer01234567").qb64, temp=True,
    )
    # Exporter has alice exposed at port 5622
    hby_exporter = habbing.Habery(
        name="exp", bran="B" * 21,
        salt=signing.Salter(raw=b"exporter01234567").qb64, temp=True,
    )
    try:
        my_aid = hby_importer.makeHab(name="me", isith="1", icount=1, transferable=True)
        their_aid = hby_exporter.makeHab(name="alice", isith="1", icount=1, transferable=True)

        # Publish peer role for both, on their own habs.
        with patch.object(publishing, "_witnesses_for", return_value=[]):
            for hby, hab, url in [
                (hby_importer, my_aid, "tcp://127.0.0.1:5621"),
                (hby_exporter, their_aid, "tcp://127.0.0.1:5622"),
            ]:
                doer = publishing.PublishPeerRoleDoer(
                    hby=hby, hab=hab, url=url, signal_bridge=None, allow=True,
                )
                doing.Doist(limit=2.0, tock=0.03125, real=False).do(doers=[doer])

        blob = export_peer_blob(their_aid)
        imported = import_peer_blob(hby_importer, blob)

        assert imported == their_aid.pre, (
            f"Expected to import remote {their_aid.pre}, got local "
            f"{my_aid.pre}"
        )
    finally:
        hby_importer.close()
        hby_exporter.close()


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
