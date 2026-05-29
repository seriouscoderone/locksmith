"""Tests for locksmith_publisher.witness_client."""
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


def _ok_response(json_payload):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = json_payload
    r.raise_for_status.return_value = None
    return r


def test_submit_event_collects_receipts_above_threshold():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
    )
    fake_receipt = {"witness_aid": "Bwit", "receipt_cesr": "AAAA"}
    with patch("locksmith_publisher.witness_client.requests.post",
               return_value=_ok_response(fake_receipt)):
        receipts = wc.submit_event(b"event")
    assert len(receipts) == 3
    assert all(isinstance(r, Receipt) for r in receipts)


def test_submit_event_raises_threshold_not_met_when_too_few_succeed():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
        max_retries=1,
    )

    def side_effect(url, **kwargs):
        if "w1" in url:
            return _ok_response({"witness_aid": "Bw1", "receipt_cesr": "AAAA"})
        raise OSError("nope")

    with patch("locksmith_publisher.witness_client.requests.post",
               side_effect=side_effect):
        with pytest.raises(WitnessThresholdNotMet) as exc:
            wc.submit_event(b"event")
    assert exc.value.collected == 1
    assert exc.value.threshold == 2
    assert "retry" in str(exc.value).lower()


def test_submit_event_raises_unreachable_on_total_network_failure():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
            "https://api.keri.host/witness/w3/",
        ],
        threshold=2,
        max_retries=1,
    )

    def side_effect(url, **kwargs):
        raise OSError("connection refused")

    with patch("locksmith_publisher.witness_client.requests.post",
               side_effect=side_effect):
        with pytest.raises(WitnessUnreachable):
            wc.submit_event(b"event")


def test_query_state_detects_duplicity():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
        ],
        threshold=2,
    )

    def side_effect(url, **kwargs):
        if "w1" in url:
            return _ok_response({"current_said": "EHshA", "sn": 4, "keys": []})
        return _ok_response({"current_said": "EHshB", "sn": 4, "keys": []})

    with patch("locksmith_publisher.witness_client.requests.post",
               side_effect=side_effect):
        with pytest.raises(WitnessDuplicityDetected):
            wc.query_state("EAaa")


def test_query_state_returns_consistent_state():
    wc = WitnessClient(
        witness_urls=[
            "https://api.keri.host/witness/w1/",
            "https://api.keri.host/witness/w2/",
        ],
        threshold=2,
    )
    with patch("locksmith_publisher.witness_client.requests.post",
               return_value=_ok_response({"current_said": "EHshX", "sn": 4, "keys": ["DAaa"]})):
        ks = wc.query_state("EAaa")
    assert isinstance(ks, KeyState)
    assert ks.current_said == "EHshX"
    assert ks.sn == 4


def test_query_kel_returns_event_list():
    wc = WitnessClient(
        witness_urls=["https://api.keri.host/witness/w1/"],
        threshold=1,
    )
    payload = {"events": [
        {"sn": 0, "said": "EHsh0", "raw": "..."},
        {"sn": 1, "said": "EHsh1", "raw": "..."},
    ]}
    fake = MagicMock(status_code=200)
    fake.json.return_value = payload
    fake.raise_for_status.return_value = None
    with patch("locksmith_publisher.witness_client.requests.get",
               return_value=fake):
        events = wc.query_kel("EAaa")
    assert len(events) == 2
    assert events[0]["sn"] == 0


def test_timeout_is_configurable():
    wc = WitnessClient(
        witness_urls=["https://api.keri.host/witness/w1/"],
        threshold=1,
        timeout_sec=5,
    )
    with patch("locksmith_publisher.witness_client.requests.post",
               return_value=_ok_response({"witness_aid": "Bw1", "receipt_cesr": "AAAA"})) as p:
        wc.submit_event(b"event")
    # Verify timeout kwarg was passed through.
    _, kwargs = p.call_args
    assert kwargs["timeout"] == 5
