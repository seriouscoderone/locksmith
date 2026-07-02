"""Appcast generator — operator-side, invoked after each ``anchor`` succeeds.

Reads every ``releases/X.Y.Z/release-anchor-X.Y.Z.cesr`` from S3, extracts the
release seal from each, emits per-platform appcasts under ``appcast/v1/``, and
archives prior appcasts under ``appcast/archive/{timestamp}/`` so the history
is recoverable.

Per Phase 4 deviation #2, this also runs on the operator's laptop (not CI) —
the same publisher signing flow that calls ``anchor`` can be followed by a
``locksmith-publisher publish-appcasts`` invocation to refresh the appcast.
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from keri.core import serdering


@dataclass(frozen=True)
class GeneratorConfig:
    bucket: str
    publisher_aid: str
    publisher_kel_url: str
    #: Base URL of the release CDN, used to build per-release ``artifact_url`` /
    #: ``anchor_url`` (no trailing slash). The real value lives in the gitignored
    #: deploy_config; callers that don't pass one fall back to that config.
    releases_cdn_base: str | None = None
    schema_version: int = 1
    channel: str = "stable"
    #: Brand-specific S3/CDN key prefix (``<prefix>/<version>/…``). Defaults to
    #: the locksmith ``releases`` prefix so existing callers are byte-identical.
    release_prefix: str = "releases"
    #: Base URL of the brand website whose ``/releases/<v>`` page the appcast's
    #: ``release_notes_url`` points at (no trailing slash).
    release_notes_base: str = "https://locksmith.app"
    #: Human-readable brand name for the RSS feed ``<title>``; falls back to the
    #: publisher AID when unset (the pre-brand behavior).
    brand_title: str | None = None

    def cdn_base(self) -> str:
        """Resolve the release CDN base, deferring to deploy_config if unset."""
        if self.releases_cdn_base:
            return self.releases_cdn_base.rstrip("/")
        from locksmith.release import load_deploy_config
        return load_deploy_config()["releases_cdn_base"].rstrip("/")


def _parse_anchor(raw: bytes) -> dict[str, Any]:
    """Parse a CESR-encoded release anchor; return ``{said, seal}``."""
    serder = serdering.SerderKERI(raw=bytearray(raw))
    seals = serder.ked.get("a", [])
    if not seals:
        raise ValueError(
            f"release anchor {serder.said} has no seals in `a` field"
        )
    return {"said": serder.said, "seal": seals[0]}


def _semver_key(v: str) -> tuple[int, int, int]:
    try:
        parts = v.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        # Push unparseable versions to the end so they don't poison the sort.
        return (10**9, 10**9, 10**9)


def build_appcast(
    *,
    publisher_aid: str,
    publisher_kel_url: str,
    releases: list[dict[str, Any]],
    channel: str = "stable",
    schema_version: int = 1,
    current_version: str | None = None,
) -> str:
    """Build an appcast JSON string the verifier's ``parse_appcast`` consumes.

    Mirrors the schema in ``locksmith.update.appcast``: the top-level object
    carries ``schema_version``/``channel``/``publisher_aid``/
    ``publisher_kel_url``/``current_version``/``releases``, and each release
    carries the full ``REQUIRED_REL`` key set. Each entry in ``releases`` only
    needs the load-bearing fields the caller knows (``version``, ``platform``,
    ``anchor_said``, ``anchor_url``, ``artifact_sha256``, ``artifact_url``);
    the remaining required keys are filled from per-release overrides or
    schema-valid defaults so ``parse_appcast`` accepts the payload.

    ``current_version`` defaults to the highest semver among ``releases`` so
    ``select_latest_for_platform`` resolves the newest release per platform.
    """
    if not releases:
        raise ValueError("build_appcast requires at least one release")

    built: list[dict[str, Any]] = []
    for r in releases:
        built.append({
            "version": r["version"],
            "released_at": r.get("released_at", ""),
            "platform": r["platform"],
            "minimum_system_version": r.get("minimum_system_version", ""),
            "artifact_url": r["artifact_url"],
            "artifact_sha256": r["artifact_sha256"],
            "artifact_size": int(r.get("artifact_size", 0)),
            "anchor_url": r["anchor_url"],
            "anchor_said": r["anchor_said"],
            "release_notes_url": r.get("release_notes_url", ""),
            "is_major": bool(r.get("is_major", False)),
            "is_critical": bool(r.get("is_critical", False)),
        })

    if current_version is None:
        current_version = max((b["version"] for b in built), key=_semver_key)

    appcast = {
        "schema_version": schema_version,
        "channel": channel,
        "publisher_aid": publisher_aid,
        "publisher_kel_url": publisher_kel_url,
        "current_version": current_version,
        "releases": built,
    }
    return json.dumps(appcast, indent=2)


def build_appcast_xml(
    *,
    title: str,
    releases: list[dict[str, Any]],
    channel: str = "stable",
) -> str:
    """Build an RSS 2.0 appcast Sparkle/WinSparkle can parse.

    Native signature verification stays OFF (no ``sparkle:edSignature``) —
    trust is the OS code-signature on the wire plus the KERI gate at install.
    Items are emitted newest-first by semver.
    """
    if not releases:
        raise ValueError("build_appcast_xml requires at least one release")
    ordered = sorted(releases, key=lambda r: _semver_key(r["version"]), reverse=True)
    items: list[str] = []
    for r in ordered:
        v = r["version"]
        pubdate = f"    <pubDate>{escape(r['released_at'])}</pubDate>\n" if r.get("released_at") else ""
        items.append(
            f"  <item>\n"
            f"    <title>{escape(title)} {escape(v)}</title>\n"
            f"{pubdate}"
            f"    <enclosure url={quoteattr(r['artifact_url'])} "
            f"sparkle:version={quoteattr(v)} sparkle:shortVersionString={quoteattr(v)} "
            f"length={quoteattr(str(int(r['artifact_size'])))} type={quoteattr('application/octet-stream')}/>\n"
            f"  </item>"
        )
    items_xml = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0" '
        'xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">\n'
        "  <channel>\n"
        f"    <title>{escape(title)} ({escape(channel)})</title>\n"
        f"{items_xml}\n"
        "  </channel>\n"
        "</rss>\n"
    )


def generate_and_upload_appcasts(*, s3, config: GeneratorConfig) -> None:
    """Regenerate per-platform appcasts from S3 and upload them.

    ``s3`` must expose ``list_release_versions(bucket=...) -> list[str]``,
    ``get_object(Bucket=, Key=) -> bytes`` (or ``-> object with ['Body'].read()``),
    and ``put_object(Bucket=, Key=, Body=, ContentType=)``.
    """
    all_versions = sorted(
        s3.list_release_versions(bucket=config.bucket, prefix=config.release_prefix),
        key=_semver_key,
    )
    if not all_versions:
        return

    # Only include versions that actually have an anchor file. Test
    # releases that pre-date Phase 4 (or were never anchored) have
    # artifact uploads but no release-anchor-<v>.cesr — skip those
    # so a missing key here doesn't poison the appcast.
    anchors_by_version: dict[str, dict[str, Any]] = {}
    versions: list[str] = []
    for v in all_versions:
        try:
            raw_or_resp = s3.get_object(
                Bucket=config.bucket,
                Key=f"{config.release_prefix}/{v}/release-anchor-{v}.cesr",
            )
        except Exception:  # noqa: BLE001 — NoSuchKey, ClientError, etc.
            # Un-anchored — leave out of the appcast. Verifier wouldn't
            # accept it anyway since no ixn / receipts exist.
            continue
        # Tolerate both raw bytes and a boto3-style response dict.
        if isinstance(raw_or_resp, (bytes, bytearray)):
            raw = bytes(raw_or_resp)
        elif isinstance(raw_or_resp, dict) and "Body" in raw_or_resp:
            raw = raw_or_resp["Body"].read()
        else:
            raise ValueError(
                f"unexpected S3 get_object return for {v}: {type(raw_or_resp).__name__}"
            )
        anchors_by_version[v] = _parse_anchor(raw)
        versions.append(v)

    if not versions:
        return

    current_version = versions[-1]
    timestamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cdn_base = config.cdn_base()

    for platform, ext in [("macos", "dmg"), ("windows", "msi")]:
        releases: list[dict[str, Any]] = []
        for v in versions:
            parsed = anchors_by_version[v]
            seal = parsed["seal"]["release"]
            artifact = next(
                a for a in seal["artifacts"] if a["platform"] == platform
            )
            releases.append({
                "version": v,
                "released_at": seal["released_at"],
                "platform": platform,
                "minimum_system_version":
                    seal["minimum_system_versions"][platform],
                "artifact_url":
                    f"{cdn_base}/{config.release_prefix}/{v}/{artifact['filename']}",
                "artifact_sha256": artifact["sha256"],
                "artifact_size": artifact["size"],
                "anchor_url":
                    f"{cdn_base}/{config.release_prefix}/{v}/release-anchor-{v}.cesr",
                "anchor_said": parsed["said"],
                "release_notes_url":
                    f"{config.release_notes_base}/releases/{v}",
                "is_major": seal.get("is_major", False),
                "is_critical": seal.get("is_critical", False),
            })

        appcast = {
            "schema_version": config.schema_version,
            "channel": config.channel,
            "publisher_aid": config.publisher_aid,
            "publisher_kel_url": config.publisher_kel_url,
            "current_version": current_version,
            "releases": releases,
        }
        body = json.dumps(appcast, indent=2).encode()
        live_key = f"appcast/v1/{platform}.json"
        archive_key = f"appcast/archive/{timestamp}/{platform}.json"
        s3.put_object(
            Bucket=config.bucket,
            Key=live_key,
            Body=body,
            ContentType="application/json",
        )
        s3.put_object(
            Bucket=config.bucket,
            Key=archive_key,
            Body=body,
            ContentType="application/json",
        )
        xml_body = build_appcast_xml(
            title=config.brand_title or config.publisher_aid,
            releases=[{"version": r["version"], "artifact_url": r["artifact_url"],
                       "artifact_size": r["artifact_size"],
                       "released_at": r["released_at"]} for r in releases],
        ).encode()
        s3.put_object(
            Bucket=config.bucket,
            Key=f"appcast/v1/{platform}.xml",
            Body=xml_body,
            ContentType="application/xml",
        )
        s3.put_object(
            Bucket=config.bucket,
            Key=f"appcast/archive/{timestamp}/{platform}.xml",
            Body=xml_body,
            ContentType="application/xml",
        )
