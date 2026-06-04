"""Tests for locksmith_publisher.witness_client.

Tests the actual sam-witness wire protocol:
- POST /receipts with application/cesr, body = CESR stream
- Response 200 + application/cesr body = receipt collected
- Response 204 = accepted but no receipt (don't count)
- GET /query?pre=<aid>&typ=kel returns JSON key state
- GET /oobi/<aid> returns CESR stream
"""
from unittest.mock import MagicMock, patch

import pytest

from locksmith_publisher.witness_client import (
    KeyState,
    Receipt,
    WitnessClient,
    WitnessDuplicityDetected,
    WitnessThresholdNotMet,
    WitnessUnreachable,
)


def _cesr_receipt_response(body: bytes = b"-FAB-receipt-stub"):
    """Mock a 200 application/cesr response with `body` in the response content."""
    r = MagicMock()
    r.status_code = 200
    r.content = body
    return r


def _empty_204_response():
    r = MagicMock()
    r.status_code = 204
    r.content = b""
    return r


def _json_ok_response(payload):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = payload
    r.content = b'{"stub": "json"}'
    r.raise_for_status.return_value = None
    return r


# Three federation-shaped URLs for testing (the actual federation URLs
# without paths — the client appends /receipts, /query, /oobi/<aid>).
FED = [
    "https://witness.keri.host",
    "https://witness.legitim.us",
    "https://witness.goonei.com",
]


def test_submit_event_collects_receipts_above_threshold():
    wc = WitnessClient(witness_urls=FED, threshold=2)
    with patch(
        "locksmith_publisher.witness_client.requests.post",
        return_value=_cesr_receipt_response(b"-FAB-w1-receipt"),
    ):
        receipts = wc.submit_event(b"event")
    assert len(receipts) == 3
    assert all(isinstance(r, Receipt) for r in receipts)
    assert all(r.cesr_bytes == b"-FAB-w1-receipt" for r in receipts)


def test_submit_event_posts_to_receipts_path_with_cesr_content_type():
    wc = WitnessClient(witness_urls=FED[:1], threshold=1)
    with patch(
        "locksmith_publisher.witness_client.requests.post",
        return_value=_cesr_receipt_response(),
    ) as p:
        wc.submit_event(b"event-bytes")
    url_arg, kwargs = p.call_args
    # Endpoint must be /receipts, not /witness/process or anything else.
    assert url_arg[0] == "https://witness.keri.host/receipts"
    assert kwargs["headers"]["Content-Type"] == "application/cesr"
    assert kwargs["data"] == b"event-bytes"


def test_submit_event_records_witness_url_in_receipt():
    """The Receipt should record WHICH witness URL produced it."""
    wc = WitnessClient(witness_urls=FED, threshold=3)
    with patch(
        "locksmith_publisher.witness_client.requests.post",
        return_value=_cesr_receipt_response(b"-FAB-receipt"),
    ):
        receipts = wc.submit_event(b"event")
    urls_seen = {r.witness_url for r in receipts}
    assert urls_seen == set(FED)


def test_submit_event_204_does_not_count_toward_threshold():
    """204 No Content means the witness accepted but had no receipt to give."""
    wc = WitnessClient(witness_urls=FED, threshold=2, max_retries=1)

    def side_effect(url, **kwargs):
        if "keri.host" in url:
            return _cesr_receipt_response(b"-FAB-receipt")
        return _empty_204_response()

    with patch(
        "locksmith_publisher.witness_client.requests.post",
        side_effect=side_effect,
    ):
        with pytest.raises(WitnessThresholdNotMet) as exc:
            wc.submit_event(b"event")
    assert exc.value.collected == 1
    assert exc.value.threshold == 2


def test_submit_event_raises_threshold_not_met_when_too_few_succeed():
    wc = WitnessClient(witness_urls=FED, threshold=2, max_retries=1)

    def side_effect(url, **kwargs):
        if "keri.host" in url:
            return _cesr_receipt_response(b"-FAB-receipt")
        raise OSError("nope")

    with patch(
        "locksmith_publisher.witness_client.requests.post",
        side_effect=side_effect,
    ):
        with pytest.raises(WitnessThresholdNotMet) as exc:
            wc.submit_event(b"event")
    assert exc.value.collected == 1
    assert exc.value.threshold == 2
    assert "retry" in str(exc.value).lower()


def test_submit_event_raises_unreachable_on_total_network_failure():
    wc = WitnessClient(witness_urls=FED, threshold=2, max_retries=1)

    def side_effect(url, **kwargs):
        raise OSError("connection refused")

    with patch(
        "locksmith_publisher.witness_client.requests.post",
        side_effect=side_effect,
    ):
        with pytest.raises(WitnessUnreachable):
            wc.submit_event(b"event")


def test_submit_event_non_200_non_204_status_retries_then_fails():
    """A 500 or other error status should not count and should be retried."""
    wc = WitnessClient(witness_urls=FED[:1], threshold=1, max_retries=2)
    err_resp = MagicMock(status_code=500, content=b"oops")

    with patch(
        "locksmith_publisher.witness_client.requests.post",
        return_value=err_resp,
    ) as p:
        with pytest.raises(WitnessThresholdNotMet):
            wc.submit_event(b"event")
    # Verified retried (max_retries=2 attempts)
    assert p.call_count == 2


def test_query_state_uses_get_with_query_params():
    """query_state should GET /query?pre=<aid>&typ=kel."""
    wc = WitnessClient(witness_urls=FED[:1], threshold=1)
    with patch(
        "locksmith_publisher.witness_client.requests.get",
        return_value=_json_ok_response({
            "pre": "EAaa", "sn": 4, "said": "EHshX",
            "transferable": True, "keys": ["DAaa"], "wits": [],
        }),
    ) as p:
        ks = wc.query_state("EAaa")
    url_arg, kwargs = p.call_args
    assert url_arg[0] == "https://witness.keri.host/query"
    assert kwargs["params"] == {"pre": "EAaa", "typ": "kel"}
    assert ks.current_said == "EHshX"
    assert ks.sn == 4


def test_query_state_detects_duplicity():
    wc = WitnessClient(witness_urls=FED[:2], threshold=2)

    def side_effect(url, **kwargs):
        if "keri.host" in url:
            return _json_ok_response({"sn": 4, "said": "EHshA", "keys": []})
        return _json_ok_response({"sn": 4, "said": "EHshB", "keys": []})

    with patch(
        "locksmith_publisher.witness_client.requests.get",
        side_effect=side_effect,
    ):
        with pytest.raises(WitnessDuplicityDetected):
            wc.query_state("EAaa")


def test_query_state_returns_consistent_state():
    wc = WitnessClient(witness_urls=FED[:2], threshold=2)
    with patch(
        "locksmith_publisher.witness_client.requests.get",
        return_value=_json_ok_response({
            "sn": 4, "said": "EHshX", "keys": ["DAaa"],
        }),
    ):
        ks = wc.query_state("EAaa")
    assert isinstance(ks, KeyState)
    assert ks.current_said == "EHshX"
    assert ks.sn == 4
    assert ks.keys == ["DAaa"]


def test_query_kel_returns_cesr_bytes():
    """query_kel should GET /oobi/<aid> and return the raw CESR body."""
    wc = WitnessClient(witness_urls=FED[:1], threshold=1)
    cesr_stream = b'{"v":"KERI10JSON..","t":"icp",...}-AAB...'
    with patch(
        "locksmith_publisher.witness_client.requests.get",
        return_value=_cesr_receipt_response(cesr_stream),
    ) as p:
        kel = wc.query_kel("EAaa")
    url_arg, kwargs = p.call_args
    assert url_arg[0] == "https://witness.keri.host/oobi/EAaa"
    assert kel == cesr_stream


def test_query_kel_raises_unreachable_when_no_witness_responds():
    wc = WitnessClient(witness_urls=FED[:1], threshold=1)
    with patch(
        "locksmith_publisher.witness_client.requests.get",
        side_effect=OSError("nope"),
    ):
        with pytest.raises(WitnessUnreachable):
            wc.query_kel("EAaa")


def test_timeout_is_configurable():
    wc = WitnessClient(witness_urls=FED[:1], threshold=1, timeout_sec=5)
    with patch(
        "locksmith_publisher.witness_client.requests.post",
        return_value=_cesr_receipt_response(),
    ) as p:
        wc.submit_event(b"event")
    _, kwargs = p.call_args
    assert kwargs["timeout"] == 5
