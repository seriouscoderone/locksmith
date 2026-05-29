import json

import pytest
import responses

from locksmith_publisher.witnesses import (
    WitnessInfo,
    discover_witness_pool,
    WitnessDiscoveryError,
)


@responses.activate
def test_discover_witness_pool_returns_three_witnesses():
    api_url = "https://api.keri.host/witness/pool"
    payload = {
        "witnesses": [
            {"aid": "BAAA", "oobi": "https://api.keri.host/witness/oobi/BAAA"},
            {"aid": "BBBB", "oobi": "https://api.keri.host/witness/oobi/BBBB"},
            {"aid": "BCCC", "oobi": "https://api.keri.host/witness/oobi/BCCC"},
        ]
    }
    responses.add(responses.GET, api_url, json=payload, status=200)
    result = discover_witness_pool(api_url)
    assert len(result) == 3
    assert isinstance(result[0], WitnessInfo)
    assert result[0].aid == "BAAA"
    assert result[0].oobi.endswith("BAAA")


@responses.activate
def test_discover_witness_pool_raises_when_too_few():
    api_url = "https://api.keri.host/witness/pool"
    responses.add(responses.GET, api_url, json={"witnesses": [
        {"aid": "BAAA", "oobi": "https://api.keri.host/witness/oobi/BAAA"},
        {"aid": "BBBB", "oobi": "https://api.keri.host/witness/oobi/BBBB"},
    ]}, status=200)
    with pytest.raises(WitnessDiscoveryError, match="at least 3"):
        discover_witness_pool(api_url, minimum=3)


@responses.activate
def test_discover_witness_pool_raises_on_http_error():
    api_url = "https://api.keri.host/witness/pool"
    responses.add(responses.GET, api_url, status=503)
    with pytest.raises(WitnessDiscoveryError, match="HTTP 503"):
        discover_witness_pool(api_url)
