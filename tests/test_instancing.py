import socket

from locksmith.core.instancing import vault_server_name, find_free_port, InstanceCoordinator


def test_vault_server_name_is_stable_and_unique():
    a1 = vault_server_name("/base", "treasurer")
    a2 = vault_server_name("/base", "treasurer")
    b = vault_server_name("/base", "auditor")
    c = vault_server_name("/other", "treasurer")
    assert a1 == a2                       # stable across calls
    assert a1 != b                        # different vault -> different name
    assert a1 != c                        # different base -> different name
    assert a1.startswith("host.keri.locksmith.vault.")
    assert vault_server_name(None, "x") == vault_server_name("", "x")


def test_find_free_port_returns_bindable_port():
    port = find_free_port(start=5621)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", port))


def test_find_free_port_skips_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("", 0))
        taken = occupied.getsockname()[1]
        occupied.listen(1)
        got = find_free_port(start=taken)
        assert got != taken
        assert got >= taken


def test_claim_grants_when_unowned(qapp, tmp_path):
    coord = InstanceCoordinator(base=str(tmp_path))
    try:
        assert coord.claim("vaultA") is True
        # Idempotent: re-claiming a vault we already own returns True.
        assert coord.claim("vaultA") is True
    finally:
        coord.release_all()


def test_claim_denied_when_owned_by_another_coordinator(qapp, tmp_path):
    owner = InstanceCoordinator(base=str(tmp_path))
    raised = []
    owner.raise_window = lambda: raised.append(True)
    other = InstanceCoordinator(base=str(tmp_path))
    try:
        assert owner.claim("vaultA") is True
        # Second coordinator sees the vault as owned -> denied.
        assert other.claim("vaultA") is False
        qapp.processEvents()  # let the owner's newConnection fire
        qapp.processEvents()
        assert raised == [True]  # owner was asked to raise its window
    finally:
        owner.release_all()
        other.release_all()


def test_release_frees_the_vault_for_reclaim(qapp, tmp_path):
    a = InstanceCoordinator(base=str(tmp_path))
    b = InstanceCoordinator(base=str(tmp_path))
    try:
        assert a.claim("vaultA") is True
        a.release("vaultA")
        # After release, another coordinator can claim it.
        assert b.claim("vaultA") is True
    finally:
        a.release_all()
        b.release_all()


def test_probe_reports_running_state(qapp, tmp_path):
    owner = InstanceCoordinator(base=str(tmp_path))
    observer = InstanceCoordinator(base=str(tmp_path))
    try:
        assert observer.probe("vaultA") is False  # nobody owns it yet
        owner.claim("vaultA")
        assert observer.probe("vaultA") is True    # now owned
    finally:
        owner.release_all()
        observer.release_all()


from unittest.mock import patch

from locksmith.core import instancing


def test_launch_new_dev_mode_uses_module_invocation(qapp):
    with patch.object(instancing.sys, "frozen", False, create=True), \
         patch.object(instancing.QProcess, "startDetached", return_value=(True, 0)) as sd:
        instancing.InstanceLauncher.launch_new("treasurer")
    sd.assert_called_once()
    args = sd.call_args[0]
    # dev mode: python -m locksmith.main --vault treasurer
    assert args[1] == ["-m", "locksmith.main", "--vault", "treasurer"]


def test_launch_new_without_vault_omits_vault_arg(qapp):
    with patch.object(instancing.sys, "frozen", False, create=True), \
         patch.object(instancing.QProcess, "startDetached", return_value=(True, 0)) as sd:
        instancing.InstanceLauncher.launch_new(None)
    args = sd.call_args[0]
    assert args[1] == ["-m", "locksmith.main"]
