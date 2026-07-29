"""Deterministic matcher (Phase 1, no LLM): utterance -> a grounded verb.

Scores each verb by how many of its phrasing tokens appear in the utterance. This is
the Phase-1 stand-in for the Phase-2 LLM proposer; both emit into the same surface. §4.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .surface import CommandSurface, Verb

_WORDS = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class MatchResult:
    verb: Verb | None
    candidates: tuple[Verb, ...]
    confident: bool


# Note: matching is a plain token-overlap score with no stopword filtering, so a
# command's display-name phrasings must avoid stopwords (e.g. "the", "a") — such
# tokens would inflate scores for unrelated utterances that happen to contain them.
def _score(verb: Verb, tokens: set[str]) -> int:
    return sum(1 for p in verb.phrasings if p in tokens)


def match(utterance: str, surface: CommandSurface) -> MatchResult:
    tokens = set(_WORDS.findall(utterance.lower()))
    scored = [(v, _score(v, tokens)) for v in surface.verbs]
    best = max((s for _, s in scored), default=0)
    if best == 0:
        return MatchResult(verb=None, candidates=(), confident=False)
    top = tuple(v for v, s in scored if s == best)
    if len(top) == 1:
        return MatchResult(verb=top[0], candidates=top, confident=True)
    return MatchResult(verb=None, candidates=top, confident=False)
