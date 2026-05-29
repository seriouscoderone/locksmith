from click.testing import CliRunner

from locksmith_publisher.cli import cli


def test_cli_help_lists_all_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("incept", "sign", "countersign", "submit", "verify-ceremony"):
        assert cmd in result.output


def test_cli_version_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_sign_is_stubbed_in_phase1():
    runner = CliRunner()
    result = runner.invoke(cli, ["sign", "--version", "1.0.0", "--candidates-url", "s3://x"])
    assert result.exit_code != 0
    assert "phase 4" in result.output.lower() or "not implemented" in result.output.lower()


def test_countersign_is_stubbed_in_phase1():
    runner = CliRunner()
    result = runner.invoke(cli, ["countersign", "--partial", "/tmp/whatever.cesr"])
    assert result.exit_code != 0
    assert "phase 4" in result.output.lower() or "not implemented" in result.output.lower()


def test_submit_is_stubbed_in_phase1():
    runner = CliRunner()
    result = runner.invoke(cli, ["submit", "--signed", "/tmp/whatever.cesr"])
    assert result.exit_code != 0
    assert "phase 4" in result.output.lower() or "not implemented" in result.output.lower()


def test_verify_ceremony_is_stubbed_in_phase1():
    runner = CliRunner()
    result = runner.invoke(cli, ["verify-ceremony", "--anchor", "/tmp/whatever.cesr"])
    assert result.exit_code != 0
    assert "phase 4" in result.output.lower() or "not implemented" in result.output.lower()
