from types import SimpleNamespace

from locksmith.core.apping import LocksmithApplication
from locksmith.core.instancing import InstanceCoordinator


def test_application_constructs_a_coordinator(qapp, tmp_path):
    config = SimpleNamespace(
        base=str(tmp_path),
        protected_url="",
        api_aid="",
        unprotected_url="",
    )
    app = LocksmithApplication(config=config)
    assert isinstance(app.coordinator, InstanceCoordinator)


def test_close_vault_releases_the_coordinator_claim(qapp, tmp_path):
    config = SimpleNamespace(
        base=str(tmp_path),
        protected_url="",
        api_aid="",
        unprotected_url="",
    )
    app = LocksmithApplication(config=config)
    # Simulate an open vault holding a claim.
    app.coordinator.claim("treasurer")
    app.name = "treasurer"
    app.vault = SimpleNamespace(db=None, plugin_manager=None)
    app.qtask = SimpleNamespace(shutdown=lambda: None, cleanup=lambda: None)
    app.plugin_manager = SimpleNamespace(on_vault_closed=lambda v: None)

    app.close_vault()

    # The vault's local-socket server must have been released.
    assert app.coordinator.probe("treasurer") is False
