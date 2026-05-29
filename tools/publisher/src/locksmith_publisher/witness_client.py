"""HTTP client for the api.keri.host witness pool.

Endpoints (per ~/KERI/code/kerihost/README.md):

  POST {witness_url}/witness/process   — submit a CESR event stream; returns a receipt
  POST {witness_url}/witness/query     — fetch current key state for a publisher AID
  GET  {witness_url}/witness/kel/{aid} — fetch the full KEL for a publisher AID

The client is intentionally thin: it issues HTTP calls, applies a `threshold`
decision over the witness pool, and raises typed exceptions. Heavy KERI logic
(event construction, KEL replay, seal extraction) lives elsewhere.

Used by:
- Phase 1 inception ceremony — submit the signed `icp` event and collect receipts
- Phase 4 release-signing flow — submit each release `ixn` event (§7.5 step 4)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests


class WitnessThresholdNotMet(Exception):
    """Fewer than `threshold` witnesses returned a successful response.

    The operator can retry the submission with the same event; receipts already
    collected on a prior attempt are not lost because witnesses are idempotent
    on event SAID.
    """

    def __init__(self, collected: int, threshold: int):
        super().__init__(
            f"only {collected}/{threshold} witness receipts collected; "
            f"retry the submission (witnesses are idempotent on event SAID)"
        )
        self.collected = collected
        self.threshold = threshold


class WitnessDuplicityDetected(Exception):
    """Witnesses returned divergent key states for the same publisher AID.

    This is a security event: either a witness is misbehaving or the publisher
    AID has been compromised and a duplicitous KEL is being served. The
    ceremony must abort and the operator must investigate.
    """

    def __init__(self, divergence: dict[str, Any]):
        super().__init__(f"witness duplicity: {divergence}")
        self.divergence = divergence


class WitnessUnreachable(Exception):
    """Every witness in the pool failed to respond.

    Distinct from `WitnessThresholdNotMet` (some succeeded, just not enough):
    here the network is broken or the pool is entirely down. Retry after
    confirming network connectivity to api.keri.host.
    """


@dataclass(frozen=True)
class Receipt:
    witness_aid: str
    receipt_cesr: str


@dataclass(frozen=True)
class KeyState:
    current_said: str
    sn: int
    keys: list[str] = field(default_factory=list)


@dataclass
class WitnessClient:
    witness_urls: list[str]
    threshold: int
    timeout_sec: int = 30
    max_retries: int = 3

    def submit_event(self, cesr_bytes: bytes) -> list[Receipt]:
        """POST a CESR event stream to every witness, gather receipts.

        Retries up to `max_retries` times for any witness that errors on a
        given attempt. Raises `WitnessThresholdNotMet` if fewer than
        `self.threshold` witnesses return a receipt across all attempts;
        raises `WitnessUnreachable` if zero witnesses respond at all.
        """
        receipts: list[Receipt] = []
        seen_witnesses: set[str] = set()
        for attempt in range(self.max_retries):
            remaining = [u for u in self.witness_urls
                         if u not in seen_witnesses]
            if not remaining:
                break
            for url in remaining:
                endpoint = url.rstrip("/") + "/witness/process"
                try:
                    resp = requests.post(
                        endpoint, data=cesr_bytes,
                        headers={"Content-Type": "application/cesr+json"},
                        timeout=self.timeout_sec,
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                    receipts.append(Receipt(
                        witness_aid=payload["witness_aid"],
                        receipt_cesr=payload["receipt_cesr"],
                    ))
                    seen_witnesses.add(url)
                except (requests.RequestException, OSError, KeyError, ValueError):
                    continue
            if len(receipts) >= self.threshold:
                return receipts
        if not receipts:
            raise WitnessUnreachable(
                f"no response from any of {len(self.witness_urls)} witnesses "
                f"after {self.max_retries} attempts"
            )
        if len(receipts) < self.threshold:
            raise WitnessThresholdNotMet(
                collected=len(receipts),
                threshold=self.threshold,
            )
        return receipts

    def query_state(self, aid: str) -> KeyState:
        """POST a key-state query to every witness, return the consensus state.

        Raises `WitnessThresholdNotMet` if fewer than `self.threshold`
        witnesses respond; raises `WitnessDuplicityDetected` if witnesses
        return inconsistent (current_said, sn) tuples.
        """
        responses: list[dict[str, Any]] = []
        for url in self.witness_urls:
            endpoint = url.rstrip("/") + "/witness/query"
            try:
                resp = requests.post(
                    endpoint, json={"aid": aid},
                    timeout=self.timeout_sec,
                )
                resp.raise_for_status()
                responses.append(resp.json())
            except (requests.RequestException, OSError, ValueError):
                continue
        if len(responses) < self.threshold:
            raise WitnessThresholdNotMet(
                collected=len(responses),
                threshold=self.threshold,
            )
        canonical = (responses[0]["current_said"], responses[0]["sn"])
        for r in responses[1:]:
            if (r["current_said"], r["sn"]) != canonical:
                raise WitnessDuplicityDetected({"responses": responses})
        return KeyState(
            current_said=responses[0]["current_said"],
            sn=responses[0]["sn"],
            keys=list(responses[0].get("keys", [])),
        )

    def query_kel(self, aid: str) -> list[dict[str, Any]]:
        """GET the full KEL for `aid` from the first witness that responds.

        Returns a list of event dicts (`sn`, `said`, `raw`). Raises
        `WitnessUnreachable` if no witness responds.
        """
        for url in self.witness_urls:
            endpoint = url.rstrip("/") + f"/witness/kel/{aid}"
            try:
                resp = requests.get(endpoint, timeout=self.timeout_sec)
                resp.raise_for_status()
                body = resp.json()
                return list(body.get("events", []))
            except (requests.RequestException, OSError, ValueError):
                continue
        raise WitnessUnreachable(
            f"no witness in pool returned KEL for {aid}"
        )
