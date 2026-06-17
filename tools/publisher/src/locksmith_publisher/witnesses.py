"""KERI.host federation witness directory.

The witness federation backing KERI.host services lives across several distinct
domains (all operated by the user, but treated as separate trust roots for
diversity of TLS / hosting / DNS). There is no remote ``/witness/pool``
discovery endpoint — the federation evolves slowly enough that a static config
is correct for v1.

Per the privacy rule, the REAL witness hosts/AIDs are NOT committed: they live
in the gitignored ``src/locksmith/release/deploy_config.json`` (committed
template: ``deploy_config.example.json``, all ``example.com``). This module
iterates that config's ``witnesses`` array to build the directory.

See memory ``[[reference-witness-federation]]`` and
``locksmith.release.deploy.load_deploy_config`` for the canonical record.
"""
from __future__ import annotations

from dataclasses import dataclass

from locksmith.release import load_deploy_config


@dataclass(frozen=True)
class WitnessInfo:
    aid: str
    oobi: str

    @classmethod
    def from_domain(cls, domain: str, aid: str) -> "WitnessInfo":
        # Per KERI spec OOBI convention: /oobi/<aid>/<role>
        # Matches keripy's OOBI_URL_TEMPLATE and the existing mailbox OOBI
        # pattern (https://<mailbox-host>/oobi/<aid>/mailbox).
        return cls(aid=aid, oobi=f"https://{domain}/oobi/{aid}/witness")

    @property
    def base_url(self) -> str:
        """Witness service base URL (the receipt endpoint, etc., hang off this)."""
        # OOBI: https://<domain>/oobi/<aid>/witness  →  base: https://<domain>
        from urllib.parse import urlparse
        parsed = urlparse(self.oobi)
        return f"{parsed.scheme}://{parsed.netloc}"


def default_witness_pool() -> list[WitnessInfo]:
    """Return the configured witness federation as a fresh list.

    Built by iterating ``deploy_config["witnesses"]``; each entry carries
    ``alias``/``host``/``aid`` (alias is informational here — the directory
    keys off host + AID). A fresh list is returned each call so callers may
    mutate it without affecting subsequent reads.
    """
    config = load_deploy_config()
    return [
        WitnessInfo.from_domain(w["host"], w["aid"])
        for w in config["witnesses"]
    ]
