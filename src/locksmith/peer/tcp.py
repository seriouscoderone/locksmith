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

    def reopen(self, **kwa) -> bool:
        ok = super().reopen(**kwa)
        if ok:
            # hio's Acceptor.open updates self.ha to the post-bind sockname
            # but leaves self.eha at the user-requested (host, port). When
            # port=0 is requested, eha[1] stays 0 and serviceAxes raises
            # because the accepted socket's sockname has a real port. Sync
            # eha to the resolved ha so port=0 (OS-assign) works.
            self.eha = self.ha
            self._log_port = self.ha[1]
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
