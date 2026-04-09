import asyncio
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from locksmith.core.receipting import LocksmithReceiptor
from locksmith.core.remoting import upsert_remote_id_metadata
from locksmith.core.rotating import AuthenticateWitnessesDoer
from locksmith.core.witnessing import get_unused_witnesses_for_rotation
from locksmith.plugins.kerifoundation.core.configing import load_witness_servers
from locksmith.plugins.kerifoundation.core.identifiers import iter_local_identifier_choices
from locksmith.plugins.kerifoundation.core.remoting import deprovision_witness
from locksmith.plugins.kerifoundation.db.basing import (
    KFBaser,
    ProvisionedWitnessRecord,
    WitnessRecord,
)
from locksmith.plugins.kerifoundation.witnesses.list import WitnessOverviewPage
from locksmith.plugins.kerifoundation.witnesses import provision as witness_provision_module
from locksmith.plugins.kerifoundation.witnesses.provision import (
    WitnessProvisionPage,
    _ProvisionRegisterWorker,
)


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------

class FakeOrg:
    def __init__(self):
        self._data = {}

    def update(self, pre, data):
        existing = self._data.get(pre, {}).copy()
        existing.update(data)
        self._data[pre] = existing

    def get(self, pre):
        data = self._data.get(pre)
        if data is None:
            return None
        return {"id": pre, **data}

    def list(self):
        return [{"id": pre, **data} for pre, data in self._data.items()]

    def rem(self, pre):
        self._data.pop(pre, None)


class FakeHby:
    def __init__(self, habs, name_entries=None):
        self.habs = {hab.name: hab for hab in habs}
        self._habs_by_name = {hab.name: hab for hab in habs}
        self.db = SimpleNamespace(
            names=SimpleNamespace(
                getItemIter=lambda keys=(): iter(
                    name_entries
                    if name_entries is not None
                    else [(("", hab.name), hab.pre) for hab in habs]
                )
            )
        )
        self.kevers = {}

    def habByPre(self, pre):
        for hab in self.habs.values():
            if hab.pre == pre:
                return hab
        return None

    def habByName(self, alias):
        return self._habs_by_name.get(alias)


class FakeVault:
    def __init__(self, habs, name_entries=None):
        self.org = FakeOrg()
        self.hby = FakeHby(habs, name_entries=name_entries)


class FakeApp:
    def __init__(self, habs=None, name_entries=None, environment=None):
        habs = habs or []
        self.vault = FakeVault(habs, name_entries=name_entries)
        self.config = SimpleNamespace(environment=environment)


def make_hab(name, pre, wits=None):
    return SimpleNamespace(
        name=name,
        pre=pre,
        kever=SimpleNamespace(wits=wits or [], transferable=False),
    )


# ---------------------------------------------------------------------------
# Shared identifier helper
# ---------------------------------------------------------------------------

def test_iter_local_identifier_choices_skips_groups_and_namespaced(monkeypatch):
    import keri.app.habbing as keri_habbing

    class FakeGroupHab:
        pass

    monkeypatch.setattr(keri_habbing, "GroupHab", FakeGroupHab)

    alpha = make_hab("alpha", "AID_ALPHA")
    zeta = make_hab("zeta", "AID_ZETA")
    group = FakeGroupHab()
    group.name = "group"
    group.pre = "AID_GROUP"
    group.kever = SimpleNamespace(wits=[], transferable=False)

    app = FakeApp(
        habs=[alpha, group, zeta],
        name_entries=[
            (("", "zeta"), "AID_ZETA"),
            (("team", "nested"), "AID_NESTED"),
            (("", "group"), "AID_GROUP"),
            (("", "alpha"), "AID_ALPHA"),
        ],
    )

    choices = list(iter_local_identifier_choices(app))
    assert choices == [("zeta", "AID_ZETA"), ("alpha", "AID_ALPHA")]


# ---------------------------------------------------------------------------
# Config — numbered env vars
# ---------------------------------------------------------------------------

def test_load_witness_servers_numbered_env_vars(monkeypatch):
    monkeypatch.setenv("KF_DEV_WITNESS_URL_1", "http://w1:5632")
    monkeypatch.setenv("KF_DEV_BOOT_URL_1", "http://b1:5631")
    monkeypatch.setenv("KF_DEV_REGION_1", "nyc")
    monkeypatch.setenv("KF_DEV_LABEL_1", "New York")
    monkeypatch.setenv("KF_DEV_WITNESS_URL_2", "http://w2:5632")
    monkeypatch.setenv("KF_DEV_BOOT_URL_2", "http://b2:5631")

    app = FakeApp(environment=SimpleNamespace(value="development"))
    servers = load_witness_servers(app)

    assert len(servers) == 2
    assert servers[0].witness_url == "http://w1:5632"
    assert servers[0].boot_url == "http://b1:5631"
    assert servers[0].region == "nyc"
    assert servers[0].label == "New York"
    assert servers[1].witness_url == "http://w2:5632"
    assert servers[1].boot_url == "http://b2:5631"
    assert servers[1].region == ""
    assert servers[1].label == ""


def test_load_witness_servers_legacy_unsuffixed_fallback(monkeypatch):
    """Legacy unsuffixed env vars still load when numbered vars are absent."""
    monkeypatch.setenv("KF_DEV_WITNESS_URL", "http://127.0.0.1:5632")
    monkeypatch.setenv("KF_DEV_BOOT_URL", "http://127.0.0.1:5631")

    app = FakeApp(environment=SimpleNamespace(value="development"))
    servers = load_witness_servers(app)
    assert len(servers) == 1
    assert servers[0].witness_url == "http://127.0.0.1:5632"
    assert servers[0].boot_url == "http://127.0.0.1:5631"


def test_load_witness_servers_numbered_entries_take_precedence(monkeypatch):
    monkeypatch.setenv("KF_DEV_WITNESS_URL", "http://legacy-w:5632")
    monkeypatch.setenv("KF_DEV_BOOT_URL", "http://legacy-b:5631")
    monkeypatch.setenv("KF_DEV_WITNESS_URL_1", "http://w1:5632")
    monkeypatch.setenv("KF_DEV_BOOT_URL_1", "http://b1:5631")

    app = FakeApp(environment=SimpleNamespace(value="development"))
    servers = load_witness_servers(app)

    assert len(servers) == 1
    assert servers[0].witness_url == "http://w1:5632"
    assert servers[0].boot_url == "http://b1:5631"


def test_load_witness_servers_incomplete_pair_skipped(monkeypatch):
    """If only WITNESS_URL is set (no BOOT_URL), that index is skipped."""
    monkeypatch.delenv("KF_DEV_WITNESS_URL", raising=False)
    monkeypatch.delenv("KF_DEV_BOOT_URL", raising=False)
    monkeypatch.delenv("KF_DEV_BOOT_URL_1", raising=False)
    monkeypatch.setenv("KF_DEV_WITNESS_URL_1", "http://w1:5632")
    # Missing KF_DEV_BOOT_URL_1
    monkeypatch.setenv("KF_DEV_WITNESS_URL_2", "http://w2:5632")
    monkeypatch.setenv("KF_DEV_BOOT_URL_2", "http://b2:5631")

    app = FakeApp(environment=SimpleNamespace(value="development"))
    servers = load_witness_servers(app)

    assert len(servers) == 1
    assert servers[0].witness_url == "http://w2:5632"


def test_load_witness_servers_stops_at_gap(monkeypatch):
    """Scanning stops when both URL and BOOT_URL are missing at an index."""
    monkeypatch.setenv("KF_DEV_WITNESS_URL_1", "http://w1:5632")
    monkeypatch.setenv("KF_DEV_BOOT_URL_1", "http://b1:5631")
    # Index 2 fully missing → stop
    monkeypatch.setenv("KF_DEV_WITNESS_URL_3", "http://w3:5632")
    monkeypatch.setenv("KF_DEV_BOOT_URL_3", "http://b3:5631")

    app = FakeApp(environment=SimpleNamespace(value="development"))
    servers = load_witness_servers(app)

    assert len(servers) == 1


# ---------------------------------------------------------------------------
# Deprovision
# ---------------------------------------------------------------------------

def test_deprovision_witness_returns_true_on_204(monkeypatch):
    class FakeResponse:
        status_code = 204
        def raise_for_status(self):
            pass

    monkeypatch.setattr("locksmith.plugins.kerifoundation.core.remoting.requests.delete",
                         lambda url, timeout=None: FakeResponse())

    assert deprovision_witness("WIT_1", "http://boot:5631") is True


def test_deprovision_witness_returns_false_on_error(monkeypatch):
    def raise_error(url, timeout=None):
        raise ConnectionError("refused")

    monkeypatch.setattr("locksmith.plugins.kerifoundation.core.remoting.requests.delete",
                         raise_error)

    assert deprovision_witness("WIT_1", "http://boot:5631") is False


# ---------------------------------------------------------------------------
# Overview page
# ---------------------------------------------------------------------------

def test_overview_page_shows_identifier_rows(qapp):
    alpha = make_hab("alpha", "AID_ALPHA")
    app = FakeApp(habs=[alpha])

    page = WitnessOverviewPage(app=app)
    page.on_show()

    assert len(page._current_rows) == 1
    assert page._current_rows[0]["Alias"] == "alpha"
    assert page._current_rows[0]["Prefix"] == "AID_ALPHA"
    assert page._current_rows[0]["Witnesses"] == "—"
    assert page._current_rows[0]["Status"] == "No witnesses"


def test_overview_page_shows_registered_and_pending_counts(qapp, tmp_path):
    alpha = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[alpha])
    db = KFBaser(name="test-overview-counts", headDirPath=str(tmp_path), reopen=True)

    try:
        page = WitnessOverviewPage(app=app)
        page.set_db(db)

        # Add 2 registered witnesses
        db.witnesses.pin(
            keys=("AID_A", "WIT_1"),
            val=WitnessRecord(eid="WIT_1", hab_pre="AID_A", totp_seed="S1"),
        )
        db.witnesses.pin(
            keys=("AID_A", "WIT_2"),
            val=WitnessRecord(eid="WIT_2", hab_pre="AID_A", totp_seed="S2"),
        )
        # Add 1 pending provisioned witness (not yet registered)
        db.provisionedWitnesses.pin(
            keys=("AID_A", "http://boot3:5631"),
            val=ProvisionedWitnessRecord(
                boot_url="http://boot3:5631", witness_url="http://w3:5632",
                eid="WIT_3", oobi="http://w3:5632/oobi/WIT_3/controller",
                hab_pre="AID_A", provisioned_at="2026-03-31T00:00:00+00:00",
            ),
        )
        # Add 1 provisioned witness that IS also registered (should not count as pending)
        db.provisionedWitnesses.pin(
            keys=("AID_A", "http://boot1:5631"),
            val=ProvisionedWitnessRecord(
                boot_url="http://boot1:5631", witness_url="http://w1:5632",
                eid="WIT_1", oobi="http://w1:5632/oobi/WIT_1/controller",
                hab_pre="AID_A", provisioned_at="2026-03-31T00:00:00+00:00",
            ),
        )

        page.on_show()

        assert len(page._current_rows) == 1
        row = page._current_rows[0]
        assert row["Witnesses"] == "2 registered, 1 pending"
        assert row["Status"] == "Ready"
    finally:
        db.close()


def test_pending_provisioned_state_survives_reload(qapp, tmp_path):
    alpha = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[alpha])
    db = KFBaser(name="test-pending-survive", headDirPath=str(tmp_path), reopen=True)

    try:
        db.provisionedWitnesses.pin(
            keys=("AID_A", "http://boot1:5631"),
            val=ProvisionedWitnessRecord(
                boot_url="http://boot1:5631", witness_url="http://w1:5632",
                eid="WIT_1", oobi="http://w1:5632/oobi/WIT_1/controller",
                hab_pre="AID_A", provisioned_at="2026-03-31T00:00:00+00:00",
            ),
        )

        # First load
        page1 = WitnessOverviewPage(app=app)
        page1.set_db(db)
        page1.on_show()
        assert page1._current_rows[0]["Witnesses"] == "1 pending"

        # Second load (simulates app restart with same DB)
        page2 = WitnessOverviewPage(app=app)
        page2.set_db(db)
        page2.on_show()
        assert page2._current_rows[0]["Witnesses"] == "1 pending"
    finally:
        db.close()


def test_overview_add_witnesses_emits_signal(qapp):
    alpha = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[alpha])
    emitted = []

    page = WitnessOverviewPage(app=app)
    page.add_witnesses_requested.connect(lambda pre: emitted.append(pre))
    page.on_show()

    page._on_row_action(page._current_rows[0], "Add Witnesses")
    assert emitted == ["AID_A"]


def test_provision_page_disables_registered_and_pending_servers(qapp, tmp_path, monkeypatch):
    alpha = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[alpha])
    db = KFBaser(name="test-server-states", headDirPath=str(tmp_path), reopen=True)

    from locksmith.plugins.kerifoundation.core.configing import WitnessServerConfig

    servers = [
        WitnessServerConfig(witness_url="http://w1:5632", boot_url="http://b1:5631"),
        WitnessServerConfig(witness_url="http://w2:5632", boot_url="http://b2:5631"),
        WitnessServerConfig(witness_url="http://w3:5632", boot_url="http://b3:5631"),
    ]
    monkeypatch.setattr(
        witness_provision_module,
        "load_witness_servers",
        lambda _app: servers,
    )

    try:
        db.witnesses.pin(
            keys=(alpha.pre, "WIT_1"),
            val=WitnessRecord(
                eid="WIT_1",
                url="http://w1:5632",
                oobi="http://w1:5632/oobi/WIT_1/controller",
                hab_pre=alpha.pre,
                totp_seed="SEED1",
            ),
        )
        db.provisionedWitnesses.pin(
            keys=(alpha.pre, "http://b1:5631"),
            val=ProvisionedWitnessRecord(
                boot_url="http://b1:5631",
                witness_url="http://w1:5632",
                eid="WIT_1",
                oobi="http://w1:5632/oobi/WIT_1/controller",
                hab_pre=alpha.pre,
                provisioned_at="2026-03-31T00:00:00+00:00",
            ),
        )
        db.provisionedWitnesses.pin(
            keys=(alpha.pre, "http://b2:5631"),
            val=ProvisionedWitnessRecord(
                boot_url="http://b2:5631",
                witness_url="http://w2:5632",
                eid="WIT_2",
                oobi="http://w2:5632/oobi/WIT_2/controller",
                hab_pre=alpha.pre,
                provisioned_at="2026-03-31T00:00:00+00:00",
            ),
        )

        page = WitnessProvisionPage(app=app)
        page.set_db(db)
        page.set_identifier(alpha.pre)
        page.on_show()

        assert [card.status for card in page._server_cards] == [
            "registered",
            "pending",
            "available",
        ]
        assert not page._server_cards[0].isEnabled()
        assert not page._server_cards[1].isEnabled()
        assert page._server_cards[2].isEnabled()

        page._on_select_all()
        assert not page._server_cards[0].is_checked()
        assert not page._server_cards[1].is_checked()
        assert page._server_cards[2].is_checked()
        assert page._action_btn.isEnabled()
    finally:
        db.close()


def test_provision_page_disables_action_when_no_servers_available(qapp, tmp_path, monkeypatch):
    alpha = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[alpha], environment=SimpleNamespace(value="development"))
    db = KFBaser(name="test-no-available-servers", headDirPath=str(tmp_path), reopen=True)

    from locksmith.plugins.kerifoundation.core.configing import WitnessServerConfig

    servers = [
        WitnessServerConfig(witness_url="http://w1:5632", boot_url="http://b1:5631"),
        WitnessServerConfig(witness_url="http://w2:5632", boot_url="http://b2:5631"),
    ]
    monkeypatch.setattr(
        witness_provision_module,
        "load_witness_servers",
        lambda _app: servers,
    )

    try:
        db.witnesses.pin(
            keys=(alpha.pre, "WIT_1"),
            val=WitnessRecord(
                eid="WIT_1",
                url="http://w1:5632",
                oobi="http://w1:5632/oobi/WIT_1/controller",
                hab_pre=alpha.pre,
                totp_seed="SEED1",
            ),
        )
        db.provisionedWitnesses.pin(
            keys=(alpha.pre, "http://b2:5631"),
            val=ProvisionedWitnessRecord(
                boot_url="http://b2:5631",
                witness_url="http://w2:5632",
                eid="WIT_2",
                oobi="http://w2:5632/oobi/WIT_2/controller",
                hab_pre=alpha.pre,
                provisioned_at="2026-03-31T00:00:00+00:00",
            ),
        )

        page = WitnessProvisionPage(app=app)
        page.set_db(db)
        page.set_identifier(alpha.pre)
        page.on_show()

        assert not page._action_btn.isEnabled()
        assert not page._server_empty_label.isHidden()
        assert "already registered or pending" in page._server_empty_label.text()
        assert page._select_all_label.isHidden()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Registration worker — OOBI fallback
# ---------------------------------------------------------------------------

def test_provision_register_worker_prefers_service_returned_oobi(monkeypatch):
    captured = []

    def fake_provision(hab_pre, boot_url):
        return {"eid": "WIT_1", "oobi": "http://provision.example/oobi/WIT_1/controller"}

    def fake_register(hab, witness_eid, witness_url, secret=None):
        return {
            "eid": witness_eid,
            "totp_seed": "SEED",
            "oobi": "https://canonical.example:5642/oobi/WIT_1/controller",
        }

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.provision_witness",
        fake_provision,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.register_with_witness",
        fake_register,
    )

    from locksmith.plugins.kerifoundation.core.configing import WitnessServerConfig
    server = WitnessServerConfig(
        witness_url="https://configured.example:5642",
        boot_url="https://boot.example:5631",
    )

    worker = _ProvisionRegisterWorker(
        hab_pre="AID_A",
        hab=object(),
        servers=[server],
    )
    worker.finished.connect(lambda results, error, rf: captured.append((results, error)))
    worker.run()

    assert captured[0][1] == ""
    assert captured[0][0][0]["oobi"] == "https://canonical.example:5642/oobi/WIT_1/controller"


def test_provision_register_worker_falls_back_to_provision_oobi(monkeypatch):
    captured = []

    def fake_provision(hab_pre, boot_url):
        return {"eid": "WIT_1", "oobi": "http://provision.example/oobi/WIT_1/controller"}

    def fake_register(hab, witness_eid, witness_url, secret=None):
        return {"eid": witness_eid, "totp_seed": "SEED", "oobi": ""}

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.provision_witness",
        fake_provision,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.register_with_witness",
        fake_register,
    )

    from locksmith.plugins.kerifoundation.core.configing import WitnessServerConfig
    server = WitnessServerConfig(witness_url="http://w:5632", boot_url="http://b:5631")

    worker = _ProvisionRegisterWorker(hab_pre="AID_A", hab=object(), servers=[server])
    worker.finished.connect(lambda results, error, rf: captured.append((results, error)))
    worker.run()

    assert captured[0][0][0]["oobi"] == "http://provision.example/oobi/WIT_1/controller"


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def test_full_batch_rollback_on_provision_failure(monkeypatch, tmp_path):
    """Provision 2 servers, fail on 3rd → deprovision all 2."""
    provision_calls = []
    deprovision_calls = []

    def fake_provision(hab_pre, boot_url):
        idx = len(provision_calls) + 1
        provision_calls.append(boot_url)
        if idx == 3:
            raise ConnectionError("server 3 down")
        return {"eid": f"WIT_{idx}", "oobi": f"http://w{idx}:5632/oobi/WIT_{idx}/controller"}

    def fake_deprovision(eid, boot_url):
        deprovision_calls.append(eid)
        return True

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.provision_witness",
        fake_provision,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.deprovision_witness",
        fake_deprovision,
    )

    from locksmith.plugins.kerifoundation.core.configing import WitnessServerConfig
    servers = [
        WitnessServerConfig(witness_url=f"http://w{i}:5632", boot_url=f"http://b{i}:5631")
        for i in range(1, 4)
    ]

    captured = []
    worker = _ProvisionRegisterWorker(hab_pre="AID_A", hab=object(), servers=servers)
    worker.finished.connect(lambda results, error, rf: captured.append((results, error, rf)))
    worker.run()

    assert captured[0][1] != ""  # error
    assert deprovision_calls == ["WIT_1", "WIT_2"]
    assert captured[0][2] == []  # no rollback failures


def test_full_batch_rollback_on_registration_failure(monkeypatch):
    """Provision all 2, register 1, fail on 2nd → deprovision all 2."""
    deprovision_calls = []
    register_count = [0]

    def fake_provision(hab_pre, boot_url):
        idx = len(deprovision_calls) + register_count[0] + 1
        return {"eid": f"WIT_{boot_url[-1]}", "oobi": f"http://w/oobi/WIT_{boot_url[-1]}"}

    prov_idx = [0]

    def fake_provision_tracked(hab_pre, boot_url):
        prov_idx[0] += 1
        return {"eid": f"WIT_{prov_idx[0]}", "oobi": f"http://w/oobi/WIT_{prov_idx[0]}"}

    def fake_register(hab, witness_eid, witness_url, secret=None):
        register_count[0] += 1
        if register_count[0] == 2:
            raise ConnectionError("register failed")
        return {"eid": witness_eid, "totp_seed": "SEED", "oobi": ""}

    def fake_deprovision(eid, boot_url):
        deprovision_calls.append(eid)
        return True

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.provision_witness",
        fake_provision_tracked,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.register_with_witness",
        fake_register,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.deprovision_witness",
        fake_deprovision,
    )

    from locksmith.plugins.kerifoundation.core.configing import WitnessServerConfig
    servers = [
        WitnessServerConfig(witness_url=f"http://w{i}:5632", boot_url=f"http://b{i}:5631")
        for i in range(1, 3)
    ]

    captured = []
    worker = _ProvisionRegisterWorker(hab_pre="AID_A", hab=object(), servers=servers)
    worker.finished.connect(lambda results, error, rf: captured.append((results, error, rf)))
    worker.run()

    assert captured[0][1] != ""
    assert set(deprovision_calls) == {"WIT_1", "WIT_2"}


def test_partial_deprovision_failure_preserves_state(monkeypatch):
    """Rollback where one deprovision fails → that witness is in rollback_failures."""
    def fake_provision(hab_pre, boot_url):
        idx = boot_url[-1]
        return {"eid": f"WIT_{idx}", "oobi": f"http://w/oobi/WIT_{idx}"}

    prov_idx = [0]

    def fake_provision_tracked(hab_pre, boot_url):
        prov_idx[0] += 1
        return {"eid": f"WIT_{prov_idx[0]}", "oobi": f"http://w/oobi/WIT_{prov_idx[0]}"}

    def fake_register(hab, witness_eid, witness_url, secret=None):
        raise ConnectionError("register failed")

    def fake_deprovision(eid, boot_url):
        return eid != "WIT_2"  # WIT_2 fails to deprovision

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.provision_witness",
        fake_provision_tracked,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.register_with_witness",
        fake_register,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.deprovision_witness",
        fake_deprovision,
    )

    from locksmith.plugins.kerifoundation.core.configing import WitnessServerConfig
    servers = [
        WitnessServerConfig(witness_url=f"http://w{i}:5632", boot_url=f"http://b{i}:5631")
        for i in range(1, 3)
    ]

    captured = []
    worker = _ProvisionRegisterWorker(hab_pre="AID_A", hab=object(), servers=servers)
    worker.finished.connect(lambda results, error, rf: captured.append((results, error, rf)))
    worker.run()

    rollback_failures = captured[0][2]
    assert len(rollback_failures) == 1
    assert rollback_failures[0]["eid"] == "WIT_2"
    assert rollback_failures[0]["boot_url"] == "http://b2:5631"
    assert rollback_failures[0]["witness_url"] == "http://w2:5632"
    assert rollback_failures[0]["oobi"] == "http://w/oobi/WIT_2"


def test_worker_rollback_failure_is_saved_as_pending(qapp, tmp_path):
    alpha = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[alpha])
    db = KFBaser(name="test-worker-rollback-pending", headDirPath=str(tmp_path), reopen=True)

    try:
        page = WitnessProvisionPage(app=app)
        page.set_db(db)
        page.set_identifier(alpha.pre)

        rollback_failures = [{
            "eid": "WIT_2",
            "oobi": "http://w2:5632/oobi/WIT_2/controller",
            "boot_url": "http://b2:5631",
            "witness_url": "http://w2:5632",
        }]

        page._handle_error("register failed", [], rollback_failures)

        record = db.provisionedWitnesses.get(keys=(alpha.pre, "http://b2:5631"))
        assert record is not None
        assert record.eid == "WIT_2"
        assert db.witnesses.get(keys=(alpha.pre, "WIT_2")) is None

        overview = WitnessOverviewPage(app=app)
        overview.set_db(db)
        overview.on_show()
        assert overview._current_rows[0]["Witnesses"] == "1 pending"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Finalization — canonical OOBI and rotation visibility
# ---------------------------------------------------------------------------

def test_finalize_registration_persists_canonical_oobi_and_makes_witness_rotatable(
    qapp, tmp_path, monkeypatch
):
    witness_eid = "WIT_1"
    returned_oobi = "https://canonical.example:5642/oobi/WIT_1/controller"
    hab = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[hab])
    db = KFBaser(name="test-finalize-success", headDirPath=str(tmp_path), reopen=True)

    async def fake_resolve_oobi(app, pre, oobi=None, force=False, alias=None, cid=None, tag=None):
        app.vault.hby.kevers[pre] = SimpleNamespace(transferable=False)
        upsert_remote_id_metadata(app, pre, alias=alias, cid=cid, tag=tag, oobi=oobi)
        return True

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.resolve_oobi",
        fake_resolve_oobi,
    )

    try:
        page = WitnessProvisionPage(app=app)
        page.set_db(db)
        page._hab_pre = hab.pre
        page._reg_hab = hab
        page._reg_batch_mode = False
        page._provisioned_in_run = [
            {"eid": witness_eid, "boot_url": "http://boot:5631", "witness_url": "https://configured.example:5642"},
        ]
        monkeypatch.setattr(page, "_show_qr_codes", lambda *args, **kwargs: None)

        asyncio.run(
            page._finalize_registration(
                [{"eid": witness_eid, "totp_seed": "SEED", "oobi": returned_oobi,
                  "boot_url": "http://boot:5631", "witness_url": "https://configured.example:5642"}]
            )
        )

        record = db.witnesses.get(keys=(hab.pre, witness_eid))
        assert record is not None
        assert record.oobi == returned_oobi
        assert record.url == "https://canonical.example:5642"

        remote_id = app.vault.org.get(witness_eid)
        assert remote_id["alias"] == "KF Witness WIT_1"
        assert remote_id["cid"] == hab.pre
        assert remote_id["tag"] == "witness"
        assert remote_id["oobi"] == returned_oobi

        unused = get_unused_witnesses_for_rotation(app, hab)
        assert [wit["id"] for wit in unused] == [witness_eid]
    finally:
        db.close()


def test_finalize_registration_does_not_persist_on_resolution_failure(
    qapp, tmp_path, monkeypatch
):
    hab = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[hab])
    db = KFBaser(name="test-finalize-failure", headDirPath=str(tmp_path), reopen=True)

    async def fake_resolve_oobi(app, pre, oobi=None, force=False, alias=None, cid=None, tag=None):
        return False

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.resolve_oobi",
        fake_resolve_oobi,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.deprovision_witness",
        lambda eid, boot_url: True,
    )

    try:
        page = WitnessProvisionPage(app=app)
        page.set_db(db)
        page._hab_pre = hab.pre
        page._reg_hab = hab
        page._reg_batch_mode = False
        page._provisioned_in_run = [
            {"eid": "WIT_1", "boot_url": "http://boot:5631", "witness_url": "http://w:5632"},
        ]
        monkeypatch.setattr(page, "_show_qr_codes", lambda *args, **kwargs: None)

        asyncio.run(
            page._finalize_registration(
                [{"eid": "WIT_1", "totp_seed": "SEED",
                  "oobi": "https://canonical.example:5642/oobi/WIT_1/controller",
                  "boot_url": "http://boot:5631", "witness_url": "http://w:5632"}]
            )
        )

        assert db.witnesses.get(keys=(hab.pre, "WIT_1")) is None
    finally:
        db.close()


def test_rollback_cleans_organizer_state(qapp, tmp_path, monkeypatch):
    """OOBI resolves for WIT_1, then WIT_2 fails → WIT_1 removed from Organizer."""
    hab = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[hab])
    db = KFBaser(name="test-rollback-org", headDirPath=str(tmp_path), reopen=True)

    resolve_count = [0]

    async def fake_resolve_oobi(app, pre, oobi=None, force=False, alias=None, cid=None, tag=None):
        resolve_count[0] += 1
        if resolve_count[0] == 1:
            app.vault.hby.kevers[pre] = SimpleNamespace(transferable=False)
            upsert_remote_id_metadata(app, pre, alias=alias, cid=cid, tag=tag, oobi=oobi)
            return True
        return False  # WIT_2 fails

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.resolve_oobi",
        fake_resolve_oobi,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.deprovision_witness",
        lambda eid, boot_url: True,
    )

    try:
        page = WitnessProvisionPage(app=app)
        page.set_db(db)
        page._hab_pre = hab.pre
        page._reg_hab = hab
        page._reg_batch_mode = False
        page._provisioned_in_run = [
            {"eid": "WIT_1", "boot_url": "http://b1:5631", "witness_url": "http://w1:5632"},
            {"eid": "WIT_2", "boot_url": "http://b2:5631", "witness_url": "http://w2:5632"},
        ]
        monkeypatch.setattr(page, "_show_qr_codes", lambda *args, **kwargs: None)

        asyncio.run(
            page._finalize_registration([
                {"eid": "WIT_1", "totp_seed": "S1", "oobi": "http://w1/oobi/WIT_1",
                 "boot_url": "http://b1:5631", "witness_url": "http://w1:5632"},
                {"eid": "WIT_2", "totp_seed": "S2", "oobi": "http://w2/oobi/WIT_2",
                 "boot_url": "http://b2:5631", "witness_url": "http://w2:5632"},
            ])
        )

        # WIT_1 should have been removed from Organizer during rollback
        assert app.vault.org.get("WIT_1") is None
        # No WitnessRecord for either
        assert db.witnesses.get(keys=(hab.pre, "WIT_1")) is None
        assert db.witnesses.get(keys=(hab.pre, "WIT_2")) is None

        # WIT_1 should NOT be rotatable
        unused = get_unused_witnesses_for_rotation(app, hab)
        assert unused == []
    finally:
        db.close()


def test_post_persist_rollback_removes_registered_state_and_keeps_pending_survivor(
    qapp, tmp_path, monkeypatch
):
    hab = make_hab("alpha", "AID_A")
    app = FakeApp(habs=[hab])
    db = KFBaser(name="test-post-persist-rollback", headDirPath=str(tmp_path), reopen=True)

    async def fake_resolve_oobi(app, pre, oobi=None, force=False, alias=None, cid=None, tag=None):
        app.vault.hby.kevers[pre] = SimpleNamespace(transferable=False)
        upsert_remote_id_metadata(app, pre, alias=alias, cid=cid, tag=tag, oobi=oobi)
        return True

    def fake_deprovision(eid, boot_url):
        return eid != "WIT_2"

    def fail_show_qr(*args, **kwargs):
        raise RuntimeError("QR rendering failed")

    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.resolve_oobi",
        fake_resolve_oobi,
    )
    monkeypatch.setattr(
        "locksmith.plugins.kerifoundation.witnesses.provision.deprovision_witness",
        fake_deprovision,
    )

    results = [
        {
            "eid": "WIT_1",
            "totp_seed": "S1",
            "oobi": "http://w1:5632/oobi/WIT_1/controller",
            "boot_url": "http://b1:5631",
            "witness_url": "http://w1:5632",
        },
        {
            "eid": "WIT_2",
            "totp_seed": "S2",
            "oobi": "http://w2:5632/oobi/WIT_2/controller",
            "boot_url": "http://b2:5631",
            "witness_url": "http://w2:5632",
        },
    ]

    try:
        page = WitnessProvisionPage(app=app)
        page.set_db(db)
        page.set_identifier(hab.pre)
        page._reg_hab = hab
        page._reg_batch_mode = True
        page._provisioned_in_run = [
            {"eid": "WIT_1", "boot_url": "http://b1:5631", "witness_url": "http://w1:5632"},
            {"eid": "WIT_2", "boot_url": "http://b2:5631", "witness_url": "http://w2:5632"},
        ]
        page._persist_provisioned_witnesses(results)
        monkeypatch.setattr(page, "_show_qr_codes", fail_show_qr)

        asyncio.run(page._finalize_registration(results))

        assert db.witnesses.get(keys=(hab.pre, "WIT_1")) is None
        assert db.witnesses.get(keys=(hab.pre, "WIT_2")) is None

        batches = db.witBatches.get(keys=(hab.pre,))
        assert batches is None or batches.batches == []

        assert app.vault.org.get("WIT_1") is None
        assert app.vault.org.get("WIT_2") is None

        assert db.provisionedWitnesses.get(keys=(hab.pre, "http://b1:5631")) is None
        pending = db.provisionedWitnesses.get(keys=(hab.pre, "http://b2:5631"))
        assert pending is not None
        assert pending.eid == "WIT_2"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# upsert_remote_id_metadata (unchanged)
# ---------------------------------------------------------------------------

def test_upsert_remote_id_metadata_creates_remote_identifier():
    app = FakeApp()

    remote_id = upsert_remote_id_metadata(
        app,
        "WIT_1",
        alias="KF Witness WIT_1",
        cid="AID_A",
        tag="witness",
        oobi="https://canonical.example:5642/oobi/WIT_1/controller",
    )

    assert remote_id["alias"] == "KF Witness WIT_1"
    assert remote_id["cid"] == "AID_A"
    assert remote_id["tag"] == "witness"
    assert remote_id["oobi"] == "https://canonical.example:5642/oobi/WIT_1/controller"
    assert "last-refresh" in remote_id


# ---------------------------------------------------------------------------
# Authentication doer tests (unchanged)
# ---------------------------------------------------------------------------

def test_authenticate_witnesses_uses_vault_receiptor(monkeypatch):
    calls = []
    emitted = []
    pinned = []

    def fake_now():
        return "2026-03-30T21:26:37.000000+00:00"

    monkeypatch.setattr("locksmith.core.rotating.helping.nowIso8601", fake_now)

    def fake_receipt(pre, sn=None, auths=None):
        calls.append((pre, sn, auths))
        if False:
            yield None

    hab = SimpleNamespace(
        name="alpha",
        pre="AID_ALPHA",
        kever=SimpleNamespace(
            delpre=None,
            wits=["WIT_1", "WIT_2"],
            sn=2,
            serder=SimpleNamespace(said="SAID_2"),
            toader=SimpleNamespace(num=2),
        ),
        db=SimpleNamespace(getWigs=lambda _key: [b"wig1", b"wig2"]),
    )

    app = SimpleNamespace(
        vault=SimpleNamespace(
            hby=object(),
            db=SimpleNamespace(
                idm=SimpleNamespace(
                    pin=lambda keys, val: pinned.append((keys, val.auth_pending))
                )
            ),
            signals=SimpleNamespace(
                emit_doer_event=lambda **kwa: emitted.append(kwa)
            ),
            receiptor=SimpleNamespace(receipt=fake_receipt),
            swain=SimpleNamespace(),
            postman=SimpleNamespace(),
        ),
        plugin_manager=None,
    )

    doer = AuthenticateWitnessesDoer(
        app=app,
        hab=hab,
        codes=["WIT_1:727667", "WIT_2:727667"],
        signal_bridge=app.vault.signals,
    )
    extended = []
    removed = []
    doer.extend = lambda doers=None, **kwa: extended.extend(doers or kwa.get("doers", []))
    doer.remove = lambda doers=None, **kwa: removed.extend(doers or kwa.get("doers", []))

    gen = doer.authenticate_do(lambda: 0.0)
    next(gen)
    try:
        next(gen)
    except StopIteration:
        pass

    assert calls == [(
        "AID_ALPHA",
        2,
        {
            "WIT_1": "727667#2026-03-30T21:26:37.000000+00:00",
            "WIT_2": "727667#2026-03-30T21:26:37.000000+00:00",
        },
    )]
    assert extended == []
    assert removed == []
    assert pinned[-1] == (("AID_ALPHA",), False)
    assert emitted[-1]["event_type"] == "witness_authentication_success"


def test_authenticate_witnesses_fails_when_receipts_are_insufficient(monkeypatch):
    emitted = []
    pinned = []

    def fake_receipt(pre, sn=None, auths=None):
        if False:
            yield None

    hab = SimpleNamespace(
        name="alpha",
        pre="AID_ALPHA",
        kever=SimpleNamespace(
            delpre=None,
            wits=["WIT_1", "WIT_2"],
            sn=2,
            serder=SimpleNamespace(said="SAID_2"),
            toader=SimpleNamespace(num=2),
        ),
        db=SimpleNamespace(getWigs=lambda _key: [b"wig1"]),
    )

    app = SimpleNamespace(
        vault=SimpleNamespace(
            hby=object(),
            db=SimpleNamespace(
                idm=SimpleNamespace(
                    pin=lambda keys, val: pinned.append((keys, val.auth_pending))
                )
            ),
            signals=SimpleNamespace(
                emit_doer_event=lambda **kwa: emitted.append(kwa)
            ),
            receiptor=SimpleNamespace(receipt=fake_receipt),
            swain=SimpleNamespace(),
            postman=SimpleNamespace(),
        ),
        plugin_manager=None,
    )

    doer = AuthenticateWitnessesDoer(
        app=app,
        hab=hab,
        codes=[],
        signal_bridge=app.vault.signals,
    )
    extended = []
    removed = []
    doer.extend = lambda doers=None, **kwa: extended.extend(doers or kwa.get("doers", []))
    doer.remove = lambda doers=None, **kwa: removed.extend(doers or kwa.get("doers", []))

    gen = doer.authenticate_do(lambda: 0.0)
    next(gen)
    try:
        next(gen)
    except StopIteration:
        pass

    assert extended == []
    assert removed == []
    assert pinned[-1] == (("AID_ALPHA",), True)
    assert emitted[-1]["event_type"] == "witness_authentication_failed"
    assert emitted[-1]["data"]["error"] == "Insufficient witness receipts: got 1, need 2"


def test_authenticate_witnesses_delegation_bypasses_vault_receiptor():
    emitted = []
    pinned = []
    delegations = []
    postman_calls = []

    def fake_send_event_to_delegator(**kwa):
        postman_calls.append(kwa)
        if False:
            yield None

    hab = SimpleNamespace(
        name="alpha",
        pre="AID_ALPHA",
        kever=SimpleNamespace(
            delpre="DEL_AID",
            wits=["WIT_1"],
            sn=2,
            prefixer=object(),
        ),
    )

    app = SimpleNamespace(
        vault=SimpleNamespace(
            hby=object(),
            db=SimpleNamespace(
                idm=SimpleNamespace(
                    pin=lambda keys, val: pinned.append((keys, val.auth_pending))
                )
            ),
            signals=SimpleNamespace(
                emit_doer_event=lambda **kwa: emitted.append(kwa)
            ),
            receiptor=SimpleNamespace(
                receipt=lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("delegated path should not use receiptor")
                )
            ),
            swain=SimpleNamespace(
                delegation=lambda **kwa: delegations.append(kwa),
                complete=lambda prefixer, seqner: True,
            ),
            postman=SimpleNamespace(sendEventToDelegator=fake_send_event_to_delegator),
        ),
        plugin_manager=None,
    )

    doer = AuthenticateWitnessesDoer(
        app=app,
        hab=hab,
        codes=[],
        signal_bridge=app.vault.signals,
    )

    gen = doer.authenticate_do(lambda: 0.0)
    next(gen)
    try:
        next(gen)
    except StopIteration:
        pass

    assert delegations == [
        {
            "pre": "AID_ALPHA",
            "sn": 2,
            "auths": {},
            "proxy": None,
        }
    ]
    assert len(postman_calls) == 1
    assert postman_calls[0]["hab"] is hab
    assert postman_calls[0]["sender"] is hab
    assert postman_calls[0]["fn"] == 2
    assert pinned[-1] == (("AID_ALPHA",), False)
    assert emitted[-1]["event_type"] == "witness_authentication_success"


def test_locksmith_receiptor_catchup_replays_full_kel(monkeypatch):
    calls = {}
    responded = []
    extended = []
    removed = []

    class FakeClient:
        def __init__(self):
            self.responses = []

        def respond(self):
            responded.append(self.responses.pop(0))

    client = FakeClient()
    client_doer = object()

    def fake_http_client(hab, wit):
        calls["http_client"] = (hab, wit)
        return client, client_doer

    def fake_stream_requests(client, dest, ims, path=None, headers=None):
        calls["stream"] = {
            "client": client,
            "dest": dest,
            "ims": bytes(ims),
            "path": path,
            "headers": headers,
        }
        return 2

    monkeypatch.setattr("locksmith.core.receipting.agenting.httpClient", fake_http_client)
    monkeypatch.setattr(
        "locksmith.core.receipting.agenting.httping.streamCESRRequests",
        fake_stream_requests,
    )

    hab = SimpleNamespace(replay=lambda pre=None: b"full-kel")
    hby = SimpleNamespace(prefixes={"AID_ALPHA"}, habs={"AID_ALPHA": hab})
    receiptor = LocksmithReceiptor(hby=hby)
    receiptor.extend = lambda doers=None, **kwa: extended.extend(doers or kwa.get("doers", []))
    receiptor.remove = lambda doers=None, **kwa: removed.extend(doers or kwa.get("doers", []))
    receiptor.tock = 0.0

    gen = receiptor.catchup("AID_ALPHA", "WIT_1")

    assert next(gen) == 0.0
    client.responses.append("resp-1")
    assert next(gen) == 0.0
    client.responses.append("resp-2")
    try:
        next(gen)
    except StopIteration:
        pass

    assert calls["http_client"] == (hab, "WIT_1")
    assert calls["stream"] == {
        "client": client,
        "dest": "WIT_1",
        "ims": b"full-kel",
        "path": None,
        "headers": None,
    }
    assert extended == [client_doer]
    assert removed == [client_doer]
    assert responded == ["resp-1", "resp-2"]
