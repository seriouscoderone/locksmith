"""CLI surface tests after the bespoke KERI-event/receipt code was retired.

The original ``incept`` / ``anchor`` / ``sign`` / ``submit`` /
``verify-ceremony`` subcommands were built on the now-deleted
``witness_client`` / ``release_anchor`` / ``signing_context`` / ``incept`` /
``anchor`` modules. They are now retired stubs (exit 2, point at the kli
pipeline). The only live subcommand is ``appcast``; the operator-facing
invocation CLI for the new pipeline is a separate, deferred task.
"""
from click.testing import CliRunner

from locksmith_publisher.cli import cli


def test_cli_help_lists_appcast():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "appcast" in result.output


def test_cli_version_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_retired_incept_points_at_kli_pipeline():
    runner = CliRunner()
    result = runner.invoke(cli, ["incept"])
    assert result.exit_code != 0
    assert "kli pipeline" in result.output.lower()


def test_retired_anchor_points_at_kli_pipeline():
    runner = CliRunner()
    result = runner.invoke(cli, ["anchor"])
    assert result.exit_code != 0
    assert "kli pipeline" in result.output.lower()


def test_retired_sign_exits_nonzero():
    runner = CliRunner()
    result = runner.invoke(cli, ["sign"])
    assert result.exit_code != 0


def test_retired_submit_exits_nonzero():
    runner = CliRunner()
    result = runner.invoke(cli, ["submit"])
    assert result.exit_code != 0


def test_retired_verify_ceremony_exits_nonzero():
    runner = CliRunner()
    result = runner.invoke(cli, ["verify-ceremony"])
    assert result.exit_code != 0
