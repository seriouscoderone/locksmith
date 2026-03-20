# -*- encoding: utf-8 -*-
"""
locksmith.core.witnessing module

Functions for working with KERI witnesses
"""
from keri import help

logger = help.ogler.getLogger(__name__)

def get_unused_witnesses_for_rotation(app, hab):
    """
    Get witnesses that are available to rotate into an identifier.

    Filters out witnesses that:
    - Don't have the "witness" tag
    - Don't belong to this hab (different cid)
    - Are already in the hab's witness list
    - Are transferable (witnesses must be non-transferable)

    Parameters:
        app: The application instance with vault access
        hab: The hab (identifier) to get available witnesses for

    Returns:
        List of witness records that can be rotated into this identifier
    """
    unused_witnesses = []

    for remote_id in app.vault.org.list():
        # Skip if not tagged as witness or tagged with something else
        if "tag" in remote_id and remote_id["tag"] != "witness":
            continue

        # Skip if belongs to a different identifier
        if "cid" in remote_id and remote_id["cid"] != hab.pre:
            continue

        # Skip if already in the hab's witness list
        if remote_id['id'] in hab.kever.wits:
            continue

        # Skip if the witness is transferable (witnesses must be non-transferable)
        kevers = app.vault.hby.kevers
        if kevers[remote_id['id']].transferable:
            continue

        unused_witnesses.append(remote_id)

    return unused_witnesses

def get_current_witnesses_for_rotation(app, hab):
    """
    Get witnesses currently assigned to an identifier that can be rotated out.

    Parameters:
        app: The application instance with vault access
        hab: The hab (identifier) to get current witnesses for

    Returns:
        List of witness records currently assigned to this identifier
    """
    current_witnesses = []

    for wit_id in hab.kever.wits:
        # Try to find this witness in the org contacts
        for remote_id in app.vault.org.list():
            if remote_id.get('id') == wit_id:
                current_witnesses.append(remote_id)
                break
        else:
            # Witness not found in contacts, create minimal record
            current_witnesses.append({
                'id': wit_id,
                'alias': wit_id[:12] + '...',  # Truncated ID as fallback alias
                'oobi': None
            })

    return current_witnesses
