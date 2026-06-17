"""Click CLI entry point for locksmith-publisher.

The publisher was rebuilt as a ``kli`` pipeline (``seal`` + ``kli`` +
``publish.anchor_release`` + ``appcast.build_appcast`` + ``s3_client``).
The bespoke KERI-event/receipt code that the original ``incept`` / ``anchor``
subcommands were built on (``witness_client``, ``release_anchor``,
``signing_context``, ``incept``, ``anchor``) has been retired — ``kli`` now
owns key custody, event signing, and witness-receipt collection.

The operator-facing invocation CLI for the new pipeline is a separate,
deferred task. Until it lands, the only live subcommand here is ``appcast``
(regenerate per-platform appcasts from S3); the former ``incept`` / ``anchor``
/ ``sign`` / ``submit`` / ``verify-ceremony`` commands are retired stubs that
point operators at the new pipeline.
"""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import click

from . import __version__
from .s3_client import S3


@click.group()
@click.version_option(__version__, prog_name="locksmith-publisher")
def cli() -> None:
    """Off-CI signing CLI for Locksmith releases."""


def _parse_s3_url(s3_url: str) -> tuple[str, str]:
    if not s3_url.startswith("s3://"):
        raise click.BadParameter(f"not an s3:// URL: {s3_url}")
    parsed = urllib.parse.urlparse(s3_url)
    return parsed.netloc, parsed.path.lstrip("/")


def _bundled_publisher_anchor_path() -> Path | None:
    """Resolve the bundled publisher_anchor.json shipped with locksmith.

    Returns ``None`` if the source tree's copy can't be located (e.g.,
    the publisher CLI was installed without the locksmith repo
    alongside it); the operator can always pass ``--publisher-aid``.
    """
    here = Path(__file__).resolve()
    # tools/publisher/src/locksmith_publisher/cli.py
    # → repo root is 4 parents up.
    for parent in here.parents:
        candidate = parent / "src" / "locksmith" / "release" / "publisher_anchor.json"
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Retired subcommands — the bespoke KERI-event/receipt pipeline they drove was
# replaced by the kli pipeline. The new operator invocation CLI is deferred.
# ---------------------------------------------------------------------------

_RETIRED_MSG = (
    "`{name}` was built on the bespoke KERI-event/receipt code (witness_client/"
    "release_anchor/signing_context/incept/anchor), which has been retired in "
    "favor of the kli pipeline (seal + kli + publish.anchor_release + "
    "appcast.build_appcast + s3_client.upload_release). The operator-facing "
    "invocation CLI for that pipeline is a separate, deferred task."
)


def _retired(name: str) -> None:
    click.echo(_RETIRED_MSG.format(name=name), err=True)
    raise SystemExit(2)


@cli.command("incept")
def incept_cmd() -> None:
    """[Retired] Publisher inception now runs through the kli pipeline."""
    _retired("incept")


@cli.command("anchor")
def anchor_cmd() -> None:
    """[Retired] Release anchoring now runs through publish.anchor_release."""
    _retired("anchor")


@cli.command("sign")
def sign_cmd() -> None:
    """[Retired] Use the kli pipeline (publish.anchor_release)."""
    _retired("sign")


@cli.command("submit")
def submit_cmd() -> None:
    """[Retired] Witness submission/receipts are handled by kli --receipt-endpoint."""
    _retired("submit")


@cli.command("verify-ceremony")
def verify_ceremony_cmd() -> None:
    """[Retired] Round-trip verification lives in the integration test suite."""
    _retired("verify-ceremony")


# ---------------------------------------------------------------------------
# appcast — live; backed by the surviving appcast.py + s3_client.py glue.
# ---------------------------------------------------------------------------


class _AppcastS3Adapter:
    """Adapter so the generator's mixed-style API (PascalCase boto3 ops +
    a couple snake_case helpers) can be backed by our S3 wrapper."""

    def __init__(self, s3):
        self._s3 = s3

    def list_release_versions(self, *, bucket):
        return self._s3.list_release_versions(bucket=bucket)

    def get_object(self, *, Bucket, Key):  # noqa: N803 — boto3-style
        return self._s3.get_object(bucket=Bucket, key=Key)

    def put_object(self, *, Bucket, Key, Body, ContentType):  # noqa: N803
        self._s3.put_object(
            bucket=Bucket, key=Key, data=Body, content_type=ContentType,
        )


@cli.command("appcast")
@click.option("--bucket", default="releases.keri.host", show_default=True,
              help="S3 bucket where releases/<version>/release-anchor-*.cesr lives "
                   "and appcast/v1/*.json will be written.")
@click.option("--publisher-aid", "publisher_aid", default=None,
              help="Publisher AID for the appcast `publisher_aid` field. "
                   "Defaults to the value in src/locksmith/release/publisher_anchor.json.")
@click.option("--publisher-kel-url", "publisher_kel_url",
              default="https://releases.keri.host/publisher/v1/kel.cesr",
              show_default=True,
              help="URL of the publisher's KEL stream the verifier replays.")
@click.option("--channel", default="stable", show_default=True)
def appcast_cmd(bucket: str, publisher_aid: str | None,
                publisher_kel_url: str, channel: str) -> None:
    """Regenerate per-platform appcasts from S3 and upload them.

    Walks every releases/<version>/ directory in the bucket, parses each
    release-anchor-<version>.cesr to extract the seal, and writes one
    appcast per platform to:

      s3://<bucket>/appcast/v1/{macos,windows}.json   (live, what apps poll)
      s3://<bucket>/appcast/archive/<timestamp>/{macos,windows}.json (history)

    Once these are live, the in-app Sparkle/WinSparkle updater in
    installed Locksmith builds can see new releases and KERI-verify them
    via the linked release anchor.
    """
    from .appcast import GeneratorConfig, generate_and_upload_appcasts

    if publisher_aid is None:
        bundled = _bundled_publisher_anchor_path()
        if bundled is None:
            raise click.UsageError(
                "could not determine publisher AID: pass --publisher-aid "
                "explicitly or run from the repo root."
            )
        try:
            publisher_aid = json.loads(bundled.read_text())["publisher_aid"]
        except (KeyError, ValueError) as ex:
            raise click.ClickException(
                f"could not read publisher_aid from {bundled}: {ex}"
            )

    click.echo(f"appcast: bucket={bucket} publisher_aid={publisher_aid}")
    s3 = _AppcastS3Adapter(S3.default())
    generate_and_upload_appcasts(
        s3=s3,
        config=GeneratorConfig(
            bucket=bucket,
            publisher_aid=publisher_aid,
            publisher_kel_url=publisher_kel_url,
            channel=channel,
        ),
    )
    click.echo(f"published s3://{bucket}/appcast/v1/macos.json")
    click.echo(f"published s3://{bucket}/appcast/v1/windows.json")


if __name__ == "__main__":
    cli()
