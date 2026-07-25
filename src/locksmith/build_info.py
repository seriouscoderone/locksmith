"""Build-time constants baked into the Locksmith binary.

This file is REWRITTEN by ``packaging/build-macos.sh`` and the Windows
equivalent before PyInstaller runs. The dev-tree default values are correct
for unpacked-source runs; the release artifact always carries the real
pyproject version and the channel from the build environment.

Do not import this module before PyInstaller bundles the app if you want
the real release version — read it from pyproject.toml during dev.
"""
from __future__ import annotations

LOCKSMITH_VERSION: str = "0.0.0+dev"
"""Semver of this build. Build scripts overwrite this string in-place."""

LOCKSMITH_RELEASE_CHANNEL: str = "stable"
"""Release channel. Phase 2 supports 'stable' only (spec §3)."""

LOCKSMITH_GIT_COMMIT: str = "dev"
"""Short git commit this build was cut from. Build scripts overwrite it with
`git rev-parse --short HEAD`. Distinguishes THIS keri.host fork build from any
other same-version build."""

KERIPY_COMMIT: str = "dev"
"""Short commit of the pinned keri.host keripy fork this build bundles. Build
scripts overwrite it with the sha from the `keri @ …@<sha>` pin in pyproject.
keri's OWN __version__ must stay '2.0.0-dev6' (it gates DB open — see the keri
pin comment in pyproject), so the fork identity is carried here, not there:
displayed as `kerihost @ <KERIPY_COMMIT>` on top of the KERI 2.0 protocol gen."""
