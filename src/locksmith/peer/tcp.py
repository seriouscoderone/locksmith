"""TCP listener for peer-mode direct messaging.

Wraps hio.core.tcp.serving.Server so we can add structured log lines
without forking the underlying networking code.
"""
from __future__ import annotations

from hio.core.tcp.serving import Server
from keri import help

logger = help.ogler.getLogger(__name__)


class TCPServer(Server):
    """hio TCP Server subclass that emits peer.listener.* structured logs."""

    def __init__(self, host: str = "0.0.0.0", port: int = 5621, **kwa):
        super().__init__(host=host, port=port, **kwa)
        self._log_host = host
        self._log_port = port

    def reopen(self) -> bool:
        ok = super().reopen()
        if ok:
            logger.info(
                f"peer.listener.started host={self._log_host} port={self._log_port}"
            )
        else:
            logger.error(
                f"peer.listener.bind_failed host={self._log_host} port={self._log_port}"
            )
        return ok

    def close(self):
        was_open = self.opened
        super().close()
        if was_open:
            logger.info(
                f"peer.listener.stopped host={self._log_host} port={self._log_port}"
            )
