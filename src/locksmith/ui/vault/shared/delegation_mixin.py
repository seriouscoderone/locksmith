# -*- encoding: utf-8 -*-
"""
locksmith.ui.vault.shared.delegation_mixin module

Shared mixin for delegation radio button handling in create dialogs.
"""
from keri import help

from locksmith.core import habbing

logger = help.ogler.getLogger(__name__)


class DelegationMixin:
    """
    Mixin providing shared delegation radio button handlers.

    Subclasses must provide:
        - self.app: LocksmithApplication instance
        - self.no_delegation_radio: LocksmithRadioButton
        - self.local_delegation_radio: LocksmithRadioButton
        - self.remote_delegation_radio: LocksmithRadioButton
        - self.delegator_dropdown: FloatingLabelComboBox
        - self.delegate_proxy_dropdown: FloatingLabelComboBox
    """

    def _on_delegation_radio_changed(self):
        """Handle delegation radio button selection changes."""
        if self.no_delegation_radio.isChecked():
            self.delegator_dropdown.hide()
            self.delegate_proxy_dropdown.hide()
        elif self.local_delegation_radio.isChecked():
            self._populate_delegator_dropdown('local')
            self.delegator_dropdown.show()
            self.delegate_proxy_dropdown.hide()
        elif self.remote_delegation_radio.isChecked():
            self._populate_delegator_dropdown('remote')
            self._populate_proxy_dropdown()
            self.delegator_dropdown.show()
            self.delegate_proxy_dropdown.show()

        # Update collapsible section height if present
        if hasattr(self, 'advanced_config'):
            self.advanced_config.update_content_height()

    def _populate_delegator_dropdown(self, delegation_type: str):
        """Populate the delegator dropdown based on delegation type."""
        self.delegator_dropdown.clear()
        self.delegator_dropdown.addItem("None")

        delegators = habbing.load_potential_delegators(self.app, delegation_type)
        for d in delegators:
            display_text = f"{d['alias']}" if d['alias'] else f"{d['id'][:12]}..."
            self.delegator_dropdown.addItem(display_text, d['id'])

    def _populate_proxy_dropdown(self):
        """Populate the proxy dropdown with local identifiers."""
        self.delegate_proxy_dropdown.clear()
        self.delegate_proxy_dropdown.addItem("None")

        proxies = habbing.load_potential_proxies(self.app)
        for p in proxies:
            display_text = p['alias']
            self.delegate_proxy_dropdown.addItem(display_text, p['alias'])
