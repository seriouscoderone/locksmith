"""Standalone ``locksmith --verify-update <path>`` CLI.

Exit codes (per ``locksmith.update.errors.*.exit_code``):

* 0  — verified
* 10 — signature / schema / rotation / duplicity / staging
* 11 — hash mismatch
* 12 — witness threshold not met
* 13 — stale appcast / superseded / downgrade
* 14 — network failure

``--json`` emits a machine-readable payload to stdout instead of human text.

Per spec §9.2 and the project's "never offer to install anyway" rule, this
CLI never prints "install anyway" / "override" / "force" suggestions. A
verification failure means the binary is untrustworthy — full stop.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path

from locksmith.release import load_deploy_config
from locksmith.update.errors import NetworkError, UpdateError
from locksmith.update.verify import verify_artifact


def _appcast_url(platform: str) -> str:
    """Resolve the per-platform appcast URL from the deploy config.

    The release CDN domain is no longer hardcoded here: it lives in the
    gitignored ``deploy_config.json`` (committed ``deploy_config.example.json``
    template). See ``locksmith.release.deploy.load_deploy_config``.
    """
    urls = load_deploy_config()["appcast_urls"]
    return urls["macos"] if platform == "macos" else urls["windows"]

#: Env var pointing at a build-injected publisher anchor JSON file. Takes
#: precedence over the packaged anchor so CI can inject the real (gitignored)
#: trust root without committing it. See ``publisher_anchor.example.json``.
ANCHOR_ENV_VAR = "LOCKSMITH_PUBLISHER_ANCHOR"


def _packaged_publisher_anchor_path() -> Path | None:
    """Return the path to the packaged ``publisher_anchor.json`` if present.

    The real anchor is gitignored and injected at build time (PyInstaller
    bundles it into ``locksmith/release/``); the committed template lives
    alongside it as ``publisher_anchor.example.json``. Returns ``None`` when
    no real anchor has been placed (e.g. a clean checkout without injection).
    """
    try:
        candidate = resources.files("locksmith.release").joinpath(
            "publisher_anchor.json"
        )
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    # ``Traversable.is_file`` works for both filesystem and zipped resources.
    try:
        if candidate.is_file():
            return Path(str(candidate))
    except (OSError, FileNotFoundError):
        return None
    return None


def _load_publisher_anchor() -> dict:
    """Resolve the publisher trust anchor, build-injection source first.

    Resolution order (privacy rule: the real anchor is never committed):

    1. ``$LOCKSMITH_PUBLISHER_ANCHOR`` — a file path injected by the build/CI.
    2. The packaged (gitignored) ``locksmith/release/publisher_anchor.json``.
    3. Otherwise raise ``FileNotFoundError`` with a clear message.

    The committed ``publisher_anchor.example.json`` is a placeholder template
    and is intentionally NOT a fallback — verifying against ``example.com``
    witnesses would be meaningless.
    """
    env_path = os.environ.get(ANCHOR_ENV_VAR)
    if env_path:
        injected = Path(env_path)
        if injected.is_file():
            return json.loads(injected.read_text())
        # An env var that points nowhere is a build misconfiguration: fail
        # loudly rather than silently falling back to the packaged anchor.
        raise FileNotFoundError(
            f"{ANCHOR_ENV_VAR} is set to {env_path!r} but no file exists there "
            f"(publisher_anchor injection misconfigured)"
        )

    packaged = _packaged_publisher_anchor_path()
    if packaged is not None:
        return json.loads(packaged.read_text())

    raise FileNotFoundError(
        "no publisher_anchor.json found: set $"
        f"{ANCHOR_ENV_VAR} to a build-injected anchor file or place a real "
        "publisher_anchor.json in locksmith/release/ "
        "(publisher_anchor.example.json is a placeholder template, not a fallback)"
    )


def _load_anchor_and_appcast(
    platform: str,
) -> tuple[str, str, int, str | None, int, str]:
    """Return ``(appcast_raw, publisher_aid, sn, said, toad, platform)``.

    Reads the publisher trust anchor (build-injected first; see
    ``_load_publisher_anchor``) and fetches the live appcast for ``platform``.
    """
    anchor = _load_publisher_anchor()
    url = _appcast_url(platform)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            appcast_raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError) as ex:
        raise NetworkError(
            f"appcast fetch failed: {url}: {ex}",
            log_fields={"url": url, "reason": str(ex)},
        ) from ex
    # ``toad`` is informational here — real verifier uses the value embedded
    # in the publisher anchor file, defaulting to 3 (production federation
    # has 5 witnesses; toad=3 is a 3-of-5 majority).
    toad = int(anchor.get("toad", 3))
    return (
        appcast_raw,
        anchor["publisher_aid"],
        int(anchor.get("embedded_kel_sn", 0)),
        anchor.get("embedded_kel_hash"),
        toad,
        platform,
    )


def _detect_platform() -> str:
    import platform as _platform
    return "macos" if _platform.system() == "Darwin" else "windows"


def _emit(
    *,
    ok: bool,
    exit_code: int,
    payload: dict,
    json_mode: bool,
) -> None:
    if json_mode:
        print(json.dumps({**payload, "ok": ok, "exit_code": exit_code}))
        return
    if ok:
        print(
            f"verified: {payload['version']} on {payload['platform']} "
            f"(SAID {payload['anchor_said']})"
        )
    else:
        print(
            f"verification FAILED: {payload['error']}: {payload['reason']}",
            file=sys.stderr,
        )


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="locksmith")
    parser.add_argument(
        "--verify-update",
        dest="path",
        metavar="PATH",
        type=Path,
        required=True,
        help="Path to a downloaded Locksmith artifact",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON to stdout instead of human text",
    )
    parser.add_argument(
        "--platform",
        choices=("macos", "windows"),
        default=None,
        help="Override platform detection",
    )
    args = parser.parse_args(argv)

    platform = args.platform or _detect_platform()
    try:
        (appcast_raw, aid, sn, said, toad, _) = _load_anchor_and_appcast(platform)
        result = verify_artifact(
            artifact_path=args.path,
            appcast_raw=appcast_raw,
            platform=platform,
            embedded_publisher_aid=aid,
            embedded_kel_sn=sn,
            embedded_kel_said=said,
            toad=toad,
        )
    except UpdateError as ex:
        _emit(
            ok=False,
            exit_code=ex.exit_code,
            payload={
                "error": type(ex).__name__,
                "reason": ex.reason,
                "log_fields": ex.log_fields,
            },
            json_mode=args.json,
        )
        return ex.exit_code

    _emit(
        ok=True,
        exit_code=0,
        payload={
            "version": result.version,
            "platform": result.platform,
            "publisher_aid": result.publisher_aid,
            "anchor_said": result.anchor_said,
            "artifact_sha256": result.artifact_sha256,
            "witness_receipts": result.witness_receipts,
            "kel_tip_sn": result.kel_tip_sn,
        },
        json_mode=args.json,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
