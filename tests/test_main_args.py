from locksmith.main import parse_vault_arg


def test_parse_vault_arg_present():
    assert parse_vault_arg(["prog", "--vault", "treasurer"]) == "treasurer"


def test_parse_vault_arg_absent():
    assert parse_vault_arg(["prog"]) is None


def test_parse_vault_arg_ignores_trailing_flag_without_value():
    assert parse_vault_arg(["prog", "--vault"]) is None
