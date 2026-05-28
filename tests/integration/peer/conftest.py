"""Fixtures for two-wallet integration tests.

Spawns two Locksmith wallets in subprocesses with isolated HOME dirs,
matching the manual dev pattern documented in the spec:

- Wallet A: HOME=<tmpdir>/wallet_a, socket <tmpdir>/wallet_a/.locksmith-control.sock
- Wallet B: HOME=<tmpdir>/wallet_b, socket <tmpdir>/wallet_b/.locksmith-control.sock

Both wallets are launched with ``.venv/bin/python -m locksmith.main``.
The fixture symlinks the locksmith-ui-tester clone into each HOME so the
dev-control socket comes up on launch.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
HOST_PLUGINS_DIR = Path.home() / ".locksmith" / "plugins"


def _install_plugins(home: Path) -> None:
    """Copy the host's installed plugin set into <home>/.locksmith/plugins/.

    The plugin manager finds plugins via ``<plugins>/index.json``. We need
    both the index AND the clone directories it points at. Copying the
    whole directory is the most reliable way to get a working install
    inside the isolated HOME without re-running install logic.
    """
    if not HOST_PLUGINS_DIR.exists():
        pytest.skip(
            f"no plugin install on host at {HOST_PLUGINS_DIR}; "
            "integration tests require locksmith-ui-tester installed"
        )
    dest = home / ".locksmith" / "plugins"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    shutil.copytree(HOST_PLUGINS_DIR, dest, symlinks=False)


def _start_wallet(home: Path, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "locksmith.main"],
        env=env,
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
    )
    return proc


def _wait_for_socket(socket_path: Path, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if socket_path.exists():
            try:
                sock = socket.socket(socket.AF_UNIX)
                sock.settimeout(1.0)
                sock.connect(str(socket_path))
                sock.close()
                return
            except OSError:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"socket never appeared: {socket_path}")


def _devctl(socket_path: Path, op: str, **kwa) -> dict:
    sock = socket.socket(socket.AF_UNIX)
    sock.settimeout(5.0)
    sock.connect(str(socket_path))
    payload = json.dumps({"op": op, **kwa}).encode("utf-8") + b"\n"
    sock.sendall(payload)
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    sock.close()
    return json.loads(buf.split(b"\n", 1)[0])


@pytest.fixture
def two_wallets():
    # pytest's tmp_path lives under /private/var/folders/... which on
    # macOS easily exceeds the 104-char UDS path limit when we put a
    # .locksmith-control.sock inside it. Allocate our own short prefix.
    root = Path(tempfile.mkdtemp(prefix="lspeer-", dir="/tmp"))
    home_a = root / "a"
    home_b = root / "b"
    home_a.mkdir()
    home_b.mkdir()
    _install_plugins(home_a)
    _install_plugins(home_b)

    log_a = root / "a.log"
    log_b = root / "b.log"

    proc_a = _start_wallet(home_a, log_a)
    proc_b = _start_wallet(home_b, log_b)

    sock_a = home_a / ".locksmith-control.sock"
    sock_b = home_b / ".locksmith-control.sock"
    try:
        _wait_for_socket(sock_a)
        _wait_for_socket(sock_b)
        yield {
            "a": {"home": home_a, "log": log_a, "sock": sock_a, "proc": proc_a},
            "b": {"home": home_b, "log": log_b, "sock": sock_b, "proc": proc_b},
            "devctl": _devctl,
        }
    finally:
        for proc in (proc_a, proc_b):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(root, ignore_errors=True)
