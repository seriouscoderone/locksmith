"""Main update-verification entry point per spec §7.

Given (artifact, appcast JSON, platform, embedded trust anchor), do:

1. Parse appcast (``appcast.parse_appcast``).
2. Confirm appcast's ``publisher_aid`` matches the embedded anchor.
3. Select the release for the current platform.
4. Fetch the publisher KEL from ``appcast.publisher_kel_url``.
5. Replay the KEL (``kel_replay.replay_kel``) from the embedded sn forward.
6. Confirm the appcast's anchor SAID exists in the KEL and is at the tip;
   reject stale/downgrade cases.
7. Fetch the anchor event; confirm its SAID matches.
8. Extract the release seal; find the artifact entry for the current
   platform; compare its SHA256 against a fresh hash of ``artifact_path``.
9. Cross-check appcast.sha256 against seal.sha256 (downgrade defense).

Returns ``VerificationResult`` on success; raises an ``UpdateError`` subclass
on any failure. No UI / logging side-effects.
"""
from __future__ import annotations

import hashlib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from keri.core import serdering

from locksmith.update.appcast import (
    Appcast,
    Release,
    parse_appcast,
    select_latest_for_platform,
)
from locksmith.update.errors import (
    DowngradeError,
    HashMismatchError,
    NetworkError,
    SchemaError,
    SignatureError,
    StaleAppcastError,
)
from locksmith.update.kel_replay import (
    KelState,
    extract_release_seal,
    replay_kel,
)

_FETCH_TIMEOUT_SEC = 30


def ssl_context() -> ssl.SSLContext:
    """SSL context that trusts certifi's CA bundle.

    A frozen PyInstaller app ships its own OpenSSL whose baked-in default CA
    paths point at the BUILD machine (the GitHub runner) — absent on the user's
    machine, so the default context raises ``CERTIFICATE_VERIFY_FAILED: unable
    to get local issuer certificate`` for every HTTPS fetch in the verify path.
    ``certifi.where()`` resolves to the cacert.pem PyInstaller bundles, so use it
    explicitly. Falls back to the system default when certifi is unavailable
    (e.g. a source checkout whose OpenSSL CA paths are valid).
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - certifi missing → system default
        return ssl.create_default_context()


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    version: str
    platform: str
    publisher_aid: str
    anchor_said: str
    artifact_sha256: str
    artifact_size: int
    witness_receipts: int
    kel_tip_sn: int


def _fetch_url(url: str) -> bytes:
    """Tiny wrapper around urllib so tests can monkeypatch.

    Raises ``NetworkError`` on connection / timeout / DNS failures.
    """
    try:
        with urllib.request.urlopen(
            url, timeout=_FETCH_TIMEOUT_SEC, context=ssl_context()
        ) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError, TimeoutError) as ex:
        raise NetworkError(
            f"fetch failed: {url}: {ex}",
            log_fields={"url": url, "reason": str(ex)},
        ) from ex


def _sha256_file(path: Path) -> tuple[str, int]:
    """Stream-hash ``path``; return (hexdigest, size)."""
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def verify_artifact(
    *,
    artifact_path: Path,
    appcast_raw: str | bytes,
    platform: str,
    embedded_publisher_aid: str,
    embedded_kel_sn: int,
    embedded_kel_said: str | None,
    toad: int,
) -> VerificationResult:
    """Run the full update-verification pipeline for one artifact.

    Raises ``UpdateError`` subclass on any failure; returns
    ``VerificationResult(ok=True, ...)`` on success.
    """
    # 1. Parse appcast.
    ac: Appcast = parse_appcast(appcast_raw)

    # 2. Appcast publisher_aid must match embedded anchor.
    if ac.publisher_aid != embedded_publisher_aid:
        raise SignatureError(
            f"appcast publisher_aid {ac.publisher_aid} does not match "
            f"embedded {embedded_publisher_aid}",
            log_fields={
                "appcast_aid": ac.publisher_aid,
                "embedded_aid": embedded_publisher_aid,
            },
        )

    # 3. Select platform release.
    rel: Release = select_latest_for_platform(ac, platform)

    # 4. Fetch & replay KEL.
    kel_stream = _fetch_url(ac.publisher_kel_url)
    state: KelState = replay_kel(
        kel_stream=kel_stream,
        publisher_aid=embedded_publisher_aid,
        embedded_sn=embedded_kel_sn,
        embedded_said=embedded_kel_said,
        toad=toad,
    )

    # 5. Stale-appcast / downgrade defense — find the anchor event in KEL.
    matching = [e for e in state.events if e.said == rel.anchor_said]
    if not matching:
        raise StaleAppcastError(
            f"appcast anchor_said {rel.anchor_said} not present in KEL",
            log_fields={
                "anchor_said": rel.anchor_said,
                "current_version": ac.current_version,
                "kel_tip_sn": state.current_sn,
            },
        )
    anchor_event = matching[0]
    if anchor_event.sn < state.current_sn:
        # Older anchor offered as current. If the seal's version mismatches
        # the appcast's claimed version, it's a downgrade; else it's stale.
        try:
            seal = extract_release_seal(state, anchor_said=rel.anchor_said)
        except SchemaError:
            raise StaleAppcastError(
                f"appcast points at sn={anchor_event.sn} but KEL tip is "
                f"sn={state.current_sn}",
                log_fields={
                    "anchor_sn": anchor_event.sn,
                    "kel_tip_sn": state.current_sn,
                },
            )
        if seal["release"]["v"] != rel.version:
            raise DowngradeError(
                f"appcast claims {rel.version} but seal says "
                f"{seal['release']['v']}",
                log_fields={
                    "appcast_version": rel.version,
                    "seal_version": seal["release"]["v"],
                },
            )
        raise StaleAppcastError(
            f"appcast points at sn={anchor_event.sn} but KEL tip is "
            f"sn={state.current_sn}",
            log_fields={
                "anchor_sn": anchor_event.sn,
                "kel_tip_sn": state.current_sn,
            },
        )

    # 6. Fetch the anchor event and confirm its SAID matches.
    anchor_raw = _fetch_url(rel.anchor_url)
    try:
        fetched_serder = serdering.SerderKERI(raw=bytearray(anchor_raw))
    except Exception as ex:
        raise SchemaError(
            f"anchor event not valid CESR/JSON: {ex}",
            log_fields={"anchor_url": rel.anchor_url},
        ) from ex
    if fetched_serder.said != rel.anchor_said:
        raise SignatureError(
            f"anchor SAID mismatch: appcast={rel.anchor_said} "
            f"fetched={fetched_serder.said}",
            log_fields={
                "appcast_said": rel.anchor_said,
                "fetched_said": fetched_serder.said,
            },
        )

    # 7. Extract the seal from KEL replay (authoritative — not from fetched bytes).
    seal = extract_release_seal(state, anchor_said=rel.anchor_said)
    if seal["release"]["v"] != rel.version:
        raise DowngradeError(
            f"appcast version {rel.version} mismatches seal "
            f"version {seal['release']['v']}",
            log_fields={
                "appcast_version": rel.version,
                "seal_version": seal["release"]["v"],
            },
        )

    # 8. Find the artifact entry for this platform in the seal.
    artifact_entry = None
    for a in seal["release"].get("artifacts", []):
        if a.get("platform") == platform:
            artifact_entry = a
            break
    if artifact_entry is None:
        raise SchemaError(
            f"seal has no artifact for platform={platform}",
            log_fields={"platform": platform, "version": rel.version},
        )

    # 9. Hash the file, compare to seal AND to appcast.
    actual_sha, actual_size = _sha256_file(artifact_path)
    if actual_sha != artifact_entry["sha256"]:
        raise HashMismatchError(
            f"artifact sha256 {actual_sha} does not match seal "
            f"{artifact_entry['sha256']}",
            log_fields={
                "expected_sha256": artifact_entry["sha256"],
                "actual_sha256": actual_sha,
                "artifact_path": str(artifact_path),
            },
        )
    if rel.artifact_sha256 != artifact_entry["sha256"]:
        # Appcast disagrees with KEL — appcast is tampered.
        raise DowngradeError(
            f"appcast sha256 {rel.artifact_sha256} disagrees with "
            f"seal sha256 {artifact_entry['sha256']}",
            log_fields={
                "appcast_sha256": rel.artifact_sha256,
                "seal_sha256": artifact_entry["sha256"],
            },
        )

    return VerificationResult(
        ok=True,
        version=rel.version,
        platform=platform,
        publisher_aid=embedded_publisher_aid,
        anchor_said=rel.anchor_said,
        artifact_sha256=actual_sha,
        artifact_size=actual_size,
        witness_receipts=anchor_event.receipts,
        kel_tip_sn=state.current_sn,
    )
