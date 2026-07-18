from unittest.mock import MagicMock

from locksmith.peer.records import PeerModeSettings
from locksmith.peer.shim import PeerExchangerShim

SENDER = "E" + "S" * 43
DEST = "E" + "D" * 43


def _exn(sender=SENDER, dest=DEST):
    serder = MagicMock()
    serder.ked = {"i": sender, "rp": dest, "a": {}}
    serder.said = "E" + "X" * 43
    return serder


def _shim(*, known=False, open_inbound=False, kel_known=True, has_loc=True,
          on_first_contact=None):
    allowlist = MagicMock()
    allowlist.contains.return_value = known
    hby = MagicMock()
    hby.kevers = {SENDER: object()} if kel_known else {}
    loc = MagicMock(); loc.url = "tcp://127.0.0.1:5621"
    hby.db.locs.get.return_value = loc if has_loc else None
    exchanger = MagicMock()
    shim = PeerExchangerShim(
        allowlist, exchanger, lambda aid: True,
        hby=hby, open_inbound=open_inbound, on_first_contact=on_first_contact,
    )
    return shim, exchanger, allowlist


def test_default_open_inbound_is_false():
    assert PeerModeSettings().open_inbound is False


def test_unknown_sender_still_rejected_when_off():
    shim, exchanger, _ = _shim(known=False, open_inbound=False)
    shim.processEvent(_exn())
    exchanger.processEvent.assert_not_called()


def test_first_contact_registers_and_delivers():
    seen = {}
    shim, exchanger, _ = _shim(
        open_inbound=True, on_first_contact=lambda a, u: seen.update(aid=a, url=u))
    shim.processEvent(_exn())
    assert seen == {"aid": SENDER, "url": "tcp://127.0.0.1:5621"}
    exchanger.processEvent.assert_called_once()


def test_first_contact_requires_verifiable_kel():
    shim, exchanger, _ = _shim(open_inbound=True, kel_known=False)
    shim.processEvent(_exn())
    exchanger.processEvent.assert_not_called()


def test_first_contact_requires_tcp_loc():
    shim, exchanger, _ = _shim(open_inbound=True, has_loc=False)
    shim.processEvent(_exn())
    exchanger.processEvent.assert_not_called()


def test_allowlisted_sender_skips_first_contact_path():
    called = []
    shim, exchanger, _ = _shim(known=True, open_inbound=True,
                               on_first_contact=lambda a, u: called.append(a))
    shim.processEvent(_exn())
    assert called == []
    exchanger.processEvent.assert_called_once()
