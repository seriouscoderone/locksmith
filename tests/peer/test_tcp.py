import logging
import socket

from locksmith.peer.tcp import TCPServer


def _free_port():
    """Bind to port 0, read back the assigned port, close."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_bind_to_free_port_succeeds(caplog):
    port = _free_port()
    server = TCPServer(host="127.0.0.1", port=port)
    with caplog.at_level(logging.INFO, logger="locksmith.peer.tcp"):
        ok = server.reopen()
    try:
        assert ok is True
        assert server.opened is True
        assert any("peer.listener.started" in r.message and f"port={port}" in r.message
                   for r in caplog.records)
    finally:
        server.close()


def test_bind_to_held_port_fails_with_structured_log(caplog):
    # Hold the port with our own socket — disable REUSEADDR so the second
    # bind genuinely conflicts.
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]

    server = TCPServer(host="127.0.0.1", port=port)
    try:
        with caplog.at_level(logging.ERROR, logger="locksmith.peer.tcp"):
            ok = server.reopen()
        assert ok is False
        assert any("peer.listener.bind_failed" in r.message for r in caplog.records)
    finally:
        holder.close()
        server.close()


def test_close_emits_stopped_log(caplog):
    port = _free_port()
    server = TCPServer(host="127.0.0.1", port=port)
    server.reopen()
    with caplog.at_level(logging.INFO, logger="locksmith.peer.tcp"):
        server.close()
    assert any("peer.listener.stopped" in r.message for r in caplog.records)
