#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
devctl — small CLI for talking to the Locksmith dev-control server.

Usage:

    python3 tools/devctl.py <op>                       # no-arg op
    python3 tools/devctl.py <op> '<json-args>'         # op with kwargs

Examples:

    python3 tools/devctl.py ping
    python3 tools/devctl.py screenshot
    python3 tools/devctl.py screenshot '{"path": "/tmp/my.png"}'
    python3 tools/devctl.py tree '{"clickable_only": true}'
    python3 tools/devctl.py click '{"target": "Templates"}'
    python3 tools/devctl.py type '{"target": "_name_field", "text": "Hello"}'
    python3 tools/devctl.py select '{"target": "_kind", "value": "government"}'
    python3 tools/devctl.py current_page

The Locksmith wallet must be running with LOCKSMITH_DEV_CONTROL=1 set in
its environment. The CLI exits with status 1 on connection failure and
status 2 on a server-reported error.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys


DEFAULT_SOCKET_PATH = "/tmp/locksmith-control.sock"


def send(op: str, kwargs: dict, socket_path: str, timeout: float) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(socket_path)
    except OSError as e:
        raise SystemExit(
            f"devctl: cannot connect to {socket_path}: {e}\n"
            f"  Is the wallet running with LOCKSMITH_DEV_CONTROL=1 set?"
        )
    payload = {"op": op, **kwargs}
    sock.sendall(json.dumps(payload).encode("utf-8") + b"\n")

    # Read until a newline appears. Responses are small (a few KB at most).
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    sock.close()

    line = buf.split(b"\n", 1)[0].decode("utf-8")
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        raise SystemExit(f"devctl: invalid JSON from server: {e}\n  {line!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Locksmith dev-control CLI")
    parser.add_argument("op", help="operation name (ping, screenshot, tree, click, …)")
    parser.add_argument(
        "args", nargs="?", default="{}",
        help="JSON object of keyword arguments (default: {})",
    )
    parser.add_argument(
        "--socket", default=DEFAULT_SOCKET_PATH,
        help=f"socket path (default: {DEFAULT_SOCKET_PATH})",
    )
    parser.add_argument(
        "--timeout", type=float, default=5.0,
        help="socket timeout in seconds (default: 5.0)",
    )
    args = parser.parse_args()

    try:
        kwargs = json.loads(args.args)
    except json.JSONDecodeError as e:
        print(f"devctl: arg is not valid JSON: {e}", file=sys.stderr)
        return 1
    if not isinstance(kwargs, dict):
        print("devctl: arg must be a JSON object", file=sys.stderr)
        return 1

    result = send(args.op, kwargs, args.socket, args.timeout)
    print(json.dumps(result, indent=2))
    if "error" in result:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
