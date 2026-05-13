# -*- encoding: utf-8 -*-
"""Stable page-key constants for the Designer plugin.

These keys are registered into VaultPage.content_stack and used to
navigate between Designer surfaces. Keeping them in a single module
avoids string drift across pages, plugin lifecycle, and tests.
"""
from __future__ import annotations

PAGE_KEY_TEMPLATES_BROWSER = "designer.templates"
PAGE_KEY_OVERVIEW = "designer.overview"
PAGE_KEY_COMMANDS = "designer.commands"
PAGE_KEY_AGGREGATES = "designer.aggregates"
PAGE_KEY_REACTIONS = "designer.reactions"
PAGE_KEY_WORKFLOWS = "designer.workflows"
PAGE_KEY_PROJECTIONS = "designer.projections"
PAGE_KEY_RULES = "designer.rules"
PAGE_KEY_IMPORTS = "designer.imports"
PAGE_KEY_EXPORTS = "designer.exports"

ALL_PAGE_KEYS: tuple[str, ...] = (
    PAGE_KEY_TEMPLATES_BROWSER,
    PAGE_KEY_OVERVIEW,
    PAGE_KEY_COMMANDS,
    PAGE_KEY_AGGREGATES,
    PAGE_KEY_REACTIONS,
    PAGE_KEY_WORKFLOWS,
    PAGE_KEY_PROJECTIONS,
    PAGE_KEY_RULES,
    PAGE_KEY_IMPORTS,
    PAGE_KEY_EXPORTS,
)

PRIMITIVE_PAGE_KEY: dict[str, str] = {
    "commands": PAGE_KEY_COMMANDS,
    "aggregates": PAGE_KEY_AGGREGATES,
    "reactions": PAGE_KEY_REACTIONS,
    "workflows": PAGE_KEY_WORKFLOWS,
    "projections": PAGE_KEY_PROJECTIONS,
    "rules": PAGE_KEY_RULES,
    "imports": PAGE_KEY_IMPORTS,
    "exports": PAGE_KEY_EXPORTS,
}
