# -*- encoding: utf-8 -*-
"""Interaction dialog for group identifiers.

This module reuses the shared interaction dialog base for group habitats so a
user can create an interaction event with arbitrary JSON payload.
"""
from locksmith.ui.vault.shared.interact_base import BaseInteractDialog


class GroupInteractDialog(BaseInteractDialog):
    """Group-specific wrapper around the shared interaction dialog base."""
