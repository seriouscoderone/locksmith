# -*- encoding: utf-8 -*-
"""Resolve the active brand's identity for the publisher.

The publisher runs from the repo, so `packaging/brandlib.py` is present. We
shell out to the same `python -m brandlib id <field>` CLI the build scripts
use (single source of truth), rather than importing brandlib (keeps this
package decoupled from packaging/). Fail-loud: a failed resolve must never
silently fall back to the default `releases/` prefix for a non-locksmith brand.
"""
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "src" / "locksmith" / "release").is_dir():
            return parent
    raise RuntimeError(
        "could not locate repo root (src/locksmith/release/) — run from the repo"
    )


def _brandlib_id(field: str) -> str:
    res = subprocess.run(
        [sys.executable, "-m", "brandlib", "id", field],
        cwd=_repo_root() / "packaging",
        capture_output=True,
        text=True,
    )
    value = res.stdout.strip()
    if res.returncode != 0 or not value:
        raise RuntimeError(
            f"brandlib id {field!r} failed: rc={res.returncode} "
            f"stderr={res.stderr.strip()!r} — refusing to guess the brand prefix"
        )
    return value


def release_prefix() -> str:
    return _brandlib_id("release_prefix")


def brand_id() -> str:
    return _brandlib_id("id")


def appcast_prefix() -> str:
    return _brandlib_id("appcast_prefix")


def artifact_prefix() -> str:
    return _brandlib_id("artifact_prefix")


def website() -> str:
    return _brandlib_id("website")
