# -*- encoding: utf-8 -*-
"""No name may be used that is never bound.

This repo has no lint configuration at all, which is how `make_hoa_resolver`
came to log through a `logger` that its module never defined (fixed 42fcfcb4).
The consequence was not a crash anyone saw: `on_vault_ui_ready` raised,
`PluginManager` caught it, and every branded HOA ran with no shell — no
onboarding wiring, no EGF resolution, no `PeerSyncDoer` — while loading all four
HOA plugins and rendering the brand. Every visible signal said it was fine.

A NameError on a branch the suite never takes is invisible to the suite. This is
the one check that does not need the branch taken.

Deliberately ONE rule (F821). Adopting ruff's defaults over a tree this size
would produce hundreds of style findings, and a gate that always fails is a gate
nobody runs.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"


def _ruff() -> list[str]:
    """The ruff to run: the venv's console script, else `python -m ruff`.

    Never skips. `ruff` is declared in the `test` extra precisely so its absence
    is a broken environment, not a reason to report green — a suite that
    silently ran nothing is the failure mode this whole file exists to prevent.
    """
    exe = Path(sys.executable).parent / "ruff"
    if exe.is_file():
        return [str(exe)]
    found = shutil.which("ruff")
    if found:
        return [found]
    pytest.fail(
        "ruff is not installed, so the undefined-name gate cannot run. It is "
        "declared in the `test` extra: pip install -e '.[test]'. This is a "
        "failure, not a skip — see this module's docstring."
    )


def test_no_undefined_names_in_src():
    proc = subprocess.run(
        [*_ruff(), "check", "--select", "F821", "--no-cache",
         "--output-format", "concise", str(SRC)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        "a name is used that is never bound — at runtime this is a NameError on "
        "whatever branch reaches it:\n\n"
        f"{proc.stdout}{proc.stderr}"
    )
