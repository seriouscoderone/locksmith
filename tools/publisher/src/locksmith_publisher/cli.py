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
from .signing_context import (
    HabSigningContext,
    PemFileSigningContext,
    PublisherStateFile,
)
from .witness_client import (
    WitnessClient,
    WitnessThresholdNotMet,
    WitnessUnreachable,
)
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

    Production (only when --key-source habery is selected): opens the
    operator's persistent Habery (passphrase unlocks the bran-encrypted
    keystore). Tests substitute a temp Habery via monkeypatch.

    The Phase 1 inception ceremony did NOT create a Habery — it persisted
    a single encrypted Ed25519 PEM file. The default ``--key-source pem``
    bypasses this function entirely and uses ``PemFileSigningContext``.
    """
    from keri.app import habbing

    return habbing.Habery(
        name=keystore_name,
        base=keystore_base,
        bran=passphrase,
    )


def _default_keys_dir() -> Path:
    return Path.home() / ".locksmith-publisher" / "keys-production" / "current"


def _default_state_file() -> Path:
    return Path.home() / ".locksmith-publisher" / "state.json"


def _bundled_publisher_anchor_path() -> Path | None:
    """Resolve the bundled publisher_anchor.json shipped with locksmith.

    Returns ``None`` if the source tree's copy can't be located (e.g.,
    the publisher CLI was installed without the locksmith repo
    alongside it); the operator can always pass the seed values
    manually via ``--seed-aid``/``--seed-sn``/``--seed-digest``.
    """
    here = Path(__file__).resolve()
    # tools/publisher/src/locksmith_publisher/cli.py
    # → repo root is 4 parents up.
    for parent in here.parents:
        candidate = parent / "src" / "locksmith" / "release" / "publisher_anchor.json"
        if candidate.is_file():
            return candidate
    return None


def _seed_pem_state(
    *,
    ctx: PemFileSigningContext,
    bundled_anchor_path: Path | None,
    witness_client_factory,
    seed_aid: str | None,
    seed_sn: int | None,
    seed_digest: str | None,
) -> None:
    """Populate the PEM context's state file from one of three sources.

    Priority:
    1. Operator-supplied ``--seed-*`` flags (explicit override).
    2. Bundled ``src/locksmith/release/publisher_anchor.json`` (very first
       ixn after inception — the embedded anchor IS the KEL tip).
    3. ``WitnessClient.query_state(aid)`` against the federation.

    Falls through silently if the state file is already populated.
    """
    if ctx.state_file.has_tip:
        return  # state already known — nothing to do

    if seed_aid is not None and seed_sn is not None and seed_digest is not None:
        ctx.seed_state_from_anchor(
            aid=seed_aid, sn=seed_sn, event_digest=seed_digest
        )
        return

    if bundled_anchor_path is not None and bundled_anchor_path.is_file():
        body = json.loads(bundled_anchor_path.read_text())
        if body.get("publisher_aid") == ctx.publisher_aid:
            ctx.seed_state_from_anchor(
                aid=body["publisher_aid"],
                sn=int(body["embedded_kel_sn"]),
                event_digest=body["embedded_kel_hash"],
            )
            return

    # Last resort: ask the witnesses.
    try:
        wc = witness_client_factory()
        ctx.seed_state_from_witnesses(wc)
        return
    except WitnessUnreachable as ex:
        raise click.ClickException(
            f"could not seed publisher KEL tip: no local state, no bundled "
            f"anchor for AID {ctx.publisher_aid!r}, and no witness reached "
            f"({ex}). Use --seed-aid/--seed-sn/--seed-digest to override."
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
    "--key-source",
    type=click.Choice(["pem", "habery"]),
    default="pem",
    show_default=True,
    help="Where the publisher signing key lives. 'pem' (default, matches "
         "Phase 1 production reality) loads the encrypted Ed25519 PEM at "
         "--keys-dir. 'habery' opens a keripy Habery — kept for tests and "
         "for any future migration to Habery-based storage.",
)
# --- PEM-mode options ---
@click.option(
    "--publisher-aid",
    default=None,
    help="Expected publisher AID prefix (PEM mode). If omitted, read from the "
         "bundled src/locksmith/release/publisher_anchor.json.",
)
@click.option(
    "--keys-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="PEM mode: directory containing key-1.enc.pem. "
         "Default: ~/.locksmith-publisher/keys-production/current/",
)
@click.option(
    "--state-file",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="PEM mode: JSON file tracking the publisher KEL tip. "
         "Default: ~/.locksmith-publisher/state.json",
)
@click.option(
    "--seed-aid",
    default=None,
    help="PEM mode: manually seed the publisher AID into the state file "
         "(overrides the bundled anchor + witness fallback).",
)
@click.option(
    "--seed-sn",
    type=int,
    default=None,
    help="PEM mode: manually seed the current KEL sn into the state file.",
)
@click.option(
    "--seed-digest",
    default=None,
    help="PEM mode: manually seed the last KEL event SAID into the state file.",
)
# --- Habery-mode options (kept for tests + --key-source habery) ---
@click.option(
    "--keystore-name", default=None,
    help="Habery mode only: name of the publisher Habery.",
)
@click.option(
    "--keystore-base", default="",
    help="Habery mode only: base directory for the Habery.",
)
# --- Passphrase is shared (Habery bran OR PEM file decrypt) ---
@click.option(
    "--passphrase",
    envvar="LOCKSMITH_PUBLISHER_PASSPHRASE",
    required=True,
    help="Passphrase that unlocks the publisher key material. "
         "PEM mode: decrypts the on-disk Ed25519 PEM. "
         "Habery mode: bran for the Habery keystore.",
)
@click.option(
    "--released-at", default=None,
    help=("ISO-8601 timestamp for the release (e.g., 2026-05-28T14:30:00Z). "
          "Defaults to the current UTC time when omitted."),
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
    key_source: str,
    publisher_aid: str | None,
    keys_dir: Path | None,
    state_file: Path | None,
    seed_aid: str | None,
    seed_sn: int | None,
    seed_digest: str | None,
    keystore_name: str | None,
    keystore_base: str,
    passphrase: str,
    released_at: str | None,
    is_major: bool,
    is_critical: bool,
    previous_version: str | None,
    release_notes_said: str,
    output_dir: Path,
    dry_run: bool,
) -> None:
    """Build, sign, and submit a release-anchoring ixn event.

    Manual flow (per Phase 4 user deviation #2): no countersign step,
    no CI signing. The publisher's signing key lives only on this
    machine — either as an encrypted Ed25519 PEM file at
    ``~/.locksmith-publisher/keys-production/current/`` (default,
    matches Phase 1 production reality) or as a keripy Habery
    (``--key-source habery``, kept for Phase 4 tests).

    PEM-mode KEL-tip discovery falls through three sources in order:
    1. ``--seed-aid`` / ``--seed-sn`` / ``--seed-digest`` flags
    2. ``--state-file`` (populated after each successful anchor)
    3. Bundled ``src/locksmith/release/publisher_anchor.json``
       (used for the very first ixn after inception)
    4. Witness federation ``query_state`` fallback
    """
    if released_at is None:
        from datetime import datetime, timezone
        released_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        click.echo(f"--released-at not given; defaulting to {released_at}")

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

    # 2. Build the signing context — PEM-on-disk (default, production) or Habery
    #    (test / legacy). Sign the ixn.
    if key_source == "habery":
        if not keystore_name:
            raise click.UsageError(
                "--keystore-name is required when --key-source=habery"
            )
        hby = _open_publisher_keystore(
            keystore_name=keystore_name,
            keystore_base=keystore_base,
            passphrase=passphrase,
        )
        try:
            hab = hby.habs[list(hby.habs.keys())[0]] if hby.habs else None
            if hab is None:
                raise click.ClickException(
                    f"keystore {keystore_name!r} has no Hab; "
                    f"run `locksmith-publisher incept` first"
                )
            click.echo(
                f"signing ixn for {request.version} via publisher AID {hab.pre} "
                f"(habery backend)"
            )
            ctx = HabSigningContext(hab=hab)
            anchor = build_release_anchor(context=ctx, request=request)
        finally:
            hby.close()
    else:
        # --- PEM mode (production default) ---
        keys_dir_resolved = keys_dir or _default_keys_dir()
        state_path_resolved = state_file or _default_state_file()

        # Resolve expected publisher AID: explicit flag → bundled anchor.
        expected_aid = publisher_aid
        bundled_path = _bundled_publisher_anchor_path()
        if expected_aid is None and bundled_path is not None:
            try:
                expected_aid = json.loads(bundled_path.read_text())["publisher_aid"]
            except (KeyError, ValueError) as ex:
                raise click.ClickException(
                    f"could not read publisher_aid from {bundled_path}: {ex}"
                )
        if not expected_aid:
            raise click.UsageError(
                "could not determine publisher AID: pass --publisher-aid "
                "explicitly or ensure src/locksmith/release/publisher_anchor.json "
                "is reachable from the publisher CLI install."
            )

        state = PublisherStateFile.load(state_path_resolved)
        ctx = PemFileSigningContext(
            publisher_aid=expected_aid,
            keys_dir=keys_dir_resolved,
            passphrase=passphrase,
            state_file=state,
        )

        # Seed the KEL tip if needed (first ixn after inception, or fresh box).
        pool = default_witness_pool()
        wc_factory = lambda: WitnessClient(  # noqa: E731
            witness_urls=[w.base_url for w in pool], threshold=3
        )
        _seed_pem_state(
            ctx=ctx,
            bundled_anchor_path=bundled_path,
            witness_client_factory=wc_factory,
            seed_aid=seed_aid,
            seed_sn=seed_sn,
            seed_digest=seed_digest,
        )

        click.echo(
            f"signing ixn for {request.version} via publisher AID "
            f"{ctx.prefix} (pem backend, sn={ctx.current_sn} → {ctx.current_sn + 1})"
        )
        anchor = build_release_anchor(context=ctx, request=request)

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
            # Witness rejection — state must NOT advance. The local
            # state file is unchanged at this point because we now only
            # commit_event() after a successful submission.
            raise click.ClickException(
                f"witness threshold not met: collected={ex.collected} "
                f"threshold={ex.threshold}"
            )
        click.echo(f"collected {len(receipts)} receipts")
        receipts_cesr = b"".join(r.cesr_bytes for r in receipts)
        # Quorum met — durably advance local KEL-tip state to match.
        ctx.commit_event(anchor.serder)

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
