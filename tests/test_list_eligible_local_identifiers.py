"""list_eligible_local_identifiers must tolerate a closed vault database.

Regression (KF onboarding crash): when the vault Habery's LMDB env is closed,
keri's LMDBer sets env=None, so getTopItemIter -> env.begin() raised
AttributeError: 'NoneType' object has no attribute 'begin' straight into the UI.
"""
from types import SimpleNamespace

from keri.app import habbing
from keri.core import signing
from keri.kering import Vrsn_1_0

from locksmith.core.habbing import list_eligible_local_identifiers


def _app_with(hby):
    return SimpleNamespace(vault=SimpleNamespace(hby=hby))


def test_returns_empty_when_vault_db_closed():
    hby = habbing.Habery(
        name="closedtest", bran="A" * 21,
        salt=signing.Salter(raw=b"0123456789abcdef").qb64,
        temp=True, version=Vrsn_1_0,
    )
    hby.makeHab(name="alice", isith="1", icount=1, transferable=True,
                version=Vrsn_1_0)
    hby.close()  # keri LMDBer.close() sets db.env = None

    assert list_eligible_local_identifiers(_app_with(hby)) == []


def test_lists_root_identifiers_when_open():
    hby = habbing.Habery(
        name="opentest", bran="B" * 21,
        salt=signing.Salter(raw=b"fedcba9876543210").qb64,
        temp=True, version=Vrsn_1_0,
    )
    try:
        hby.makeHab(name="alice", isith="1", icount=1, transferable=True,
                    version=Vrsn_1_0)
        aliases = {item["alias"]
                   for item in list_eligible_local_identifiers(_app_with(hby))}
        assert "alice" in aliases
    finally:
        hby.close()
