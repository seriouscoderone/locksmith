"""admitDo's outbound-attachment selection (`_send_attachment`).

The admit-send path must reuse the builder's complete, CESR-quadlet-aligned
attachment for a single-sig hab — the same way the grant-send path does — rather
than re-fetching it via `exchanging.serializeMessage(...)` and chopping the serder
off the front. That re-fetch was doubly broken: it returned a `(None, None)` tuple
when the exn wasn't in the db (crash: "'tuple' object does not support item
deletion") and could yield a non-quadlet-aligned attachment (crash: "Invalid
attachments size=NNN, nonintegral quadlets"). See ipexing.py:809-810.
"""
from keri.app import habbing
from keri.vc import protocoling

from locksmith.core.ipexing import _send_attachment


def test_single_sig_admit_send_uses_aligned_builder_attachment():
    with habbing.openHby(name="t_admit_send", temp=True) as hby:
        hab = hby.makeHab(name="carrier")
        recp = hby.makeHab(name="doi").pre
        # any ipex builder returns (exn, atc); the helper is verb-agnostic
        exn, atc = protocoling.ipexApplyExn(hab=hab, recp=recp, message="",
                                            schema="E" + "A" * 43, attrs={})

        result = _send_attachment(hab, exn, bytearray(atc), hby)

        # uses the builder's attachment, not a re-fetch-and-chop
        assert bytes(result) == bytes(atc)
        # CESR quadlet-aligned (the old path could emit a non-aligned attachment)
        assert len(result) % 4 == 0
