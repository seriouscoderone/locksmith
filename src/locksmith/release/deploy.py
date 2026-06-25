"""Deployment config loader: federation/CDN domains in ONE gitignored place.

The real personal domains backing the KERI.host federation and release CDN
(witness hosts + AIDs, ``releases_cdn_base`` / ``s3_bucket`` /
``publisher_kel_url`` / per-platform ``appcast_urls``) are NOT committed. They
live in a single gitignored ``src/locksmith/release/deploy_config.json``; the
repo commits only ``deploy_config.example.json`` (``example.com`` placeholders).

This mirrors the ``publisher_anchor.json`` de-commit, with ONE deliberate
difference: the example template IS an acceptable dev/test fallback here.
Unlike the trust anchor (where verifying against ``example.com`` witnesses would
be meaningless), the example URLs are harmless — fetching them just fails or
404s, and the real verify gate stays dark until a real publisher anchor is
present. So the loader can always return SOMETHING, which keeps unit/integration
tests green on a clean checkout.

Resolution order:

1. ``$LOCKSMITH_DEPLOY_CONFIG`` — a file path (build/CI injection). If the env
   var is set but the file is missing, raise ``FileNotFoundError`` (loud
   misconfiguration) rather than silently falling back.
2. The packaged (gitignored) ``locksmith/release/deploy_config.json``.
3. The committed ``locksmith/release/deploy_config.example.json`` template.

Schema (see ``deploy_config.example.json``)::

    {
      "releases_cdn_base": "https://releases.example.com",
      "s3_bucket": "releases.example.com",
      "publisher_kel_url": "https://releases.example.com/publisher/v1/kel.cesr",
      "appcast_urls": {
        "macos":   "https://releases.example.com/appcast/v1/macos.json",
        "windows": "https://releases.example.com/appcast/v1/windows.json"
      },
      "witnesses": [
        {"alias": "wan", "host": "witness.example.com", "aid": "B..."},
        ...
      ]
    }

Each ``witnesses`` entry carries the exact fields the publisher's witness
directory (``locksmith_publisher.witnesses``) needs: ``alias``, ``host``,
``aid``. The OOBI is derived as ``https://<host>/oobi/<aid>/witness`` per the
KERI spec convention.
"""
from __future__ import annotations

import json
import os
import sys
from importlib import resources
from pathlib import Path

#: Env var pointing at a build-injected deploy-config JSON file. Takes
#: precedence over the packaged config so CI can inject the real (gitignored)
#: domains without committing them. See ``deploy_config.example.json``.
DEPLOY_CONFIG_ENV_VAR = "LOCKSMITH_DEPLOY_CONFIG"

_REAL_FILENAME = "deploy_config.json"
_EXAMPLE_FILENAME = "deploy_config.example.json"


def frozen_release_file(filename: str) -> Path | None:
    """Locate a bundled ``locksmith/release/<filename>`` on the filesystem when
    running frozen (PyInstaller).

    ``importlib.resources`` can FAIL to find data files whose package code lives
    in PyInstaller's embedded PYZ archive (the package has no on-disk ``__init__``
    for the resource reader to anchor to). PyInstaller still lays the data down
    on the filesystem under ``sys._MEIPASS`` (and, in a macOS ``.app``, under
    ``Contents/Frameworks`` and ``Contents/Resources``). Resolve from there.

    Returns ``None`` when not frozen or the file is absent — callers then fall
    back to the ``importlib.resources`` lookup (correct for source checkouts).
    """
    if not getattr(sys, "frozen", False):
        return None
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    # macOS .app: executable at Contents/MacOS/, data under Frameworks/Resources.
    contents = Path(sys.executable).resolve().parent.parent
    roots.append(contents / "Frameworks")
    roots.append(contents / "Resources")
    for root in roots:
        candidate = root / "locksmith" / "release" / filename
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _resource_path(filename: str) -> Path | None:
    """Return a filesystem path to ``filename`` packaged under this module.

    Works for a normal source checkout, a zipped resource, AND a PyInstaller
    frozen app (via :func:`frozen_release_file`). Returns ``None`` when absent.
    """
    frozen = frozen_release_file(filename)
    if frozen is not None:
        return frozen
    try:
        candidate = resources.files("locksmith.release").joinpath(filename)
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    try:
        if candidate.is_file():
            return Path(str(candidate))
    except (OSError, FileNotFoundError):
        return None
    return None


def _packaged_deploy_config_path() -> Path | None:
    """Path to the packaged (gitignored) real ``deploy_config.json``, if present."""
    return _resource_path(_REAL_FILENAME)


def _example_deploy_config_path() -> Path | None:
    """Path to the committed ``deploy_config.example.json`` template, if present."""
    return _resource_path(_EXAMPLE_FILENAME)


def load_deploy_config() -> dict:
    """Resolve the deployment config (env-injection first, example last).

    See the module docstring for the full resolution order. Raises
    ``FileNotFoundError`` only when ``$LOCKSMITH_DEPLOY_CONFIG`` is set to a
    path that does not exist, or (defensively) when not even the committed
    example template can be located.
    """
    env_path = os.environ.get(DEPLOY_CONFIG_ENV_VAR)
    if env_path:
        injected = Path(env_path)
        if injected.is_file():
            return json.loads(injected.read_text())
        raise FileNotFoundError(
            f"{DEPLOY_CONFIG_ENV_VAR} is set to {env_path!r} but no file exists "
            f"there (deploy_config injection misconfigured)"
        )

    packaged = _packaged_deploy_config_path()
    if packaged is not None:
        return json.loads(packaged.read_text())

    example = _example_deploy_config_path()
    if example is not None:
        return json.loads(example.read_text())

    raise FileNotFoundError(
        "no deploy_config found: set $"
        f"{DEPLOY_CONFIG_ENV_VAR} to a build-injected config file, place a real "
        "deploy_config.json in locksmith/release/, or ship the committed "
        "deploy_config.example.json template"
    )
