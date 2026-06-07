"""Integration smoke: submit a release ixn payload via the Phase 1 WitnessClient.

The base ``WitnessClient`` is a Phase 1 deliverable. This file confirms the
seam between Phase 4's release-ixn anchor flow and the Phase 1 client — it
does NOT re-test the receipt-collection / threshold / duplicity / unreachable
paths that ``tools/publisher/tests/test_witness_client.py`` already covers.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from locksmith_publisher.witness_client import (
    Receipt,
    WitnessClient,
    WitnessThresholdNotMet,
)


WITNESS_URLS = [
    "https://witness.keri.host",
    "https://witness.legitim.us",
    "https://witness.goonei.com",
    "https://witness.verdadero.me",
    "https://witness.honest.town",
]


def _ok_response(payload: bytes):
    r = MagicMock(status_code=200, content=payload)
    r.raise_for_status.return_value = None
    return r


def test_release_ixn_submission_returns_receipts():
    """A serialized release ixn event submits exactly like an icp event."""
    wc = WitnessClient(witness_urls=WITNESS_URLS, threshold=3)
    ixn_payload = b'{"v":"KERI10JSON","t":"ixn","sn":"5",...}'  # opaque CESR stream
    with patch(
        "locksmith_publisher.witness_client.requests.post",
        return_value=_ok_response(b"WITNESS_RECEIPT_CESR"),
    ):
        receipts = wc.submit_event(ixn_payload)
    assert len(receipts) >= 3
    assert all(isinstance(r, Receipt) for r in receipts)
    assert all(r.cesr_bytes == b"WITNESS_RECEIPT_CESR" for r in receipts)


def test_release_ixn_submission_propagates_threshold_not_met():
    """If only one witness responds and threshold is 3, raise WitnessThresholdNotMet."""
    wc = WitnessClient(witness_urls=WITNESS_URLS, threshold=3, max_retries=1)

    def side_effect(url, **kwargs):
        if "witness.keri.host" in url:
            return _ok_response(b"AAAA")
        raise OSError("connection reset")

    ixn_payload = b'{"v":"KERI10JSON","t":"ixn","sn":"5",...}'
    with patch(
        "locksmith_publisher.witness_client.requests.post",
        side_effect=side_effect,
    ):
        with pytest.raises(WitnessThresholdNotMet) as e:
            wc.submit_event(ixn_payload)
    assert e.value.collected == 1
    assert e.value.threshold == 3
