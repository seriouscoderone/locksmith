# -*- encoding: utf-8 -*-
"""
locksmith.plugins.kerifoundation.core.remoting module

HTTP clients for provisioning and registering controller AIDs with
KERI Foundation witnesses.
"""
from urllib.parse import urljoin

import requests
from keri import help
from keri.core import coring
from keri.app.httping import CESR_DESTINATION_HEADER

logger = help.ogler.getLogger(__name__)


def provision_witness(hab_pre, boot_url):
    """Provision a witness for a controller AID via POST /witnesses."""
    url = urljoin(boot_url, "/witnesses")
    logger.info(f"Provisioning {hab_pre[:12]}... via {url}")

    response = requests.post(
        url,
        json={"aid": hab_pre},
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    eid = data.get("eid", "")
    oobis = data.get("oobis") or []
    oobi = oobis[0] if oobis else ""

    if not eid:
        raise ValueError(f"Witness response missing 'eid' field: {data}")
    if not oobi:
        raise ValueError(f"Witness response missing 'oobis' field: {data}")

    logger.info(f"Provisioned witness {eid[:12]}... for {hab_pre[:12]}...")

    return {"eid": eid, "oobi": oobi}


def register_with_witness(hab, witness_eid, witness_url, secret=None):
    """Register a controller AID with a witness via POST /aids.

    Sends the controller's KEL to the witness. The witness returns an
    encrypted TOTP seed that only the controller can decrypt.

    Args:
        hab: Habery instance for the controller identifier
        witness_eid: Witness AID (prefix) to register with
        witness_url: Base URL of the witness server
        secret: Optional shared secret (base32 str) for batch mode.
                If provided, all witnesses in the batch use this secret.
                If None, the witness generates its own secret.

    Returns:
        dict with keys: totp_seed (str), oobi (str), eid (str)

    Raises:
        requests.HTTPError: If the witness returns a non-200 response
        ValueError: If the response is missing expected fields
    """
    # Build KEL from controller's event log
    body = bytearray()
    for msg in hab.db.clonePreIter(pre=hab.pre):
        body.extend(msg)

    fargs = {"kel": body.decode("utf-8")}

    # Include shared secret for batch mode
    if secret is not None:
        fargs["secret"] = secret

    # Include delegator KEL if identifier is delegated
    if hab.kever.delegated:
        delkel = bytearray()
        for msg in hab.db.clonePreIter(hab.kever.delpre):
            delkel.extend(msg)
        fargs["delkel"] = delkel.decode("utf-8")

    headers = {CESR_DESTINATION_HEADER: witness_eid}

    url = urljoin(witness_url, "/aids")
    logger.info(f"Registering {hab.pre[:12]}... with witness {witness_eid[:12]}... at {url}")

    # POST multipart/form-data (requests sets Content-Type automatically)
    response = requests.post(
        url,
        files={k: (None, v) for k, v in fargs.items()},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    if "totp" not in data:
        raise ValueError(f"Witness response missing 'totp' field: {data}")

    # Decrypt TOTP seed: encrypted with controller's public key
    m = coring.Matter(qb64=data["totp"])
    d = coring.Matter(qb64=hab.decrypt(ser=m.raw))
    seed = d.raw.decode("utf-8")

    logger.info(f"Successfully registered with witness {witness_eid[:12]}...")

    return {
        "totp_seed": seed,
        "oobi": data.get("oobi", ""),
        "eid": witness_eid,
    }


def deprovision_witness(eid: str, boot_url: str) -> bool:
    """Best-effort DELETE /witnesses/{eid} on the boot server.

    Returns ``True`` on a successful (2xx) response, ``False`` on any
    error.  Never raises — failures are logged as warnings.

    Note: witness-hk may return 500 for an unknown *eid* because
    ``deleteWitness`` raises ``ValueError`` which the HTTP handler does
    not catch as a ``ConfigurationError``.  This is a known gap.
    """
    url = urljoin(boot_url, f"/witnesses/{eid}")
    logger.info(f"Deprovisioning witness {eid[:12]}... via DELETE {url}")

    try:
        response = requests.delete(url, timeout=15)
        response.raise_for_status()
        logger.info(f"Deprovisioned witness {eid[:12]}...")
        return True
    except Exception:
        logger.warning(f"Failed to deprovision witness {eid[:12]}... at {url}", exc_info=True)
        return False
