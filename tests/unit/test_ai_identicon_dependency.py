"""Smoke test: Locksmith can use the extracted `ai-identicon` dependency.

The avatar system was extracted to its own package (github.com/seriouscoderone
/ai-identicon) and Locksmith now depends on it. Its own exhaustive suite lives
in that repo; here we only assert the dependency is importable and renders, so
a broken/missing install fails Locksmith's CI early.

Run: .venv/bin/python -m pytest tests/unit/test_ai_identicon_dependency.py -q --import-mode=importlib
"""

from __future__ import annotations


def test_ai_identicon_imports_and_renders():
    import ai_identicon
    from ai_identicon import Genome, color_svg, line_art_svg, AvatarController

    assert ai_identicon.ALGO_VERSION == 1  # the version Locksmith is pinned against
    g = Genome.from_seed("EK7f-example-aid-prefix")
    assert color_svg(g).startswith("<svg")
    assert "<line" in line_art_svg(g, "white")
    # deterministic: same seed → identical portrait
    assert color_svg(Genome.from_seed("x")) == color_svg(Genome.from_seed("x"))
