"""Click CLI entry point for locksmith-publisher.

Only the `incept` subcommand is fully implemented in Phase 1.
The release signing subcommands are stubs that fail loudly until Phase 4.
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__


def _not_yet(name: str) -> None:
    click.echo(
        f"`{name}` is not implemented in Phase 1. It will be added in Phase 4 "
        "(release signing ceremony).",
        err=True,
    )
    sys.exit(2)


@click.group()
@click.version_option(__version__, prog_name="locksmith-publisher")
def cli() -> None:
    """Off-CI signing CLI for Locksmith releases."""


@cli.command("incept")
@click.option("--witness-pool-oobi", required=True, multiple=True,
              help="OOBI URL of a witness AID to include in the inception event. Repeat for each witness (>=3 required).")
@click.option("--toad", type=int, default=2, show_default=True,
              help="Threshold of accountable duplicity (number of witness receipts required).")
@click.option("--quorum", type=int, default=2, show_default=True,
              help="Signer quorum required (2-of-3 by default).")
@click.option("--signers", type=int, default=3, show_default=True,
              help="Total number of signer devices.")
@click.option("--dry-run/--production", default=True, show_default=True,
              help="--dry-run uses ephemeral staging witnesses and writes outputs to a tmp dir. --production targets the real publisher.")
@click.option("--output-dir", type=click.Path(file_okay=False, path_type=Path), required=True,
              help="Directory where publisher_anchor.json and KEL artifacts are written.")
@click.option("--yubikey-slots", multiple=True, default=("9c", "9c", "9c"), show_default=True,
              help="PIV slot identifier for each signer device. Default 9c (Digital Signature). Provide once per signer.")
def incept_cmd(
    witness_pool_oobi: tuple[str, ...],
    toad: int,
    quorum: int,
    signers: int,
    dry_run: bool,
    output_dir: Path,
    yubikey_slots: tuple[str, ...],
) -> None:
    """Bootstrap the 2-of-3 multisig publisher AID. One-time ceremony."""
    from .incept import run_inception_ceremony

    run_inception_ceremony(
        witness_oobis=list(witness_pool_oobi),
        toad=toad,
        quorum=quorum,
        signers=signers,
        dry_run=dry_run,
        output_dir=output_dir,
        yubikey_slots=list(yubikey_slots),
    )


@cli.command("sign")
@click.option("--version", required=True, help="Release version string (X.Y.Z).")
@click.option("--candidates-url", required=True, help="S3 URL of the release-candidate.json from CI.")
def sign_cmd(version: str, candidates_url: str) -> None:
    """[Phase 4] Signer 1: produce a partial release-anchor signature."""
    _not_yet("sign")


@cli.command("countersign")
@click.option("--partial", required=True, type=click.Path(exists=False),
              help="Path to release-anchor-X.Y.Z.partial.cesr produced by `sign`.")
def countersign_cmd(partial: str) -> None:
    """[Phase 4] Signer 2: add the second signature to reach quorum."""
    _not_yet("countersign")


@cli.command("submit")
@click.option("--signed", required=True, type=click.Path(exists=False),
              help="Path to the quorum-signed release-anchor-X.Y.Z.cesr.")
def submit_cmd(signed: str) -> None:
    """[Phase 4] Submit signed event to witnesses, gather receipts, upload to S3."""
    _not_yet("submit")


@cli.command("verify-ceremony")
@click.option("--anchor", required=True, type=click.Path(exists=False),
              help="Path to a finalized release-anchor.cesr file.")
def verify_ceremony_cmd(anchor: str) -> None:
    """[Phase 4] Re-verify a finalized release anchor against witnesses end-to-end."""
    _not_yet("verify-ceremony")


if __name__ == "__main__":
    cli()
