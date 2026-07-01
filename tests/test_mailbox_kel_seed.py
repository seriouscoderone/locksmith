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

        seeded = vault.db.mbx.get(keys=(doi.pre, mbx_hab.pre))
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


def test_seed_kel_mailboxes_skips_when_no_mailbox_resolves(monkeypatch, tmp_path):
    from keri.app import agenting

    monkeypatch.setattr(vaulting, "LocksmithBaser",
                        lambda name, reopen=True: LocksmithBaser(
                            name=f"{name}-locksmith", headDirPath=str(tmp_path), reopen=reopen))
    monkeypatch.setattr(vaulting, "TurretDoer", _NoTurret)

    hby = habbing.Habery(name="vault-skip", temp=True,
                         salt=signing.Salter(raw=b'abcdef0123456789').qb64)
    rgy = credentialing.Regery(hby=hby, name=hby.name, temp=True)
    vault = None
    try:
        vault = vaulting.Vault(app=SimpleNamespace(), hby=hby, rgy=rgy)
        hby.makeHab(name="no-mailbox-hab")  # hab with no mailbox role and no witnesses

        monkeypatch.setattr(agenting, "mailbox", lambda hab, cid: None)

        before = len(list(vault.db.mbx.getTopItemIter()))
        vault.seed_kel_mailboxes()
        after = len(list(vault.db.mbx.getTopItemIter()))
        assert after == before                       # None -> nothing pinned
    finally:
        if vault is not None:
            vault.db.close()
            vault.rep.mbx.close()
            vault.notifier.noter.close()
        rgy.close()
        hby.close()


def test_seed_kel_mailboxes_leaves_explicit_designation_untouched(monkeypatch, tmp_path):
    from keri.app import agenting
    from locksmith.db.basing import MailboxListener

    monkeypatch.setattr(vaulting, "LocksmithBaser",
                        lambda name, reopen=True: LocksmithBaser(
                            name=f"{name}-locksmith", headDirPath=str(tmp_path), reopen=reopen))
    monkeypatch.setattr(vaulting, "TurretDoer", _NoTurret)

    hby = habbing.Habery(name="vault-explicit", temp=True,
                         salt=signing.Salter(raw=b'fedcba9876543210').qb64)
    rgy = credentialing.Regery(hby=hby, name=hby.name, temp=True)
    vault = None
    try:
        vault = vaulting.Vault(app=SimpleNamespace(), hby=hby, rgy=rgy)
        doi = hby.makeHab(name="state-doi-explicit")

        # Pre-pin an explicit db.mbx entry the user "designated" (name="my-mailbox")
        vault.db.mbx.pin(keys=(doi.pre, "Embx"), val=MailboxListener(cid=doi.pre, eid="Embx", name="my-mailbox"))

        # Resolver returns same EID — seed should skip because entry already exists
        monkeypatch.setattr(agenting, "mailbox", lambda hab, cid: "Embx")

        vault.seed_kel_mailboxes()

        kept = vault.db.mbx.get(keys=(doi.pre, "Embx"))
        assert kept.name == "my-mailbox"             # explicit designation NOT clobbered
    finally:
        if vault is not None:
            vault.db.close()
            vault.rep.mbx.close()
            vault.notifier.noter.close()
        rgy.close()
        hby.close()


def test_seed_kel_mailboxes_pins_per_aid_when_sharing_one_mailbox(monkeypatch, tmp_path):
    from keri.app import agenting

    monkeypatch.setattr(vaulting, "LocksmithBaser",
                        lambda name, reopen=True: LocksmithBaser(
                            name=f"{name}-locksmith", headDirPath=str(tmp_path), reopen=reopen))
    monkeypatch.setattr(vaulting, "TurretDoer", _NoTurret)

    hby = habbing.Habery(name="vault-shared", temp=True,
                         salt=signing.Salter(raw=b'sharedmailbox012').qb64)
    rgy = credentialing.Regery(hby=hby, name=hby.name, temp=True)
    vault = None
    try:
        vault = vaulting.Vault(app=SimpleNamespace(), hby=hby, rgy=rgy)
        a = hby.makeHab(name="aid-a")
        b = hby.makeHab(name="aid-b")

        monkeypatch.setattr(agenting, "mailbox", lambda hab, cid: "Eshared")  # both share one mailbox

        vault.seed_kel_mailboxes()

        entries = {mbl.cid: mbl for _k, mbl in vault.db.mbx.getTopItemIter()}
        assert a.pre in entries, "AID a not seeded"
        assert b.pre in entries, "AID b not seeded (the bug: 2nd AID sharing a mailbox is skipped)"
        assert entries[a.pre].eid == "Eshared"
        assert entries[b.pre].eid == "Eshared"
    finally:
        if vault is not None:
            vault.db.close()
            vault.rep.mbx.close()
            vault.notifier.noter.close()
        rgy.close()
        hby.close()
