"""Click CLI entry point for locksmith-publisher.

Subcommands:

* ``incept``    — bootstrap the publisher AID. One-time. Implemented in Phase 1.
* ``anchor``    — build, sign, and submit a release-anchoring ``ixn`` event.
                  Single-sig per Phase 1 deviation; manual on the operator's
                  laptop after CI has uploaded the binaries.

The publisher private key never enters CI. The flow is:

1. CI builds + code-signs DMG/MSI, uploads to ``s3://releases.keri.host/releases/X.Y.Z/``.
2. Operator runs ``locksmith-publisher anchor --version X.Y.Z`` on their laptop.
   The CLI downloads the artifacts, computes hashes, builds the release seal,
   signs the ixn event with the locally-stored publisher key, submits to the
   witness federation, collects receipts, and uploads the anchor bundle back
   to S3 alongside the artifacts.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

import click

from . import __version__
from .release_anchor import (
    ArtifactInput,
    ReleaseAnchorRequest,
    build_release_anchor,
    write_release_anchor_files,
)
from .s3_client import S3
from .witness_client import WitnessClient, WitnessThresholdNotMet
from .witnesses import default_witness_pool


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
@click.option(
    "--witness-pool-oobi",
    required=True,
    multiple=True,
    help="OOBI URL of a witness AID. Repeat for each witness (>=3 required).",
)
@click.option(
    "--toad", type=int, default=2, show_default=True,
    help="Witness threshold (toad).",
)
@click.option(
    "--quorum", type=int, default=2, show_default=True,
    help="Signer quorum required (default: 2-of-3).",
)
@click.option(
    "--signers", type=int, default=3, show_default=True,
    help="Total number of signer devices.",
)
@click.option(
    "--dry-run/--production", default=True, show_default=True,
    help="--dry-run uses ephemeral staging witnesses.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    required=True,
    help="Directory for publisher_anchor.json + KEL artifacts.",
)
@click.option(
    "--yubikey-slots",
    multiple=True,
    default=("9c", "9c", "9c"),
    show_default=True,
    help="PIV slot per signer. Default 9c (Digital Signature).",
)
def incept_cmd(
    witness_pool_oobi: tuple[str, ...],
    toad: int,
    quorum: int,
    signers: int,
    dry_run: bool,
    output_dir: Path,
    yubikey_slots: tuple[str, ...],
) -> None:
    """Bootstrap the publisher AID. One-time ceremony."""
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


def _parse_s3_url(s3_url: str) -> tuple[str, str]:
    if not s3_url.startswith("s3://"):
        raise click.BadParameter(f"not an s3:// URL: {s3_url}")
    parsed = urllib.parse.urlparse(s3_url)
    return parsed.netloc, parsed.path.lstrip("/")


def _open_publisher_keystore(
    *,
    keystore_name: str,
    keystore_base: str,
    passphrase: str,
):
    """Open the publisher Habery. Test seam — patched by ``tests/unit/publisher``.

    Production: opens the operator's persistent Habery (passphrase unlocks the
    bran-encrypted keystore). Tests substitute a temp Habery via monkeypatch.
    """
    from keri.app import habbing

    return habbing.Habery(
        name=keystore_name,
        base=keystore_base,
        bran=passphrase,
    )


@cli.command("anchor")
@click.option("--version", "version_str", required=True,
              help="Release version (X.Y.Z) that CI has already uploaded.")
@click.option(
    "--macos-artifact",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    help="Local path to the .dmg. If omitted, downloads from --candidates-url.",
)
@click.option(
    "--windows-artifact",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    help="Local path to the .msi. If omitted, downloads from --candidates-url.",
)
@click.option(
    "--candidates-url",
    default="s3://releases.keri.host/releases/",
    show_default=True,
    help="S3 URL prefix where CI uploaded the artifacts. The CLI appends version/.",
)
@click.option(
    "--keystore-name", required=True,
    help="Name of the publisher Habery (must contain the live publisher AID).",
)
@click.option(
    "--keystore-base", default="",
    help="Base directory for the Habery (default: keripy's default location).",
)
@click.option(
    "--passphrase",
    envvar="LOCKSMITH_PUBLISHER_PASSPHRASE",
    required=True,
    help="Passphrase that unlocks the publisher Habery.",
)
@click.option(
    "--released-at", required=True,
    help="ISO-8601 timestamp for the release (e.g., 2026-05-28T14:30:00Z).",
)
@click.option(
    "--is-major", is_flag=True, default=False,
    help="Flag the release as a major version bump.",
)
@click.option(
    "--is-critical", is_flag=True, default=False,
    help="Flag the release as critical (security/data-loss fix).",
)
@click.option(
    "--previous-version", default=None,
    help="Prior release version (for the seal's previous_version field).",
)
@click.option(
    "--release-notes-said", default="EHshNoReleaseNotesSAIDProvidedXXXXXXXXXXXXX",
    show_default=True,
    help="SAID of the release-notes ACDC. Use a placeholder until Phase 5.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    required=True,
    help="Local directory where release-anchor-X.Y.Z.cesr is written.",
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Build + sign but do NOT submit to witnesses or upload to S3.",
)
def anchor_cmd(
    version_str: str,
    macos_artifact: Path | None,
    windows_artifact: Path | None,
    candidates_url: str,
    keystore_name: str,
    keystore_base: str,
    passphrase: str,
    released_at: str,
    is_major: bool,
    is_critical: bool,
    previous_version: str | None,
    release_notes_said: str,
    output_dir: Path,
    dry_run: bool,
) -> None:
    """Build, sign, and submit a release-anchoring ixn event.

    Manual flow (per Phase 4 user deviation #2): no countersign step,
    no CI signing. The publisher's signing key lives only in the local
    Habery keystore on this machine.
    """
    # 1. Resolve artifact paths — fetch from S3 if not provided locally.
    artifacts: list[ArtifactInput] = []
    s3_client: S3 | None = None
    bucket, prefix = _parse_s3_url(candidates_url.rstrip("/") + "/")

    for platform, ext, local_path in [
        ("macos", "dmg", macos_artifact),
        ("windows", "msi", windows_artifact),
    ]:
        if local_path is not None:
            artifacts.append(ArtifactInput.from_path(platform=platform, path=local_path))
            continue
        # Download from S3 to a tmp file under output_dir.
        if s3_client is None:
            s3_client = S3.default()
        key = prefix + f"{version_str}/Locksmith-{version_str}.{ext}"
        click.echo(f"fetching s3://{bucket}/{key} ...")
        body = s3_client.get_object(bucket=bucket, key=key)
        output_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = output_dir / f"Locksmith-{version_str}.{ext}"
        tmp_path.write_bytes(body)
        artifacts.append(ArtifactInput.from_path(platform=platform, path=tmp_path))

    request = ReleaseAnchorRequest(
        version=version_str,
        channel="stable",
        released_at=released_at,
        is_major=is_major,
        is_critical=is_critical,
        previous_version=previous_version,
        minimum_system_versions={"macos": "13.0", "windows": "10.0.19041"},
        artifacts=tuple(artifacts),
        release_notes_said=release_notes_said,
    )

    # 2. Open the publisher Habery, locate the Hab, sign the ixn.
    hby = _open_publisher_keystore(
        keystore_name=keystore_name,
        keystore_base=keystore_base,
        passphrase=passphrase,
    )
    try:
        hab = hby.habs[list(hby.habs.keys())[0]] if hby.habs else None
        # When habs is keyed by AID, just take the first one — the publisher
        # keystore should contain exactly one Hab.
        if hab is None:
            raise click.ClickException(
                f"keystore {keystore_name!r} has no Hab; "
                f"run `locksmith-publisher incept` first"
            )
        click.echo(f"signing ixn for {request.version} via publisher AID {hab.pre}")
        anchor = build_release_anchor(hab=hab, request=request)
    finally:
        hby.close()

    # 3. Optionally submit to witnesses.
    receipts_cesr: bytes | None = None
    if dry_run:
        click.echo("[dry-run] would submit to witnesses + upload to S3")
    else:
        pool = default_witness_pool()
        wc = WitnessClient(
            witness_urls=[w.base_url for w in pool],
            threshold=3,
        )
        click.echo(f"submitting ixn (said={anchor.said}) to {len(pool)} witnesses ...")
        try:
            receipts = wc.submit_event(anchor.raw)
        except WitnessThresholdNotMet as ex:
            raise click.ClickException(
                f"witness threshold not met: collected={ex.collected} "
                f"threshold={ex.threshold}"
            )
        click.echo(f"collected {len(receipts)} receipts")
        receipts_cesr = b"".join(r.cesr_bytes for r in receipts)

    # 4. Persist locally.
    paths = write_release_anchor_files(
        anchor,
        out_dir=output_dir,
        version=version_str,
        receipts_cesr=receipts_cesr,
    )
    click.echo(f"wrote {paths['event']}")
    if "receipts" in paths:
        click.echo(f"wrote {paths['receipts']}")
    click.echo(f"wrote {paths['meta']}")

    # 5. Upload to S3 unless dry-run.
    if dry_run:
        click.echo("[dry-run] skipping S3 upload")
        return

    if s3_client is None:
        s3_client = S3.default()
    s3_key_event = f"releases/{version_str}/release-anchor-{version_str}.cesr"
    click.echo(f"uploading to s3://releases.keri.host/{s3_key_event}")
    s3_client.put_file(
        bucket="releases.keri.host",
        key=s3_key_event,
        path=paths["event"],
        content_type="application/cesr",
    )
    if "receipts" in paths:
        s3_key_receipts = f"releases/{version_str}/release-anchor-{version_str}.receipts.cesr"
        s3_client.put_file(
            bucket="releases.keri.host",
            key=s3_key_receipts,
            path=paths["receipts"],
            content_type="application/cesr",
        )
    # Update publisher pointer for verifier convenience.
    s3_client.put_object(
        bucket="releases.keri.host",
        key="publisher/v1/latest.json",
        data=json.dumps({
            "latest_version": version_str,
            "anchor_said": anchor.said,
            "anchor_sn": anchor.sn,
        }).encode(),
        content_type="application/json",
    )
    click.echo(f"published {version_str} (SAID {anchor.said})")


# Legacy Phase 1 stubs kept around for backward compatibility — they now point
# users at the new `anchor` subcommand.

@cli.command("sign")
@click.option("--version", required=True, help="Release version string (X.Y.Z).")
def sign_cmd(version: str) -> None:
    """[Deprecated in Phase 4] Use `anchor` for the combined sign+submit flow."""
    click.echo(
        "The `sign`/`countersign`/`submit` triple was the Phase 4 plan's multisig "
        "design. Phase 4 settled on a single-sig publisher; the combined `anchor` "
        "subcommand replaces all three. See `locksmith-publisher anchor --help`.",
        err=True,
    )
    sys.exit(2)


@cli.command("submit")
@click.option("--signed", required=True, type=click.Path(exists=False))
def submit_cmd(signed: str) -> None:
    """[Deprecated in Phase 4] Use `anchor` for the combined sign+submit flow."""
    click.echo(
        "The `sign`/`submit` subcommands were the Phase 4 plan's multisig design. "
        "Phase 4 settled on a single-sig publisher; the combined `anchor` "
        "subcommand replaces both. See `locksmith-publisher anchor --help`.",
        err=True,
    )
    sys.exit(2)


@cli.command("verify-ceremony")
@click.option("--anchor", "anchor_path", required=True,
              type=click.Path(exists=False))
def verify_ceremony_cmd(anchor_path: str) -> None:
    """[Phase 4] Re-verify a finalized release anchor against witnesses end-to-end."""
    _not_yet("verify-ceremony")


if __name__ == "__main__":
    cli()
