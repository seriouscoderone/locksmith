"""Smoke test: verify the two-wallet fixture brings both processes up
and both dev-control sockets answer a ping."""
import re
from pathlib import Path

import pytest

from .conftest import REPO_ROOT


@pytest.mark.integration
def test_both_wallets_respond_to_ping(two_wallets):
    devctl = two_wallets["devctl"]
    pong_a = devctl(two_wallets["a"]["sock"], "ping")
    pong_b = devctl(two_wallets["b"]["sock"], "ping")
    assert pong_a.get("ok") is True
    assert pong_b.get("ok") is True


_SOURCE_RE = re.compile(r"startup\.identity .*source=(\S+)")


@pytest.mark.integration
def test_spawned_wallets_run_the_tree_under_test(two_wallets):
    """The spawned wallets must import THIS checkout's ``src``, not another one.

    There is exactly one venv, at the main checkout, and its editable ``.pth``
    holds an absolute path to the main checkout's ``src`` (CLAUDE.md "Worktree
    venv isolation"). So a subprocess launched with the venv's interpreter
    bare-imports ``locksmith`` from the MAIN tree — every test here passes while
    exercising code the diff never touched. Switching the fixture to
    ``sys.executable`` fixes the crash but not that; only prepending this
    repo root's ``src`` to the subprocess PYTHONPATH does.

    Asserting on the wallet's own ``startup.identity source=`` line is what makes
    the guarantee machine-checkable — the wallet reports where it resolved from,
    so this cannot pass by accident from a worktree.
    """
    expected = str((REPO_ROOT / "src").resolve())
    for side in ("a", "b"):
        log = Path(two_wallets[side]["log"]).read_text(errors="replace")
        found = _SOURCE_RE.findall(log)
        assert found, (
            f"wallet {side} logged no 'startup.identity … source=' line. Either it "
            f"died before startup, or it imported a tree that predates that log "
            f"line — which is itself the bug this test exists to catch.\n"
            f"--- tail of {two_wallets[side]['log']} ---\n{log[-3000:]}"
        )
        assert found[-1] == expected, (
            f"wallet {side} is running code from {found[-1]!r}, not the tree under "
            f"test at {expected!r}. The fixture must prepend "
            f"PYTHONPATH=<repo_root>/src to the spawned wallet's env."
        )
