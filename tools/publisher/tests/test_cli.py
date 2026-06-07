"""Phase 1 CLI surface tests, updated for Phase 4's combined ``anchor`` command.

Phase 4 collapsed ``sign`` + ``countersign`` + ``submit`` into a single
``anchor`` command (single-sig publisher, manual signing on operator laptop).
The old stubs now print a deprecation note pointing at ``anchor``.
"""
from click.testing import CliRunner

from locksmith_publisher.cli import cli


def test_cli_help_lists_all_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("incept", "anchor", "verify-ceremony"):
        assert cmd in result.output


def test_cli_version_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_deprecated_sign_points_at_anchor():
    """Phase 4 superseded `sign` with the combined `anchor` command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["sign", "--version", "1.0.0"])
    assert result.exit_code != 0
    assert "anchor" in result.output.lower()


def test_deprecated_submit_points_at_anchor():
    runner = CliRunner()
    result = runner.invoke(cli, ["submit", "--signed", "/tmp/whatever.cesr"])
    assert result.exit_code != 0
    assert "anchor" in result.output.lower()


def test_verify_ceremony_is_still_stubbed():
    """verify-ceremony remains a Phase 4 follow-up stub."""
    runner = CliRunner()
    result = runner.invoke(cli, ["verify-ceremony", "--anchor", "/tmp/whatever.cesr"])
    assert result.exit_code != 0
    assert "phase 4" in result.output.lower() or "not implemented" in result.output.lower()
