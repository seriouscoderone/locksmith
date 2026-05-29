"""Helpers for querying the api.keri.host witness pool.

The api.keri.host service exposes a small JSON endpoint listing its current
witness AIDs and OOBI URLs. We query it at inception time to bake the witnesses
into the publisher AID's inception event.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import requests


class WitnessDiscoveryError(RuntimeError):
    """Raised when the witness pool cannot be queried or doesn't meet minimums."""


@dataclass(frozen=True)
class WitnessInfo:
    aid: str
    oobi: str


def discover_witness_pool(pool_url: str, *, minimum: int = 3, timeout: float = 10.0) -> List[WitnessInfo]:
    """Fetch the witness pool from `pool_url` and return WitnessInfo entries.

    Raises WitnessDiscoveryError if fewer than `minimum` witnesses are returned
    or on HTTP/parse error.
    """
    try:
        resp = requests.get(pool_url, timeout=timeout)
    except requests.RequestException as exc:
        raise WitnessDiscoveryError(f"failed to GET {pool_url}: {exc}") from exc
    if resp.status_code != 200:
        raise WitnessDiscoveryError(f"HTTP {resp.status_code} from {pool_url}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise WitnessDiscoveryError(f"response from {pool_url} is not JSON: {exc}") from exc
    raw = body.get("witnesses")
    if not isinstance(raw, list):
        raise WitnessDiscoveryError(f"response from {pool_url} missing 'witnesses' array")
    witnesses = [WitnessInfo(aid=entry["aid"], oobi=entry["oobi"]) for entry in raw]
    if len(witnesses) < minimum:
        raise WitnessDiscoveryError(
            f"witness pool returned {len(witnesses)} witnesses; need at least {minimum}"
        )
    return witnesses
