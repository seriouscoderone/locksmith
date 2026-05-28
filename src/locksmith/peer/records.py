"""Persisted records and settings for peer mode."""
from dataclasses import dataclass


@dataclass
class PeerRecord:
    """One paired peer in the sender allowlist."""

    aid: str
    label: str
    endpoint_url: str
    paired_at: str = ""
    last_contacted_at: str = ""


@dataclass
class PeerModeSettings:
    """Vault-level configuration for the peer-mode listener."""

    enabled: bool = False
    port: int = 5621
    bind_host: str = "0.0.0.0"
    advertised_host: str = ""
