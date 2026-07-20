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
    open_inbound: bool = False


@dataclass
class PeerHealth:
    """Last-seen reachability state for a paired peer's TCP endpoint.

    Updated by PeerHealthMonitorDoer on each probe cycle. The fields
    are written even on failure — last_outcome carries the machine-
    stable reason code from ReachabilityResult so the UI can render
    a meaningful state (reachable / refused / timeout / etc.) without
    re-running the probe.
    """

    aid: str = ""
    last_probed_at: str = ""           # ISO-8601 UTC of last attempt
    last_outcome: str = ""             # ok | refused | timeout | unreachable | dns_failure | invalid_host | other
    last_message: str = ""             # human-readable (from ReachabilityResult.message)
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    probed_count: int = 0
