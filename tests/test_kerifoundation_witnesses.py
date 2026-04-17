import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from locksmith.plugins.kerifoundation.db.basing import (
    ACCOUNT_STATUS_ONBOARDED,
    KFBaser,
    KFAccountRecord,
    WitnessRecord,
)
from locksmith.plugins.kerifoundation.onboarding.service import (
    AccountWatcherRow,
    AccountWitnessRow,
)
from locksmith.plugins.kerifoundation.watchers.list import WatcherListPage
from locksmith.plugins.kerifoundation.witnesses.list import WitnessOverviewPage
from locksmith.plugins.kerifoundation.witnesses.provision import (
    HostedWitnessAllocation,
    HostedWitnessRegistrar,
)


class FakeOrg:
    def __init__(self):
        self.data = {}

    def rem(self, pre):
        self.data.pop(pre, None)


class FakeHby:
    def __init__(self, habs):
        self._by_pre = {hab.pre: hab for hab in habs}

    def habByPre(self, pre):
        return self._by_pre.get(pre)


class FakeVault:
    def __init__(self, habs):
        self.hby = FakeHby(habs)
        self.org = FakeOrg()


class FakeApp:
    def __init__(self, habs):
        self.vault = FakeVault(habs)


def make_hab(name, pre, wits=None, toad=1):
    return SimpleNamespace(
        name=name,
        pre=pre,
        kever=SimpleNamespace(
            wits=list(wits or []),
            toader=SimpleNamespace(num=toad),
        ),
    )


class FakeBootClient:
    def __init__(self, witness_rows=None, watcher_rows=None):
        self.witness_rows = list(witness_rows or [])
        self.watcher_rows = list(watcher_rows or [])
        self.calls = []

    def list_account_witnesses(self, hab, *, account_aid: str, destination: str = ""):
        self.calls.append(("witnesses", hab.pre, account_aid, destination))
        return list(self.witness_rows)

    def list_account_watchers(self, hab, *, account_aid: str, destination: str = ""):
        self.calls.append(("watchers", hab.pre, account_aid, destination))
        return list(self.watcher_rows)


def _make_db(tmp_path, name):
    return KFBaser(name=name, headDirPath=str(tmp_path), reopen=True)


def test_witness_overview_page_uses_boot_rows_and_local_auth_overlay(qapp, tmp_path):
    hab = make_hab("kf-account", "AID_ACCOUNT")
    app = FakeApp([hab])
    db = _make_db(tmp_path, "kf-witness-overview")
    boot_client = FakeBootClient(
        witness_rows=[
            AccountWitnessRow(
                eid="WIT_1",
                name="Witness One",
                url="https://wit-1.example",
                region_name="US West",
            ),
            AccountWitnessRow(
                eid="WIT_2",
                name="Witness Two",
                url="https://wit-2.example",
                region_name="US East",
            ),
        ]
    )

    try:
        db.pin_account(
            KFAccountRecord(
                account_aid=hab.pre,
                account_alias=hab.name,
                status=ACCOUNT_STATUS_ONBOARDED,
                boot_server_aid="BOOT_AID",
            )
        )
        db.witnesses.pin(
            keys=(hab.pre, "WIT_1"),
            val=WitnessRecord(
                eid="WIT_1",
                hab_pre=hab.pre,
                oobi="https://wit-1.example/oobi/WIT_1/controller",
                totp_seed="SEED1",
                batch_mode=True,
            ),
        )

        page = WitnessOverviewPage(app=app)
        page.set_db(db)
        page.set_boot_client(boot_client)
        page.on_show()

        assert boot_client.calls == [("witnesses", hab.pre, hab.pre, "BOOT_AID")]
        assert [row["Witness AID"] for row in page._current_rows] == ["WIT_1", "WIT_2"]
        assert page._current_rows[0]["Auth"] == "Batch TOTP configured"
        assert page._current_rows[1]["Auth"] == "Pending local auth"
    finally:
        db.close()


def test_watcher_list_page_uses_boot_rows(qapp, tmp_path):
    hab = make_hab("kf-account", "AID_ACCOUNT")
    app = FakeApp([hab])
    db = _make_db(tmp_path, "kf-watcher-overview")
    boot_client = FakeBootClient(
        watcher_rows=[
            AccountWatcherRow(
                eid="WAT_1",
                name="Watcher One",
                url="https://watch-1.example",
                region_name="US West",
                status="Ready",
            )
        ]
    )

    try:
        db.pin_account(
            KFAccountRecord(
                account_aid=hab.pre,
                account_alias=hab.name,
                status=ACCOUNT_STATUS_ONBOARDED,
                boot_server_aid="BOOT_AID",
            )
        )

        page = WatcherListPage(app=app)
        page.set_db(db)
        page.set_boot_client(boot_client)
        page.on_show()

        assert boot_client.calls == [("watchers", hab.pre, hab.pre, "BOOT_AID")]
        assert page._table._static_data[0]["Watcher AID"] == "WAT_1"
        assert page._table._static_data[0]["Status"] == "Ready"
    finally:
        db.close()


def test_hosted_witness_registrar_persists_registration_state(tmp_path, monkeypatch):
    hab = make_hab("kf-account", "AID_ACCOUNT")
    app = FakeApp([hab])
    db = _make_db(tmp_path, "kf-hosted-registrar")

    def fake_resolve_oobi(*args, **kwa):
        return True

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.register_with_witness",
        lambda hab, witness_eid, witness_url, secret=None: {
            "eid": witness_eid,
            "totp_seed": "SEED",
            "oobi": "",
        },
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.resolve_oobi_blocking",
        fake_resolve_oobi,
    )

    try:
        registrar = HostedWitnessRegistrar(app=app, db=db)
        result = registrar.register(
            hab=hab,
            witnesses=[
                HostedWitnessAllocation(
                    eid="WIT_1",
                    witness_url="https://wit-1.example",
                    boot_url="https://boot-1.example",
                    oobi="https://wit-1.example/oobi/WIT_1/controller",
                    name="Witness One",
                ),
                HostedWitnessAllocation(
                    eid="WIT_2",
                    witness_url="https://wit-2.example",
                    boot_url="https://boot-2.example",
                    oobi="https://wit-2.example/oobi/WIT_2/controller",
                    name="Witness Two",
                ),
            ],
            batch_mode=True,
        )

        assert result.batch_mode is True
        assert len(result.results) == 2
        assert db.witnesses.get(keys=(hab.pre, "WIT_1")) is not None
        assert db.witnesses.get(keys=(hab.pre, "WIT_2")) is not None
        assert db.provisionedWitnesses.get(keys=(hab.pre, "https://boot-1.example")) is not None
        assert db.provisionedWitnesses.get(keys=(hab.pre, "https://boot-2.example")) is not None
        batches = db.witBatches.get(keys=(hab.pre,))
        assert batches is not None
        assert batches.batches == [["WIT_1", "WIT_2"]]
    finally:
        db.close()


def test_hosted_witness_registrar_persists_recovery_state_when_rollback_fails(tmp_path, monkeypatch):
    hab = make_hab("kf-account", "AID_ACCOUNT")
    app = FakeApp([hab])
    db = _make_db(tmp_path, "kf-hosted-registrar-rollback")

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.register_with_witness",
        lambda hab, witness_eid, witness_url, secret=None: {
            "eid": witness_eid,
            "totp_seed": "SEED",
            "oobi": f"{witness_url}/oobi/{witness_eid}/controller",
        },
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.resolve_oobi_blocking",
        lambda *args, **kwa: False,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.deprovision_witness",
        lambda eid, boot_url: False,
    )

    try:
        registrar = HostedWitnessRegistrar(app=app, db=db)
        with pytest.raises(ValueError) as excinfo:
            registrar.register(
                hab=hab,
                witnesses=[
                    HostedWitnessAllocation(
                        eid="WIT_1",
                        witness_url="https://wit-1.example",
                        boot_url="https://boot-1.example",
                        oobi="https://wit-1.example/oobi/WIT_1/controller",
                        name="Witness One",
                    )
                ],
                batch_mode=True,
            )
        message = str(excinfo.value)
        assert "Failed to resolve OOBI for witness WIT_1." in message
        assert "Boot URL: https://boot-1.example" in message
        assert "Resolver: resolver_state=unknown(no_hby_db)" in message
        assert "Cleanup after witness registration failure was incomplete:" in message
        assert "rollback=WIT_1..." in message
        assert "pending=WIT_1..." in message

        record = db.provisionedWitnesses.get(keys=(hab.pre, "https://boot-1.example"))
        assert record is not None
        assert record.eid == "WIT_1"
        assert db.witnesses.get(keys=(hab.pre, "WIT_1")) is None
    finally:
        db.close()


def test_hosted_witness_registrar_preserves_primary_oobi_failure_when_cleanup_succeeds(tmp_path, monkeypatch):
    hab = make_hab("kf-account", "AID_ACCOUNT")
    app = FakeApp([hab])
    db = _make_db(tmp_path, "kf-hosted-registrar-primary-error")
    purged_oobis = []

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.register_with_witness",
        lambda hab, witness_eid, witness_url, secret=None: {
            "eid": witness_eid,
            "totp_seed": "SEED",
            "oobi": f"{witness_url}/oobi/{witness_eid}/controller",
        },
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.resolve_oobi_blocking",
        lambda *args, **kwa: False,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.deprovision_witness",
        lambda eid, boot_url: True,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.purge_oobi_resolution_state",
        lambda app, *, oobi: purged_oobis.append(oobi),
    )

    try:
        registrar = HostedWitnessRegistrar(app=app, db=db)
        with pytest.raises(ValueError) as excinfo:
            registrar.register(
                hab=hab,
                witnesses=[
                    HostedWitnessAllocation(
                        eid="WIT_1",
                        witness_url="https://wit-1.example",
                        boot_url="https://boot-1.example",
                        oobi="https://wit-1.example/oobi/WIT_1/controller",
                        name="Witness One",
                    )
                ],
                batch_mode=True,
            )

        message = str(excinfo.value)
        assert "Failed to resolve OOBI for witness WIT_1." in message
        assert "WIT_1" in message
        assert "Cleanup after witness registration failure was incomplete:" not in message
        assert purged_oobis == ["https://wit-1.example/oobi/WIT_1/controller"]
        assert db.provisionedWitnesses.get(keys=(hab.pre, "https://boot-1.example")) is None
    finally:
        db.close()
