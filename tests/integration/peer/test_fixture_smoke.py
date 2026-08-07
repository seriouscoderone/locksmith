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


_DISCOVERY_RE = re.compile(r"plugin\.discovery .*loaded=(\[[^\]]*\])")
_EGF_RE = re.compile(r"egf\.resolved said=(\S+) dir=(\S+) authorities=(\[[^\]]*\])")


@pytest.mark.integration
def test_branded_wallets_actually_wire_their_hoa_shell(two_hoa_wallets):
    """A branded wallet must LOAD the shell and RESOLVE its EGF — not just look branded.

    This is the gate that was missing. ``make_hoa_resolver`` logged which
    ecosystem a build resolved from a module that had no ``logger`` (fixed in
    42fcfcb4): the call raised ``NameError``, the ``except`` handler raised the
    SAME ``NameError``, ``on_vault_ui_ready`` died, and ``PluginManager`` caught
    it as one ERROR line. The wallet still loaded all four HOA plugins and still
    rendered the brand — so every visible signal said "branded HOA" while it ran
    with no onboarding wiring, no EGF, and no ``PeerSyncDoer``. Every HOA test
    downstream then failed for a reason that had nothing to do with its subject.

    So assert all three legs, because each fails on its own:

    1. the shell is LOADED (brand composition + entry point + activation policy)
    2. ``on_vault_ui_ready`` did not blow up (the defect above)
    3. the EGF actually resolved to at least one authority — a wallet that
       trusts nobody accepts no role credential, and says nothing about it
    """
    for side in ("cuo", "actuary"):
        path = Path(two_hoa_wallets[side]["log"])
        log = path.read_text(errors="replace")
        tail = f"\n--- tail of {path} ---\n{log[-3000:]}"

        loaded = _DISCOVERY_RE.findall(log)
        assert loaded, f"{side} logged no plugin.discovery line at all.{tail}"
        assert "hoa_shell" in loaded[-1], (
            f"{side} is branded but did not LOAD hoa_shell: loaded={loaded[-1]}. "
            f"Either the brand does not list it under plugins.bundled, its "
            f"composed entry point is not installed in this venv, or the "
            f"activation policy vetoed it.{tail}")

        assert "plugin.vault_ui_ready_failed" not in log, (
            f"{side}'s HOA shell raised inside on_vault_ui_ready. The plugin is "
            f"loaded and the brand renders, so nothing else in this suite can "
            f"see it — but the shell wired NOTHING.{tail}")

        egf = _EGF_RE.findall(log)
        assert egf, (
            f"{side} never logged egf.resolved. Its brand pins an EGF, so the "
            f"shell either did not run or bailed before resolving it.{tail}")
        said, _dir, authorities = egf[-1]
        assert authorities not in ("[]", "['']"), (
            f"{side} resolved EGF {said} to NO authorities in its accept "
            f"phases. Every role gate resolves its issuer from this list, so "
            f"the wallet will reject every grant it is ever sent.{tail}")
