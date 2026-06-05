import socket

from locksmith.core.instancing import vault_server_name, find_free_port


def test_vault_server_name_is_stable_and_unique():
    a1 = vault_server_name("/base", "treasurer")
    a2 = vault_server_name("/base", "treasurer")
    b = vault_server_name("/base", "auditor")
    c = vault_server_name("/other", "treasurer")
    assert a1 == a2                       # stable across calls
    assert a1 != b                        # different vault -> different name
    assert a1 != c                        # different base -> different name
    assert a1.startswith("host.keri.locksmith.vault.")


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
