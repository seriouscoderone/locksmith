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
import sys
from pathlib import Path

from keri import help
from PySide6.QtCore import QProcess
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
            sock.deleteLater()  # reclaim the parentless socket on next event loop pass
            return True
        sock.abort()
        sock.deleteLater()  # reclaim the parentless socket on next event loop pass
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
        # The connect-first check above means any socket file here is stale
        # (crashed owner), so removing it is safe; the LMDB single-writer
        # lock (later task) is the backstop for the simultaneous-claim race.
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
        if conn is None:
            return
        # Distinguish an explicit raise request from a liveness probe.
        # probe() connects (to check we're alive) and disconnects WITHOUT
        # writing anything, so it must NOT bring us to the front — only an
        # actual "raise" command from request_raise should. Reading on a
        # probe returns promptly because the peer has already disconnected.
        requested = False
        if conn.waitForReadyRead(_CONNECT_TIMEOUT_MS):
            requested = b"raise" in bytes(conn.readAll())
        conn.close()
        conn.deleteLater()
        if not requested:
            logger.debug(f"instance.probe.received vault={vault}")
            return
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
        sock.deleteLater()  # reclaim the parentless socket on next event loop pass
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


class InstanceLauncher:
    """Spawn a new OS process of this app, optionally opened on a vault.

    Mirrors the plugin-restart relaunch pattern in
    ``ui/window.py::_handle_restart_requested`` (QProcess.startDetached),
    extended with a ``--vault`` argument.
    """

    # Pixels to offset a new instance from the launching window so both are
    # visible at once (Windows/VS Code-style cascade): down and to the right.
    # (Down-left clamps against the screen's left edge and overlaps instead.)
    _CASCADE_DX = 48
    _CASCADE_DY = 48

    @staticmethod
    def launch_new(vault: str | None = None, origin_xy: tuple[int, int] | None = None) -> None:
        extra = ["--vault", vault] if vault else []
        if origin_xy is not None:
            # Cascade off the launching window's position so the new instance
            # doesn't land exactly on top of it. Clamped to the screen edge.
            tx = max(0, int(origin_xy[0]) + InstanceLauncher._CASCADE_DX)
            ty = max(0, int(origin_xy[1]) + InstanceLauncher._CASCADE_DY)
            extra += ["--win-pos", f"{tx},{ty}"]
        if getattr(sys, "frozen", False):
            if sys.platform == "darwin":
                # sys.executable -> .../Locksmith.app/Contents/MacOS/Locksmith
                app_bundle = str(Path(sys.executable).parents[2])
                QProcess.startDetached("open", ["-n", app_bundle, "--args"] + extra)
                logger.info(f"instance.launch.spawned platform={sys.platform} vault={vault}")
                return
            QProcess.startDetached(sys.executable, sys.argv[1:] + extra)
        else:
            QProcess.startDetached(sys.executable, ["-m", "locksmith.main"] + extra)
        logger.info(f"instance.launch.spawned platform={sys.platform} vault={vault}")
