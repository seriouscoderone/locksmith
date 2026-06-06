from locksmith.main import parse_vault_arg, parse_window_pos


def test_parse_vault_arg_present():
    assert parse_vault_arg(["prog", "--vault", "treasurer"]) == "treasurer"


def test_parse_vault_arg_absent():
    assert parse_vault_arg(["prog"]) is None


def test_parse_vault_arg_ignores_trailing_flag_without_value():
    assert parse_vault_arg(["prog", "--vault"]) is None


def test_parse_window_pos_present():
    assert parse_window_pos(["prog", "--win-pos", "120,340"]) == (120, 340)


def test_parse_window_pos_absent():
    assert parse_window_pos(["prog"]) is None


def test_parse_window_pos_malformed_returns_none():
    assert parse_window_pos(["prog", "--win-pos", "nope"]) is None
    assert parse_window_pos(["prog", "--win-pos"]) is None
