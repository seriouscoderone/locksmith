"""Minimal Sphinx configuration for the first Locksmith documentation pass."""

from __future__ import annotations

import os
import sys


ROOT = os.path.abspath("..").replace("\\", "/")
SRC = os.path.join(ROOT, "src")

if SRC not in sys.path:
    sys.path.insert(0, SRC)


project = "Locksmith"
author = "KERI Foundation"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_mock_imports = [
    "PySide6",
    "keri",
    "hio",
    "qasync",
    "locksmith.ui.home",
    "locksmith.ui.navigation",
    "locksmith.ui.toolbar",
    "locksmith.ui.toolkit.tables",
    "locksmith.ui.toolkit.pages.base",
    "locksmith.ui.toolkit.widgets.buttons",
    "locksmith.ui.toolkit.widgets.toast",
    "locksmith.ui.vault.shared.base_list_page",
    "locksmith.ui.vault.credentials.issued.delete",
    "locksmith.ui.vault.credentials.issued.grant",
    "locksmith.ui.vault.credentials.issued.issue",
    "locksmith.ui.vault.credentials.issued.view",
    "locksmith.ui.vault.credentials.received.accept",
    "locksmith.ui.vault.credentials.received.delete",
    "locksmith.ui.vault.credentials.schema.add",
    "locksmith.ui.vault.credentials.schema.delete",
    "locksmith.ui.vault.credentials.schema.view",
    "locksmith.ui.vault.remotes.add",
    "locksmith.ui.vault.remotes.challenge",
    "locksmith.ui.vault.remotes.delete",
    "locksmith.ui.vault.remotes.filter",
    "locksmith.ui.vault.remotes.view",
    "locksmith.ui.vault.identifiers.list",
    "locksmith.ui.vault.notifications",
    "locksmith.ui.vault.shared.export",
    "locksmith.ui.vault.groups.authenticate",
    "locksmith.ui.vault.groups.create",
    "locksmith.ui.vault.groups.delete",
    "locksmith.core.grouping",
    "locksmith.ui.vault.groups.interact",
    "locksmith.ui.vault.groups.rotate",
    "locksmith.ui.vault.groups.view",
    "locksmith.ui.vault.settings.page",
    "locksmith.ui.vaults.drawer",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_theme = "alabaster"
