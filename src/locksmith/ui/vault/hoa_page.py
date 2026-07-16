# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.hoa_page module

VaultPage variant for an HOA (Higher-Order Application) shell: peel-light.

Keeps VaultPage's string-keyed page registry, plugin surface, and navigation
wiring intact, but does NOT register the built-in wallet pages (identifiers,
credentials, groups, remotes, settings, notifications). This is a subtractive
peel — nothing in VaultPage is deleted or altered, so upstream Locksmith
merges stay clean. Selection between VaultPage and HoaVaultPage happens at
the call site (locksmith.ui.window) based on ``brand().peel_core_pages``.
"""
from locksmith.ui.vault.page import VaultPage


class HoaVaultPage(VaultPage):
    """VaultPage for an HOA shell.

    Overrides ``_register_core_pages()`` to a no-op so none of the built-in
    wallet pages are registered, while the ``_pages`` registry and
    ``register_page()`` remain fully functional for plugin-contributed pages.
    """

    def _register_core_pages(self) -> None:
        """Suppress registration of the built-in wallet pages."""
        return

    def registered_page_keys(self) -> list[str]:
        """Expose the current page-registry keys (for tests/inspection)."""
        return list(self._pages.keys())
