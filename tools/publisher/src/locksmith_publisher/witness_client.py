"""HTTP client for the KERI.host 5-witness federation.

The federation witnesses (witness.keri.host, witness.legitim.us,
witness.goonei.com, witness.verdadero.me, witness.honest.town) run the
sam-witness Lambda handler (~/code/keripy/sam-witness/witness_handler.py),
which follows the keripy reference HTTP protocol.

Routes used by this client:

  POST {url}/receipts            — submit a signed CESR event stream;
                                   returns 200 + application/cesr body
                                   (receipt event) on success, 204 if the
                                   event didn't produce a receipt.
  GET  {url}/query?pre=<aid>&typ=kel
                                 — fetch current key state summary as JSON
                                   ({pre, sn, said, transferable, keys, wits}).
  GET  {url}/oobi/<aid>          — fetch the AID's KEL as a signed CESR stream.

Wire format details:

  - Content-Type: `application/cesr` (NOT `application/cesr+json`)
  - Submission body: inline CESR stream (event JSON + concatenated signature
    blocks). The witness also accepts JSON event in body + signatures in the
    CESR-ATTACHMENT header — this client uses the inline form because that's
    what `incept._attach_signatures()` produces.
  - Response for POST /receipts: raw application/cesr bytes containing one or
    more receipt events. Verifier parses these later with keripy.

See memory `[[reference-keri-wire-protocol]]` for the canonical protocol
reference; `[[reference-witness-federation]]` for the federation AID list.

Used by:
- Phase 1 inception ceremony — submit the signed `icp` event and collect
  receipts so the publisher AID is live on the federation.
- Phase 4 release-signing flow — submit each release `ixn` event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests


CESR_CONTENT_TYPE = "application/cesr"


class WitnessThresholdNotMet(Exception):
    """Fewer than `threshold` witnesses returned a receipt.

    The operator can retry the submission with the same event; witnesses
    are idempotent on event SAID, so receipts already collected on a
    prior attempt are not lost (the witness returns the same receipt
    again or returns 204 if it already saw the event).
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

    Security event: either a witness is misbehaving or the publisher AID
    has been compromised and a duplicitous KEL is being served. Abort and
    investigate.
    """

    def __init__(self, divergence: dict[str, Any]):
        super().__init__(f"witness duplicity: {divergence}")
        self.divergence = divergence


class WitnessUnreachable(Exception):
    """Every witness in the pool failed to respond at all.

    Distinct from `WitnessThresholdNotMet` (some responded, just not
    enough): here every request errored out. Retry after confirming
    network connectivity.
    """


@dataclass(frozen=True)
class Receipt:
    """A receipt response from one witness.

    `cesr_bytes` is the raw `application/cesr` body the witness returned
    (1+ KERI receipt events with attached signatures). Parsing into
    structured form happens elsewhere (keripy Parser); this client
    preserves the bytes so signature verification stays end-to-end.
    """

    witness_url: str
    cesr_bytes: bytes


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
        """POST a signed CESR event stream to each witness's `/receipts`,
        gather the returned receipts.

        Retries up to `max_retries` times for any witness that errors on a
        given attempt. Raises `WitnessThresholdNotMet` if fewer than
        `self.threshold` witnesses return a receipt across all attempts;
        raises `WitnessUnreachable` if zero witnesses respond at all.

        A witness response of 204 No Content means the witness accepted the
        event but had no receipt to return (e.g., it had already seen this
        event and returned it before). The submission counts as
        "responded" for unreachable tracking but does NOT count toward
        the receipt threshold.
        """
        receipts: list[Receipt] = []
        receipted_witnesses: set[str] = set()
        any_response: set[str] = set()
        for attempt in range(self.max_retries):
            remaining = [u for u in self.witness_urls
                         if u not in receipted_witnesses]
            if not remaining:
                break
            for url in remaining:
                endpoint = url.rstrip("/") + "/receipts"
                try:
                    resp = requests.post(
                        endpoint,
                        data=cesr_bytes,
                        headers={"Content-Type": CESR_CONTENT_TYPE},
                        timeout=self.timeout_sec,
                    )
                except (requests.RequestException, OSError):
                    continue
                any_response.add(url)
                if resp.status_code == 200 and resp.content:
                    receipts.append(Receipt(
                        witness_url=url,
                        cesr_bytes=resp.content,
                    ))
                    receipted_witnesses.add(url)
                # 204 No Content: accepted but no receipt returned. Don't
                # count toward receipts; don't retry this witness.
                elif resp.status_code == 204:
                    receipted_witnesses.add(url)
                # Other status codes: retry on next attempt.
            if len(receipts) >= self.threshold:
                return receipts
        if not any_response:
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
        """GET the witness's key-state summary for `aid` from each witness,
        return the consensus state.

        Uses GET `{url}/query?pre=<aid>&typ=kel`, which sam-witness implements
        as a JSON summary: `{pre, sn, said, transferable, keys, wits}`.

        Raises `WitnessThresholdNotMet` if fewer than `self.threshold`
        witnesses respond; raises `WitnessDuplicityDetected` if witnesses
        return inconsistent (said, sn) tuples.
        """
        responses: list[dict[str, Any]] = []
        for url in self.witness_urls:
            endpoint = url.rstrip("/") + "/query"
            try:
                resp = requests.get(
                    endpoint,
                    params={"pre": aid, "typ": "kel"},
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
        canonical = (responses[0]["said"], responses[0]["sn"])
        for r in responses[1:]:
            if (r["said"], r["sn"]) != canonical:
                raise WitnessDuplicityDetected({"responses": responses})
        return KeyState(
            current_said=responses[0]["said"],
            sn=responses[0]["sn"],
            keys=list(responses[0].get("keys", [])),
        )

    def query_kel(self, aid: str) -> bytes:
        """GET the full KEL for `aid` from the first witness that responds.

        Uses GET `{url}/oobi/<aid>` which returns a signed CESR stream
        containing the AID's KEL plus location/role reply events.

        Returns raw CESR bytes; caller parses with keripy. Raises
        `WitnessUnreachable` if no witness responds.
        """
        for url in self.witness_urls:
            endpoint = url.rstrip("/") + f"/oobi/{aid}"
            try:
                resp = requests.get(endpoint, timeout=self.timeout_sec)
                if resp.status_code == 200 and resp.content:
                    return resp.content
            except (requests.RequestException, OSError):
                continue
        raise WitnessUnreachable(
            f"no witness in pool returned KEL for {aid}"
        )
