import logging
from types import SimpleNamespace

from datetime import datetime, timezone

from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.records import PeerRecord
from locksmith.peer.shim import PeerExchangerShim


def _exn(sender="EAID_BOB", recipient="EAID_ALICE"):
    return SimpleNamespace(
        ked={"i": sender, "rp": recipient},
        said="SAID_FAKE",
    )


class _RecordingExchanger:
    def __init__(self):
        self.calls = []

    def processEvent(self, serder, tsgs=None, cigars=None, **kwargs):
        self.calls.append((serder, tsgs, cigars, kwargs))


def test_paired_sender_to_opted_in_destination_forwards(baser, caplog):
    al = PeerAllowlist(baser)
    al.add(PeerRecord(aid="EAID_BOB", label="Bob", endpoint_url="tcp://x:5621",
                      paired_at=datetime.now(timezone.utc).isoformat()))
    exchanger = _RecordingExchanger()
    shim = PeerExchangerShim(allowlist=al, exchanger=exchanger,
                             is_destination_exposed=lambda aid: aid == "EAID_ALICE")

    with caplog.at_level(logging.INFO, logger="locksmith.peer.shim"):
        shim.processEvent(_exn(), tsgs=None, cigars=None)

    assert len(exchanger.calls) == 1
    assert any("peer.recv.delivered" in r.message for r in caplog.records)


def test_non_exn_payload_is_discarded(baser, caplog):
    al = PeerAllowlist(baser)
    exchanger = _RecordingExchanger()
    shim = PeerExchangerShim(allowlist=al, exchanger=exchanger,
                             is_destination_exposed=lambda aid: True)

    class _Garbage:
        said = "GARBAGE"
        # No `ked` attribute -> AttributeError on access

    with caplog.at_level(logging.WARNING, logger="locksmith.peer.shim"):
        shim.processEvent(_Garbage())

    assert exchanger.calls == []
    assert any("peer.parser.discarded" in r.message for r in caplog.records)


def test_unknown_sender_is_dropped_and_logged(baser, caplog):
    al = PeerAllowlist(baser)
    exchanger = _RecordingExchanger()
    shim = PeerExchangerShim(allowlist=al, exchanger=exchanger,
                             is_destination_exposed=lambda aid: True)

    with caplog.at_level(logging.WARNING, logger="locksmith.peer.shim"):
        shim.processEvent(_exn(sender="EAID_MALLORY"))

    assert exchanger.calls == []
    assert any("peer.gate.sender_rejected" in r.message and "EAID_MALLORY" in r.message
               for r in caplog.records)


def test_ipex_exn_recipient_falls_back_to_attribute_block_i(baser, caplog):
    """keripy's ipexGrantExn (and the rest of the IPEX family) builds
    exn messages with rp="" and the actual recipient AID in the
    attribute block as a.i. The shim falls back to a.i when rp is
    empty so the destination-exposed gate sees the real recipient.
    """
    al = PeerAllowlist(baser)
    al.add(PeerRecord(aid="EAID_BOB", label="Bob", endpoint_url="tcp://x:5621",
                      paired_at=datetime.now(timezone.utc).isoformat()))
    exchanger = _RecordingExchanger()
    shim = PeerExchangerShim(allowlist=al, exchanger=exchanger,
                             is_destination_exposed=lambda aid: aid == "EAID_ALICE")

    # IPEX-shape exn: rp empty, recipient in a.i
    serder = SimpleNamespace(
        ked={"i": "EAID_BOB", "rp": "", "a": {"i": "EAID_ALICE", "m": "hi"}},
        said="SAID_FAKE",
    )
    with caplog.at_level(logging.INFO, logger="locksmith.peer.shim"):
        shim.processEvent(serder)

    assert len(exchanger.calls) == 1, (
        "shim should deliver to the exchanger when a.i names an exposed "
        "destination, even though rp is empty"
    )
    assert any("peer.recv.delivered" in r.message for r in caplog.records)


def test_paired_sender_to_unexposed_destination_is_dropped_and_logged(baser, caplog):
    al = PeerAllowlist(baser)
    al.add(PeerRecord(aid="EAID_BOB", label="Bob", endpoint_url="tcp://x:5621",
                      paired_at=datetime.now(timezone.utc).isoformat()))
    exchanger = _RecordingExchanger()
    shim = PeerExchangerShim(allowlist=al, exchanger=exchanger,
                             is_destination_exposed=lambda aid: False)

    with caplog.at_level(logging.WARNING, logger="locksmith.peer.shim"):
        shim.processEvent(_exn())

    assert exchanger.calls == []
    assert any("peer.gate.destination_not_exposed" in r.message for r in caplog.records)
