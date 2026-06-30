"""Vault.seed_kel_mailboxes — auto-seed db.mbx from each local AID's KEL-designated
mailbox (agenting.mailbox, role-first/witness-fallback), so the wallet polls the mailbox
the AID designated in its OWN KEL without a manual UI designation."""
from types import SimpleNamespace

from hio.base import doing
from keri.app import habbing
from keri.core import signing
from keri.kering import Roles
from keri.recording import EndpointRecord
from keri.vdr import credentialing

from locksmith.core import vaulting
from locksmith.db.basing import LocksmithBaser


class _NoTurret(doing.DoDoer):
    def __init__(self, *a, **k):
        super().__init__(doers=[])


def test_seed_kel_mailboxes_pins_designated_mailbox(monkeypatch, tmp_path):
    monkeypatch.setattr(vaulting, "LocksmithBaser",
                        lambda name, reopen=True: LocksmithBaser(
                            name=f"{name}-locksmith", headDirPath=str(tmp_path), reopen=reopen))
    monkeypatch.setattr(vaulting, "TurretDoer", _NoTurret)

    hby = habbing.Habery(name="vault-seed", temp=True,
                         salt=signing.Salter(raw=b'0123456789abcdef').qb64)
    rgy = credentialing.Regery(hby=hby, name=hby.name, temp=True)
    vault = None
    try:
        vault = vaulting.Vault(app=SimpleNamespace(), hby=hby, rgy=rgy)
        mbx_hab = hby.makeHab(name="mailbox-svc")               # the dedicated mailbox AID
        doi = hby.makeHab(name="state-doi")
        doi.db.ends.pin(keys=(doi.pre, Roles.mailbox, mbx_hab.pre),  # designate the mailbox
                        val=EndpointRecord(allowed=True))            # end-role (makeEndRole
        #                                                              alone doesn't persist to db.ends)

        vault.seed_kel_mailboxes()

        seeded = vault.db.mbx.get(keys=(mbx_hab.pre,))
        assert seeded is not None, "db.mbx was not seeded from the AID's KEL mailbox role"
        assert seeded.cid == doi.pre
        assert seeded.eid == mbx_hab.pre
    finally:
        if vault is not None:
            vault.db.close()
            vault.rep.mbx.close()
            vault.notifier.noter.close()
        rgy.close()
        hby.close()
