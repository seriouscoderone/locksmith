"""Click CLI entry point for locksmith-publisher.

The publisher was rebuilt as a ``kli`` pipeline (``seal`` + ``kli`` +
``publish.anchor_release`` + ``appcast.build_appcast`` + ``s3_client``).
``kli`` now owns key custody, event signing, and witness-receipt collection.
"""
from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path

import click
from keri.app import habbing

from . import __version__
from . import kli
from . import publish
from .anchor_doc import build_publisher_anchor
from .appcast import build_appcast
from .s3_client import S3
from .witnesses import default_witness_pool
from locksmith.release.deploy import load_deploy_config


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
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_ARTIFACT_PREFIX = "Locksmith"


def _artifact_url(cdn: str, version: str, prefix: str, ext: str) -> str:
    """Return the CDN URL for a release artifact with the given brand prefix."""
    return f"{cdn.rstrip('/')}/releases/{version}/{prefix}-{version}.{ext}"


def _publisher_anchor_path() -> Path:
    bundled = _bundled_publisher_anchor_path()
    if bundled is not None:
        return bundled
    # Not yet present — resolve the canonical gitignored location from this file.
    for parent in Path(__file__).resolve().parents:
        cand = parent / "src" / "locksmith" / "release"
        if cand.is_dir():
            return cand / "publisher_anchor.json"
    raise click.UsageError("could not locate src/locksmith/release/ — run from the repo")


def _read_publisher_aid(*, name: str, base: str, bran: str) -> str:
    """Open the keystore read-only and return the publisher hab prefix (the AID)."""
    hby = habbing.Habery(name=name, base=base, bran=bran)
    try:
        hab = hby.habByName("publisher")
        if hab is None:
            raise click.ClickException(f"no 'publisher' alias in keystore {name}")
        return hab.pre
    finally:
        hby.close()


def _bran(bran_env: str) -> str:
    try:
        return os.environ[bran_env]
    except KeyError:
        raise click.UsageError(f"bran env var {bran_env} is not set")


# ---------------------------------------------------------------------------
# Operator commands
# ---------------------------------------------------------------------------


@cli.command("incept")
@click.option("--name", required=True, help="keystore name")
@click.option("--base", required=True, help="keystore base dir")
@click.option("--alias", default="publisher", show_default=True)
@click.option("--bran-env", default="LOCKSMITH_PUBLISHER_BRAN", show_default=True,
              help="env var holding the keystore bran (never pass the bran as an arg)")
@click.option("--salt-env", default="LOCKSMITH_PUBLISHER_SALT", show_default=True,
              help="env var holding the deterministic qb64 salt (optional). "
                   "When set, the AID is reproducible from (salt + bran). "
                   "The salt is a secret — read from env, never passed as a CLI arg. "
                   "When unset or empty, a random salt is used (default).")
@click.option("--toad", default=3, show_default=True, type=int)
def incept_cmd(name, base, alias, bran_env, salt_env, toad):
    """Mint the publisher AID: init keystore, resolve witness OOBIs, incept (pre-rotation)."""
    bran = _bran(bran_env)
    salt = os.environ.get(salt_env) or None  # empty string → None (random)
    pool = default_witness_pool()
    kli.kli_init(name=name, base=base, bran=bran, salt=salt)
    for w in pool:
        kli.kli_resolve_oobi(name=name, base=base, bran=bran, oobi=w.oobi)
    out = kli.kli_incept(name=name, alias=alias, bran=bran, base=base,
                         wits=[w.aid for w in pool], toad=toad)
    click.echo(out)


@cli.command("gen-anchor")
@click.option("--name", required=True)
@click.option("--base", required=True)
@click.option("--bran-env", default="LOCKSMITH_PUBLISHER_BRAN", show_default=True)
@click.option("--toad", default=3, show_default=True, type=int)
@click.option("--force", is_flag=True, help="overwrite an existing publisher_anchor.json")
def gen_anchor_cmd(name, base, bran_env, toad, force):
    """Write src/locksmith/release/publisher_anchor.json from the minted keystore."""
    path = _publisher_anchor_path()
    if path.exists() and not force:
        raise click.ClickException(f"{path} already exists; pass --force to overwrite")
    aid = _read_publisher_aid(name=name, base=base, bran=_bran(bran_env))
    doc = build_publisher_anchor(
        publisher_aid=aid,
        witness_oobis=[w.oobi for w in default_witness_pool()],
        toad=toad,
    )
    path.write_text(json.dumps(doc, indent=2) + "\n")
    click.echo(f"wrote {path} (publisher_aid={aid})")


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
@click.option("--bucket", default=None,
              help="S3 bucket where releases/<version>/release-anchor-*.cesr lives "
                   "and appcast/v1/*.json will be written. Defaults to "
                   "deploy_config.json's `s3_bucket`.")
@click.option("--publisher-aid", "publisher_aid", default=None,
              help="Publisher AID for the appcast `publisher_aid` field. "
                   "Defaults to the value in src/locksmith/release/publisher_anchor.json.")
@click.option("--publisher-kel-url", "publisher_kel_url", default=None,
              help="URL of the publisher's KEL stream the verifier replays. "
                   "Defaults to deploy_config.json's `publisher_kel_url`.")
@click.option("--channel", default="stable", show_default=True)
def appcast_cmd(bucket: str | None, publisher_aid: str | None,
                publisher_kel_url: str | None, channel: str) -> None:
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
    from locksmith.release import load_deploy_config

    from .appcast import GeneratorConfig, generate_and_upload_appcasts

    # Federation/CDN domains are no longer hardcoded here — pull unset options
    # from the (gitignored) deploy_config (committed example uses example.com).
    deploy_cfg = load_deploy_config()
    if bucket is None:
        bucket = deploy_cfg["s3_bucket"]
    if publisher_kel_url is None:
        publisher_kel_url = deploy_cfg["publisher_kel_url"]
    releases_cdn_base = deploy_cfg["releases_cdn_base"]

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
            releases_cdn_base=releases_cdn_base,
            channel=channel,
        ),
    )
    click.echo(f"published s3://{bucket}/appcast/v1/macos.json")
    click.echo(f"published s3://{bucket}/appcast/v1/windows.json")


@cli.command("anchor")
@click.option("--name", required=True)
@click.option("--base", required=True)
@click.option("--alias", default="publisher", show_default=True)
@click.option("--bran-env", default="LOCKSMITH_PUBLISHER_BRAN", show_default=True)
@click.option("--version", required=True)
@click.option("--macos", "macos_path", required=True,
              type=click.Path(exists=True, path_type=Path))
@click.option("--windows", "windows_path", required=True,
              type=click.Path(exists=True, path_type=Path))
@click.option("--out-dir", default="out", show_default=True)
def anchor_cmd(name, base, alias, bran_env, version, macos_path, windows_path, out_dir):
    """Sign + witness the release seal over the (served) artifacts; export the KEL."""
    info = publish.anchor_release(
        name=name, alias=alias, bran=_bran(bran_env), base=base, version=version,
        artifacts=[("macos", macos_path), ("windows", windows_path)], out_dir=out_dir)
    click.echo(json.dumps(info, indent=2))


@cli.command("publish")
@click.option("--name", required=True)
@click.option("--base", required=True)
@click.option("--bran-env", default="LOCKSMITH_PUBLISHER_BRAN", show_default=True)
@click.option("--version", required=True)
@click.option("--anchor-said", required=True)
@click.option("--macos-sha256", required=True)
@click.option("--windows-sha256", required=True)
@click.option("--out-dir", default="out", show_default=True)
def publish_cmd(name, base, bran_env, version, anchor_said,
                macos_sha256, windows_sha256, out_dir):
    """Upload KEL + anchor + per-platform appcasts to S3 from deploy_config."""
    cfg = load_deploy_config()
    bucket = cfg["s3_bucket"]
    cdn = cfg["releases_cdn_base"].rstrip("/")
    kel_url = cfg["publisher_kel_url"]
    artifact_prefix = cfg.get("artifact_prefix", _DEFAULT_ARTIFACT_PREFIX)
    aid = _read_publisher_aid(name=name, base=base, bran=_bran(bran_env))

    out = Path(out_dir)
    kel = (out / f"{aid}-kel.cesr").read_bytes()
    anchor_bytes = (out / f"{anchor_said}.cesr").read_bytes()
    anchor_url = f"{cdn}/publisher/v1/anchors/{anchor_said}.cesr"

    def _appcast(platform, sha, ext):
        rel = {"version": version, "platform": platform, "anchor_said": anchor_said,
               "anchor_url": anchor_url, "artifact_sha256": sha,
               "artifact_url": _artifact_url(cdn, version, artifact_prefix, ext)}
        return build_appcast(publisher_aid=aid, publisher_kel_url=kel_url,
                             releases=[rel], current_version=version).encode()

    s3 = S3.default()
    s3.upload_release(bucket=bucket, kel=kel, anchors={anchor_said: anchor_bytes},
                      appcast=_appcast("macos", macos_sha256, "dmg"),
                      appcast_key="appcast/v1/macos.json")
    s3.put_object(bucket=bucket, key="appcast/v1/windows.json",
                  data=_appcast("windows", windows_sha256, "msi"),
                  content_type="application/json")
    click.echo(f"published v{version}: publisher/v1/kel.cesr + anchors/{anchor_said}.cesr "
               f"+ appcast/v1/{{macos,windows}}.json")


if __name__ == "__main__":
    cli()
