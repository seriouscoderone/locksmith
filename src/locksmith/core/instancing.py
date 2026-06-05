"""Cross-instance coordination and new-instance launching.

Multiple Locksmith processes can run at once, one open vault each. This
module provides:
  * vault_server_name() — a stable, unique QLocalServer name per vault.
  * find_free_port()    — pick a bindable TCP port (peer-listener default).
  * InstanceCoordinator — claim/release a vault via a per-vault local
    socket; deny + raise the owner when the vault is already open.
  * InstanceLauncher    — spawn a new OS process opened on a given vault.

The vault name is the context key — there is no HOME/base fork. All
vault state is already namespaced by vault name on disk.
"""
from __future__ import annotations

import hashlib
import socket

from keri import help

logger = help.ogler.getLogger(__name__)


def vault_server_name(base: str | None, vault: str) -> str:
    """Deterministic, collision-resistant local-socket name for a vault.

    Hashed to stay within local-socket name length/character limits and
    prefixed with the bundle id so it can't clash with other apps.
    """
    raw = f"{base or ''}\x00{vault}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return f"host.keri.locksmith.vault.{digest}"


def find_free_port(start: int = 5621, host: str = "0.0.0.0", limit: int = 200) -> int:
    """Return the first bindable TCP port at/after ``start``.

    Falls back to ``start`` if none found in the scan window (the caller's
    bind will then surface the conflict through the existing red status).
    """
    bind_host = "" if host == "0.0.0.0" else host
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((bind_host, port))
                return port
            except OSError:
                continue
    return start
