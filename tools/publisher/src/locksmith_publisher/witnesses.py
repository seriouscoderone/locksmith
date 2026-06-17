"""KERI.host federation witness directory.

The 5-witness federation backing KERI.host services lives across 5 distinct
domains (all operated by the user, but treated as separate trust roots for
diversity of TLS / hosting / DNS). There is no remote `/witness/pool`
discovery endpoint — the federation evolves slowly enough that hardcoding the
list in source is correct for v1.

See memory `[[reference-witness-federation]]` for the canonical record.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WitnessInfo:
    aid: str
    oobi: str

    @classmethod
    def from_domain(cls, domain: str, aid: str) -> "WitnessInfo":
        # Per KERI spec OOBI convention: /oobi/<aid>/<role>
        # Matches keripy's OOBI_URL_TEMPLATE and the existing mailbox.keri.host
        # pattern (https://mailbox.keri.host/oobi/<aid>/mailbox).
        return cls(aid=aid, oobi=f"https://{domain}/oobi/{aid}/witness")

    @property
    def base_url(self) -> str:
        """Witness service base URL (the receipt endpoint, etc., hang off this)."""
        # OOBI: https://<domain>/oobi/<aid>/witness  →  base: https://<domain>
        from urllib.parse import urlparse
        parsed = urlparse(self.oobi)
        return f"{parsed.scheme}://{parsed.netloc}"


KERI_HOST_FEDERATION: tuple[WitnessInfo, ...] = (
    WitnessInfo.from_domain("witness.keri.host",    "BE4B4CjpxNrCv8_HjLYvcwz-sui6AcJdygO-afEoTpmi"),
    WitnessInfo.from_domain("witness.legitim.us",   "BFuK9vjfkaGd5DdyAABzd00vmsxQ3bDDnUAAGpxc7ZGP"),
    WitnessInfo.from_domain("witness.goonei.com",   "BE7l4TEmGGpDAccj5Hc0bcIm5nABU2V2gFTrcF5NfT2j"),
    WitnessInfo.from_domain("witness.verdadero.me", "BGR9eydkMxsAniqb3FSJwA24ADRM96STzWE_aaOeiyC5"),
    WitnessInfo.from_domain("witness.honest.town",  "BKCg06XEU80byz4ioN4Iim-7x2TzuklqKKuWRrViDqGV"),
)


def default_witness_pool() -> list[WitnessInfo]:
    """Return the canonical 5-witness federation as a fresh list."""
    return list(KERI_HOST_FEDERATION)
