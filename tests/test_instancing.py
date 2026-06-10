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


def test_probe_does_not_raise_the_owner(qapp, tmp_path):
    # A probe (used to render the drawer's "running elsewhere" badge) must
    # NOT bring the owning instance to the front — only request_raise should.
    owner = InstanceCoordinator(base=str(tmp_path))
    raised = []
    owner.raise_window = lambda: raised.append(True)
    observer = InstanceCoordinator(base=str(tmp_path))
    try:
        owner.claim("vaultA")
        assert observer.probe("vaultA") is True
        for _ in range(5):
            qapp.processEvents()
        assert raised == [], "probing must not raise the owner's window"

        # But an explicit raise request still works.
        observer.request_raise("vaultA")
        for _ in range(5):
            qapp.processEvents()
        assert raised == [True], "request_raise should raise the owner"
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


def test_launch_new_with_origin_cascades_window_pos(qapp):
    # origin (200, 100) -> cascade down/right: x+48=248, y+48=148
    with patch.object(instancing.sys, "frozen", False, create=True), \
         patch.object(instancing.QProcess, "startDetached", return_value=(True, 0)) as sd:
        instancing.InstanceLauncher.launch_new("treasurer", origin_xy=(200, 100))
    args = sd.call_args[0]
    assert args[1] == ["-m", "locksmith.main", "--vault", "treasurer",
                       "--win-pos", "248,148"]


def test_launch_new_origin_from_top_left(qapp):
    # From the top-left corner, the new instance still steps down-and-right.
    with patch.object(instancing.sys, "frozen", False, create=True), \
         patch.object(instancing.QProcess, "startDetached", return_value=(True, 0)) as sd:
        instancing.InstanceLauncher.launch_new(None, origin_xy=(0, 0))
    args = sd.call_args[0]
    assert args[1] == ["-m", "locksmith.main", "--win-pos", "48,48"]


def test_launch_new_windows_frozen_does_not_carry_stale_args(qapp):
    # Cascade bug: a frozen Windows instance that was ITSELF launched with
    # --win-pos/--vault (i.e. a cascaded child) must not forward those stale
    # args to a new instance. Otherwise the child's old --win-pos is prepended
    # before the fresh one, and parse_window_pos (first occurrence) opens the
    # grandchild at the parent's launch position instead of cascading — so
    # only the first New Instance appears to cascade.
    stale_argv = ["Locksmith.exe", "--win-pos", "0,0", "--vault", "old"]
    with patch.object(instancing.sys, "frozen", True, create=True), \
         patch.object(instancing.sys, "platform", "win32"), \
         patch.object(instancing.sys, "argv", stale_argv), \
         patch.object(instancing.sys, "executable", "Locksmith.exe"), \
         patch.object(instancing.QProcess, "startDetached", return_value=(True, 0)) as sd:
        instancing.InstanceLauncher.launch_new(None, origin_xy=(200, 100))
    spawned = sd.call_args[0][1]
    # Exactly one --win-pos, and it's the FRESH cascade target (200+48,100+48).
    assert spawned.count("--win-pos") == 1, f"stale --win-pos carried over: {spawned}"
    assert spawned == ["--win-pos", "248,148"], spawned
    # A no-vault New Instance must not inherit the parent's --vault.
    assert "--vault" not in spawned, f"stale --vault carried over: {spawned}"
