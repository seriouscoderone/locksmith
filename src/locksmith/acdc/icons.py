# -*- encoding: utf-8 -*-
"""
locksmith.acdc.icons module

Resource paths for the ecosystem-viewer plugin's visual vocabulary.

Each constant maps a domain concept (or reused common UI affordance) to a
Qt resource path under `:/assets/material-icons/`. Code that renders ACDC
schemas, credentials, or relationships should import these constants
rather than hard-coding paths, so the visual vocabulary stays consistent
and the asset set stays discoverable.

Citations to the design doc are by section number; see
`docs/superpowers/designs/2026-05-06-ecosystem-viewer-redesign.md` for
the rationale behind each metaphor.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Privacy — public vs private credential (§2.1)
# ---------------------------------------------------------------------------

ICON_PRIVACY_PUBLIC = ":/assets/material-icons/privacy_public.svg"
"""Open thin-stroke circle. Public credential (no `u` nonce); SAID is
correlatable across presentations."""

ICON_PRIVACY_PRIVATE = ":/assets/material-icons/privacy_private.svg"
"""Hatched-fill circle. Private credential (`u` UUID/nonce present);
non-correlatable across presentations."""


# ---------------------------------------------------------------------------
# Targeting — targeted vs untargeted (§2.2)
# ---------------------------------------------------------------------------

ICON_TARGETING_TARGETED = ":/assets/material-icons/targeting_targeted.svg"
"""Two overlapping silhouettes. Targeted credential — commits to a
specific issuee AID via `a.i`."""

ICON_TARGETING_UNTARGETED = ":/assets/material-icons/targeting_untargeted.svg"
"""One silhouette with broadcast waves. Untargeted credential —
public attestation with no committed issuee."""


# ---------------------------------------------------------------------------
# Schema identity (§2.7)
# ---------------------------------------------------------------------------

ICON_SAID_FINGERPRINT = ":/assets/material-icons/said_fingerprint.svg"
"""Concentric-arc rangefinder. Indicates a content-addressed identity
(a SAID); used inline beside SAID values."""


# ---------------------------------------------------------------------------
# Issuer (§2.8)
# ---------------------------------------------------------------------------

ICON_ISSUER_SIGIL = ":/assets/material-icons/issuer_sigil.svg"
"""6-spoke asterisk. KERI-flavored sigil for issuer-AID circles in the
graph view and issuer cards on the overview."""


# ---------------------------------------------------------------------------
# Ecosystem (§3.2)
# ---------------------------------------------------------------------------

ICON_ECOSYSTEM = ":/assets/material-icons/hub.svg"
"""Hub glyph (a node with spokes). Canonical icon for "ecosystem"
across the entire wallet — overview tiles, section headers, the
plugin's menu entry, anywhere an ecosystem is identified visually."""


# ---------------------------------------------------------------------------
# Graph canvas controls (§5.8)
# ---------------------------------------------------------------------------

ICON_FIT_TO_CONTENT = ":/assets/material-icons/fit_to_content.svg"
"""Four corner brackets. Fits the graph view to its content extent."""

ICON_UNRESOLVED = ":/assets/material-icons/unresolved.svg"
"""Question mark inside a dashed circle. Placeholder for schemas/AIDs
that an edge or membership references but that aren't resolved into
this wallet yet."""


# ---------------------------------------------------------------------------
# Reused from existing material-icons set (§7.16-7.21)
# ---------------------------------------------------------------------------

ICON_DEVELOPER_MODE = ":/assets/material-icons/tune.svg"
"""Reused tune.svg. Developer-details disclosure toggle (§4.6)."""

ICON_COPY = ":/assets/material-icons/content_copy.svg"
"""Reused content_copy.svg. Copy SAID/AID to clipboard."""

ICON_BACK_ARROW = ":/assets/material-icons/chevron_left.svg"
"""Reused chevron_left.svg. Page back button."""

ICON_ADD_PLUS = ":/assets/material-icons/add.svg"
"""Reused add.svg. Create-ecosystem CTA, add-member affordance."""

ICON_RELAYOUT = ":/assets/material-icons/refresh.svg"
"""Reused refresh.svg. Trigger graph relayout in the ecosystem view."""
