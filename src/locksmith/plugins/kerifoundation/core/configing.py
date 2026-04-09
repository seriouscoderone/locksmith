# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.core.configing module

Plugin-local environment helpers for KERI Foundation witness services.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from keri import help

logger = help.ogler.getLogger(__name__)


@dataclass(frozen=True)
class WitnessServerConfig:
    """Provisionable witness server endpoints for one environment."""

    witness_url: str
    boot_url: str
    region: str = ""
    label: str = ""


def load_witness_servers(app: Any) -> list[WitnessServerConfig]:
    """Load provisionable witness servers for the app's current environment.

    Prefers numbered environment variables starting from ``_1``::

        KF_PROD_WITNESS_URL_1, KF_PROD_BOOT_URL_1, KF_PROD_REGION_1, KF_PROD_LABEL_1
        KF_PROD_WITNESS_URL_2, KF_PROD_BOOT_URL_2, ...

    Numbering must be contiguous. If both ``WITNESS_URL_N`` and
    ``BOOT_URL_N`` are missing the scan stops. If only one of the pair
    is present a warning is logged and the index is skipped (scan
    continues). ``REGION_N`` and ``LABEL_N`` are optional.

    If no numbered entries are present at all, the loader falls back to
    the legacy unsuffixed pair for backward compatibility and logs a
    deprecation warning.
    """
    environment = getattr(getattr(app, "config", None), "environment", None)
    if environment is None:
        return []

    env_name = getattr(environment, "value", str(environment)).lower()
    prefix = "KF_DEV" if env_name == "development" else "KF_PROD"

    servers: list[WitnessServerConfig] = []
    numbered_keys_seen = False
    index = 1
    while True:
        witness_url = os.environ.get(f"{prefix}_WITNESS_URL_{index}", "").strip()
        boot_url = os.environ.get(f"{prefix}_BOOT_URL_{index}", "").strip()

        if not witness_url and not boot_url:
            break  # End of contiguous range

        numbered_keys_seen = True

        if not witness_url or not boot_url:
            present = "WITNESS_URL" if witness_url else "BOOT_URL"
            missing = "BOOT_URL" if witness_url else "WITNESS_URL"
            logger.warning(
                f"{prefix}_{present}_{index} is set but {prefix}_{missing}_{index} "
                f"is missing — skipping server index {index}"
            )
            index += 1
            continue

        region = os.environ.get(f"{prefix}_REGION_{index}", "").strip()
        label = os.environ.get(f"{prefix}_LABEL_{index}", "").strip()

        servers.append(
            WitnessServerConfig(
                witness_url=witness_url,
                boot_url=boot_url,
                region=region,
                label=label,
            )
        )
        index += 1

    if servers or numbered_keys_seen:
        return servers

    legacy_witness_url = os.environ.get(f"{prefix}_WITNESS_URL", "").strip()
    legacy_boot_url = os.environ.get(f"{prefix}_BOOT_URL", "").strip()
    if not legacy_witness_url and not legacy_boot_url:
        return []

    if not legacy_witness_url or not legacy_boot_url:
        logger.warning(
            f"Legacy witness config for {prefix} is incomplete; both "
            f"{prefix}_WITNESS_URL and {prefix}_BOOT_URL are required"
        )
        return []

    logger.warning(
        f"Using deprecated legacy witness config {prefix}_WITNESS_URL / "
        f"{prefix}_BOOT_URL; rename them to {prefix}_WITNESS_URL_1 / "
        f"{prefix}_BOOT_URL_1"
    )
    return [
        WitnessServerConfig(
            witness_url=legacy_witness_url,
            boot_url=legacy_boot_url,
        )
    ]
