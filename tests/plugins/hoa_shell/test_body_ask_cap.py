"""Stop prodding a peer that is silently withholding a body.

Two independent sources of wasted `pro`s, measured on the four-window actuarial
arc as **27 of 33 prods from the designer going to the admin**, which had nothing
to disclose to it:

1. Anchors that CANNOT have a body — registry inceptions and rotations. Filtered
   in `keri_serviceaid.providers.peer_sync.credential_anchors`, tested there,
   because the discriminator is the event construction in `keri/vdr/eventing.py`.
2. A real credential the peer declines to disclose. No filter can predict this,
   and the refusal is SILENT: `ProdResponder.processProd` returns None and logs on
   the RESPONDER's side (`keri/app/prodding.py:148-152`), so from the asker's side
   "withheld" and "in flight" are the same observation. Counting is the only stop.

This file covers (2).
"""
import logging

from locksmith.plugins.hoa_shell.peer_sync_doer import MAX_BODY_ASKS, PeerSyncDoer

PEER_A = "E" + "P" * 43
PEER_B = "E" + "Q" * 43
SAID = "E" + "S" * 43


def _doer():
    """A doer with no app: `_claim_body_ask` touches only its own counter dict, so
    constructing the real class is honest here and needs no vault."""
    return PeerSyncDoer(app=None)


def test_asks_are_allowed_up_to_the_cap_then_refused_forever():
    doer = _doer()
    allowed = [doer._claim_body_ask(PEER_A, SAID) for _ in range(MAX_BODY_ASKS)]
    assert allowed == [True] * MAX_BODY_ASKS, (
        "every ask up to the cap must go out -- giving up early stalls a leg")
    assert doer._claim_body_ask(PEER_A, SAID) is False
    # ...and it stays refused; this is not a sliding window.
    assert [doer._claim_body_ask(PEER_A, SAID) for _ in range(3)] == [False] * 3


def test_the_cap_is_per_peer_not_per_said():
    """The same SAID may be disclosable by one peer and withheld by another, so
    exhausting one peer must not give up on the others."""
    doer = _doer()
    for _ in range(MAX_BODY_ASKS):
        doer._claim_body_ask(PEER_A, SAID)
    assert doer._claim_body_ask(PEER_A, SAID) is False
    assert doer._claim_body_ask(PEER_B, SAID) is True, (
        "peer B was never asked; peer A's exhaustion must not speak for it")


def test_the_cap_is_per_said_not_per_peer():
    """The mirror of the above: one withheld credential must not stop this peer
    being asked about a different one."""
    doer = _doer()
    other = "E" + "T" * 43
    for _ in range(MAX_BODY_ASKS):
        doer._claim_body_ask(PEER_A, SAID)
    assert doer._claim_body_ask(PEER_A, SAID) is False
    assert doer._claim_body_ask(PEER_A, other) is True


def test_an_undelivered_ask_is_refunded_so_a_down_peer_is_never_written_off():
    """THE REGRESSION THIS FILE SHIPPED WITH, observed live on 2026-08-08.

    The cap counted asks at QUEUE time, with no knowledge of whether the bytes
    reached the peer. Driving the HOA against an admin that was not running
    produced six prods per SAID, "presuming withheld", and then permanent silence
    toward a peer that had never once been asked — strictly worse than the log
    noise the cap was added to fix. Zero replies and zero failures appeared in the
    log, because `peer_request` returns b"" for both "never connected" and
    "connected, said nothing" and `_drain` absorbed both.

    A down peer must be indefinitely re-askable."""
    doer = _doer()
    for _ in range(MAX_BODY_ASKS * 3):
        assert doer._claim_body_ask(PEER_A, SAID) is True, (
            "an undelivered ask must not consume the budget — a peer that is "
            "down has told us nothing about what it would disclose")
        doer._refund_body_ask(PEER_A, SAID)      # what _drain does on delivered=False


def test_a_refund_cannot_push_the_count_below_zero():
    doer = _doer()
    doer._refund_body_ask(PEER_A, SAID)
    doer._refund_body_ask(PEER_A, SAID)
    allowed = [doer._claim_body_ask(PEER_A, SAID) for _ in range(MAX_BODY_ASKS + 1)]
    assert allowed == [True] * MAX_BODY_ASKS + [False], (
        "refunds on an unasked pair must not buy extra asks")


def test_a_refund_after_giving_up_does_not_re_arm_the_asking():
    """The asymmetry is deliberate. Once a peer has DELIVERED-refused the full
    budget, a later unreachable blip must not restart the cycle — otherwise a
    genuinely withholding peer that also flaps gets prodded forever."""
    doer = _doer()
    for _ in range(MAX_BODY_ASKS):
        doer._claim_body_ask(PEER_A, SAID)
    assert doer._claim_body_ask(PEER_A, SAID) is False
    doer._refund_body_ask(PEER_A, SAID)
    assert doer._claim_body_ask(PEER_A, SAID) is False, (
        "a refund must not undo a give-up that delivered asks earned")


def test_exhaustion_is_announced_once_at_info():
    """A watch that quietly stops asking is indistinguishable from one that never
    asked. Log the give-up -- once, not on every subsequent tick.

    Captured by attaching a handler to the module's own logger rather than via
    caplog: these are `keri.help.ogler` loggers and do not propagate to pytest's
    root handler (the same reason tests/peer/test_peer_sync_roundtrip.py rolls its
    own `_Cap` handler)."""
    from locksmith.plugins.hoa_shell import peer_sync_doer as mod

    captured = []

    class _Cap(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    handler = _Cap(level=logging.INFO)
    mod.logger.addHandler(handler)
    previous = mod.logger.level
    mod.logger.setLevel(logging.INFO)
    try:
        doer = _doer()
        for _ in range(MAX_BODY_ASKS + 4):
            doer._claim_body_ask(PEER_A, SAID)
    finally:
        mod.logger.removeHandler(handler)
        mod.logger.setLevel(previous)

    lines = [m for m in captured if "body_asks_exhausted" in m]
    assert len(lines) == 1, f"expected exactly one give-up line, got {len(lines)}"
    assert SAID[:12] in lines[0]


def test_the_give_up_line_fires_only_once_the_ask_is_actually_declined():
    """It used to fire at `asks + 1 == MAX_BODY_ASKS` and then `return True`, so
    the log read "will not ask again" immediately followed by an outbound prod for
    the same SAID — measured in the live log, lines 139-140. The announcement must
    coincide with a refusal, not with the last permitted ask."""
    from locksmith.plugins.hoa_shell import peer_sync_doer as mod

    captured = []

    class _Cap(logging.Handler):
        def emit(self, record):
            captured.append((len(captured), record.getMessage()))

    handler = _Cap(level=logging.INFO)
    mod.logger.addHandler(handler)
    previous = mod.logger.level
    mod.logger.setLevel(logging.INFO)
    try:
        doer = _doer()
        results = []
        for _ in range(MAX_BODY_ASKS + 1):
            allowed = doer._claim_body_ask(PEER_A, SAID)
            results.append((allowed, [m for _, m in captured
                                      if "body_asks_exhausted" in m]))
    finally:
        mod.logger.removeHandler(handler)
        mod.logger.setLevel(previous)

    # Every allowed ask must have been announced-free; the announcement appears
    # on the first call that returns False.
    for allowed, announced in results[:MAX_BODY_ASKS]:
        assert allowed is True
        assert announced == [], (
            "the give-up was announced while the ask was still going out")
    allowed, announced = results[-1]
    assert allowed is False and len(announced) == 1


def test_the_cap_leaves_room_for_a_slow_peer():
    """A guard rail on the constant itself: at DEFAULT_TOCK seconds per pass, the
    cap has to span more than a couple of ticks or a peer that is merely slow gets
    written off as withholding. Measured arc legs take tens of seconds."""
    from locksmith.plugins.hoa_shell.peer_sync_doer import DEFAULT_TOCK
    assert MAX_BODY_ASKS * DEFAULT_TOCK >= 25, (
        f"{MAX_BODY_ASKS} asks x {DEFAULT_TOCK}s = "
        f"{MAX_BODY_ASKS * DEFAULT_TOCK}s is too short a window to distinguish "
        "'withheld' from 'slow'")
