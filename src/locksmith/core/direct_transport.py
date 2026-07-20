"""Idempotent direct-mode transport bring-up for HOA builds (spec Sec 5).

On vault open for an onboarding brand whose EGF declares a
mode="direct" authority endpoint: (1) enable the peer listener
(carrier ports start at 5622 — 5621 is the DOI convention), (2) expose
the default AID + publish its peer role (witnessless AIDs land local
rpys and emit no_witnesses — expected), (3) pair each direct authority
from its bundled OOBI artifact (kevers + locs + PeerRecord). All
failures surface as ("DirectTransport","transport_failed") events —
never silent, never fatal to vault open.
"""
from __future__ import annotations

from keri import help, kering

from keri_serviceaid.egf.errors import EgfError
from keri_serviceaid.egf.oobi_source import LocalDirOobiSource

from locksmith.core.branding import brand, egf_local_dir
from locksmith.core.instancing import find_free_port
from locksmith.peer.allowlist import PeerAllowlist
from locksmith.peer.cesr_blob import PeerBlobError
from locksmith.peer.oobi_import import parse_oobi_cesr
from locksmith.peer.publishing import PublishPeerRoleDoer
from locksmith.peer.records import PeerModeSettings, PeerRecord

logger = help.ogler.getLogger(__name__)


def make_hoa_oobi_source():
    root = egf_local_dir()
    return LocalDirOobiSource(root) if root is not None else None


def direct_authorities(egf_doc, accept_phases):
    out, seen = [], set()
    for auth in egf_doc.all_authorities(accept_phases=accept_phases):
        if auth.aid in seen:
            continue
        for ep in auth.endpoints:
            if ep.mode == "direct":
                seen.add(auth.aid)
                out.append((auth, ep))
                break
    return out


def ensure_direct_transport(app, egf_doc, oobi_source, accept_phases) -> bool:
    """Bring up direct-mode peer transport for the onboarding vault.

    Returns True once bring-up has been attempted (listener enabled, AID
    exposed, authorities paired) OR there was nothing to do; returns False
    ONLY when it deferred because the default identifier does not exist
    yet — the first-run case where inception runs asynchronously on the
    vault's Doist (``create_identifier`` schedules an ``InceptDoer`` and
    returns before the hab appears). The caller retries on that False so
    transport comes up the moment the AID lands, rather than never (the
    per-vault wiring guard otherwise runs this exactly once). Idempotent:
    already-enabled settings and already-paired authorities are skipped."""
    targets = direct_authorities(egf_doc, accept_phases)
    if not targets:
        return True
    vault = app.vault

    # (0) default identifier -- resolved FIRST: no listener without an
    # identity to expose. Mirrors RequestFlow._default_hab's convention
    # (brand().default_aid_alias), falling back to "whatever hab exists"
    # for reference-brand/dev builds that haven't set an alias, then to
    # "no identifiers yet" -- never raise out of vault open.
    alias = brand().default_aid_alias
    hab = vault.hby.habByName(alias) if alias else None
    if hab is None:
        hab = next(iter(vault.hby.habs.values()), None)
    if hab is None:
        logger.warning("direct_transport.no_hab vault has no identifiers yet")
        return False

    # (1) listener
    settings = vault.db.peerSettings.get(keys=("default",))
    if settings is None or not settings.enabled:
        settings = PeerModeSettings(
            enabled=True,
            port=(settings.port if settings else find_free_port(start=5622)),
            advertised_host="127.0.0.1",
            open_inbound=settings.open_inbound if settings else False,
        )
        vault.db.peerSettings.pin(keys=("default",), val=settings)
    vault.restart_peer_mode()

    # (2) expose + publish the default AID's peer role
    if hab.pre not in vault._peer_exposed_aids:
        vault._peer_exposed_aids.add(hab.pre)
        url = f"tcp://{settings.advertised_host or '127.0.0.1'}:{settings.port}"
        vault.extend([PublishPeerRoleDoer(
            vault.hby, hab, url, signal_bridge=vault.signals, allow=True)])

    # (3) pair each direct authority from the bundled artifact
    allowlist = PeerAllowlist(vault.db)
    for auth, ep in targets:
        if allowlist.get(auth.aid) is not None:
            continue
        try:
            cesr = oobi_source.fetch(ep.oobi_ref or auth.aid)
            parse_oobi_cesr(vault.hby, cesr)
        except (EgfError, PeerBlobError) as e:
            logger.error(f"direct_transport.pair_failed aid={auth.aid} err={e}")
            vault.signals.emit_doer_event(
                "DirectTransport", "transport_failed",
                {"message": f"Couldn't pair {auth.display_name}: {e}"})
            continue
        loc = vault.hby.db.locs.get(keys=(auth.aid, kering.Schemes.tcp))
        allowlist.add(PeerRecord(
            aid=auth.aid, label=auth.display_name,
            endpoint_url=loc.url if loc else ""))
        logger.info(f"direct_transport.paired aid={auth.aid}")
    return True
