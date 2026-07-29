from unittest.mock import MagicMock, patch

from locksmith.peer.records import PeerModeSettings
from locksmith.peer.shim import PeerExchangerShim

SENDER = "E" + "S" * 43
DEST = "E" + "D" * 43
# The sender's endpoint provider — its vault's peer listener, a separate
# non-transferable identifier, not the sender's own AID.
SENDER_EID = "B" + "S" * 43


def _exn(sender=SENDER, dest=DEST):
    serder = MagicMock()
    serder.ked = {"i": sender, "rp": dest, "a": {}}
    serder.said = "E" + "X" * 43
    return serder


def _shim(*, known=False, open_inbound=False, kel_known=True, has_loc=True,
          has_end=True, on_first_contact=None):
    allowlist = MagicMock()
    allowlist.contains.return_value = known
    hby = MagicMock()
    hby.kevers = {SENDER: object()} if kel_known else {}
    # The first-contact gate resolves the sender's endpoint natively:
    # cid -> ends[peer] -> eid -> locs[eid]. Both stores are faked because BOTH
    # halves are required — an address with no authorization behind it must not
    # get a stranger past this gate (see has_end=False below).
    end = MagicMock(); end.enabled = True; end.allowed = None
    hby.db.ends.getTopItemIter.return_value = (
        [((SENDER, "peer", SENDER_EID), end)] if has_end else [])
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


def test_first_contact_requires_the_address_to_be_authorized():
    """A location with no /end/role behind it must not admit a stranger.

    That state is reachable without any malice: a stream damaged mid-flight can
    land the /loc/scheme and drop the /end/role/add. The gate used to read
    db.locs directly and would have accepted the sender at an address nothing
    vouched for.
    """
    shim, exchanger, _ = _shim(open_inbound=True, has_end=False)
    shim.processEvent(_exn())
    exchanger.processEvent.assert_not_called()


def test_allowlisted_sender_skips_first_contact_path():
    called = []
    shim, exchanger, _ = _shim(known=True, open_inbound=True,
                               on_first_contact=lambda a, u: called.append(a))
    shim.processEvent(_exn())
    assert called == []
    exchanger.processEvent.assert_called_once()


def test_first_contact_registration_failure_does_not_propagate():
    """Finding 1 (final-review wave): a DB-write failure inside
    Vault._register_first_contact_peer (e.g. PeerAllowlist(...).add()
    raising) must be guarded there -- it must NOT propagate up through
    PeerExchangerShim.processEvent, the inbound parser hot path. On
    failure the vault logs and emits a "registration_failed" doer event;
    the exn is effectively rejected (never landed in the allowlist), which
    is safe since the sender can just retry."""
    from locksmith.core import vaulting

    class _FakeVault:
        def __init__(self):
            self.db = MagicMock()
            self.org = MagicMock()
            self.signals = MagicMock()

    fake_vault = _FakeVault()

    def on_first_contact(aid, url):
        vaulting.Vault._register_first_contact_peer(fake_vault, aid, url)

    with patch("locksmith.core.vaulting.PeerAllowlist") as mock_allowlist_cls:
        mock_allowlist_cls.return_value.add.side_effect = RuntimeError("db write failed")

        shim, exchanger, _ = _shim(open_inbound=True, on_first_contact=on_first_contact)

        # Must not raise -- the guard swallows the allowlist-add failure.
        shim.processEvent(_exn())

    # The parser still delivered the event (first-contact was "accepted"
    # at the shim level; the registration failure is a best-effort side
    # channel, not a delivery gate).
    exchanger.processEvent.assert_called_once()
    # org.update was never reached -- the allowlist add raised first.
    fake_vault.org.update.assert_not_called()
    fake_vault.signals.emit_doer_event.assert_called_once_with(
        "PeerFirstContact", "registration_failed",
        {"aid": SENDER, "error": "db write failed"})
