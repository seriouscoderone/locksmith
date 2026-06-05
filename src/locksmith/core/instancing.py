"""Cross-instance coordination and new-instance launching.

Multiple Locksmith processes can run at once, one open vault each. This
module provides:
  * vault_server_name() — a stable, unique QLocalServer name per vault.
  * find_free_port()    — pick a bindable TCP port (peer-listener default).
  * InstanceCoordinator — claim/release a vault via a per-vault local
    socket; deny + raise the owner when the vault is already open.
    (added in later tasks)
  * InstanceLauncher    — spawn a new OS process opened on a given vault.
    (added in later tasks)

The vault name is the context key — there is no HOME/base fork. All
vault state is already namespaced by vault name on disk.
"""
from __future__ import annotations

import hashlib
import socket

from keri import help
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = help.ogler.getLogger(__name__)

_CONNECT_TIMEOUT_MS = 200


def vault_server_name(base: str | None, vault: str) -> str:
    """Deterministic, collision-resistant local-socket name for a vault.

    Hashed to stay within local-socket name length/character limits and
    prefixed with the bundle id so it can't clash with other apps.
    """
    # NUL separator is unambiguous: filesystem paths and vault names cannot
    # contain NUL bytes on any supported OS.
    raw = f"{base or ''}\x00{vault}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return f"host.keri.locksmith.vault.{digest}"


def find_free_port(start: int = 5621, host: str = "0.0.0.0", limit: int = 200) -> int:
    """Return the first bindable TCP port at/after ``start``.

    Falls back to ``start`` if none found in the scan window (the caller's
    bind will then surface the conflict through the existing red status).
    """
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # Match the real peer listener (hio Server), which sets
            # SO_REUSEADDR=1, so the probe accurately predicts bindability.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start


class InstanceCoordinator:
    """Per-vault single-instance coordination over Qt local sockets.

    One coordinator lives per process. It can hold claims for more than
    one vault transiently (during a switch-in-place the new vault is
    claimed before the old one is released), so claims are tracked in a
    dict keyed by vault name.
    """

    def __init__(self, base: str | None = None, raise_window=None):
        self._base = base or ""
        self.raise_window = raise_window  # zero-arg callable, set by the window
        self._servers: dict[str, QLocalServer] = {}

    def _name(self, vault: str) -> str:
        return vault_server_name(self._base, vault)

    def request_raise(self, vault: str) -> bool:
        """Ask a running owner of ``vault`` to raise its window.

        Returns True if an owner answered (vault is open elsewhere).
        """
        sock = QLocalSocket()
        sock.connectToServer(self._name(vault))
        if sock.waitForConnected(_CONNECT_TIMEOUT_MS):
            logger.info(f"instance.raise.requested vault={vault}")
            sock.write(b"raise\n")
            sock.flush()
            sock.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
            sock.disconnectFromServer()
            sock.close()
            return True
        sock.abort()
        return False

    def claim(self, vault: str) -> bool:
        """Become the owner of ``vault``. Returns False if already owned
        elsewhere (in which case the owner has been asked to raise)."""
        if vault in self._servers:
            return True  # idempotent — we already own it
        if self.request_raise(vault):
            logger.info(f"instance.claim.denied vault={vault}")
            return False
        name = self._name(vault)
        # Clear a stale socket file left by a crashed owner; safe because
        # no live listener answered request_raise above.
        QLocalServer.removeServer(name)
        server = QLocalServer()
        if not server.listen(name):
            logger.error(
                f"instance.claim.listen_failed vault={vault} "
                f"err={server.errorString()}"
            )
            return False
        server.newConnection.connect(lambda v=vault: self._on_incoming(v))
        self._servers[vault] = server
        logger.info(f"instance.claim.granted vault={vault}")
        return True

    def _on_incoming(self, vault: str) -> None:
        server = self._servers.get(vault)
        if server is None:
            return
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readAll()  # drain the "raise" payload
            conn.close()
        logger.info(f"instance.raise.received vault={vault}")
        if self.raise_window is not None:
            self.raise_window()

    def probe(self, vault: str) -> bool:
        """Non-owning liveness check used to render drawer badges."""
        if vault in self._servers:
            return True
        sock = QLocalSocket()
        sock.connectToServer(self._name(vault))
        ok = sock.waitForConnected(_CONNECT_TIMEOUT_MS)
        sock.abort()
        sock.close()
        return ok

    def release(self, vault: str) -> None:
        server = self._servers.pop(vault, None)
        if server is not None:
            server.close()
            QLocalServer.removeServer(self._name(vault))
            logger.info(f"instance.released vault={vault}")

    def release_all(self) -> None:
        for vault in list(self._servers):
            self.release(vault)
