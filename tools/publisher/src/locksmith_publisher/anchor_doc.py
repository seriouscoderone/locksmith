"""Pure builder for the publisher trust anchor (publisher_anchor.json).

Schema consumed by locksmith/update/cli.py:_load_publisher_anchor + verify.
For sn=0 the inception event's SAID is the AID prefix, so embedded_kel_hash
equals publisher_aid.
"""
from __future__ import annotations


def build_publisher_anchor(*, publisher_aid: str, witness_oobis: list[str],
                           toad: int = 3) -> dict:
    return {
        "publisher_aid": publisher_aid,
        "embedded_kel_sn": 0,
        "embedded_kel_hash": publisher_aid,
        "toad": toad,
        "witness_oobis": list(witness_oobis),
    }
