"""The "set as default" affordance on a role card.

The first build put an "Open at startup" CHECKBOX beside Open, and the owner
read the affordance as absent: a small box riding a button row does not announce
what it does, and the SET state was invisible until you noticed a tick. It is now
a named action plus a badge the card wears.
"""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from locksmith.ui.onboarding.home_page import RoleCard, RoleStatus


def _role(role_id="product_designer"):
    return SimpleNamespace(id=role_id, kind="persona",
                           display_name="Insurance Product Designer",
                           description="Turns attested pieces into a product.",
                           onboarding=None)


def _card(qtbot, status=RoleStatus.ACTIVE, page_available=True, is_default=False):
    card = RoleCard(_role(), status, page_available=page_available,
                    opens_at_startup=is_default)
    qtbot.addWidget(card)
    return card


def test_an_active_role_offers_a_named_action_not_a_bare_box(qtbot):
    card = _card(qtbot)
    button = card.findChild(QPushButton, "roleCard.defaultButton.product_designer")
    assert button is not None, "no way to set a default on an active role"
    assert button.text() == "Set as default"


def test_the_card_wears_a_badge_when_it_is_the_default(qtbot):
    """The state has to be readable at a glance, not by inspecting a control."""
    plain = _card(qtbot, is_default=False)
    assert plain.findChild(QLabel, "roleCard.defaultBadge.product_designer") is None

    chosen = _card(qtbot, is_default=True)
    badge = chosen.findChild(QLabel, "roleCard.defaultBadge.product_designer")
    assert badge is not None and badge.text() == "DEFAULT"
    button = chosen.findChild(QPushButton, "roleCard.defaultButton.product_designer")
    assert button.text() == "Clear default", "no way back out of the choice"


@pytest.mark.parametrize("status,page_available,why", [
    (RoleStatus.AVAILABLE, False, "a role you do not hold"),
    (RoleStatus.PENDING, False, "a role you have only asked for"),
    (RoleStatus.REVOKED, False, "a role taken away from you"),
    (RoleStatus.ACTIVE, False, "held, but its page is not registered"),
])
def test_no_default_action_where_it_could_not_be_honoured(qtbot, status,
                                                          page_available, why):
    """Same two conditions as Open: ACTIVE and the page really registered.
    Pinning a surface you cannot open is a preference with nowhere to go -- and
    the landing resolver would silently skip it, so the card would be lying."""
    card = _card(qtbot, status=status, page_available=page_available)
    assert card.findChild(QPushButton,
                          "roleCard.defaultButton.product_designer") is None, why


def test_the_action_reports_which_role_and_which_direction(qtbot):
    card = _card(qtbot, is_default=False)
    seen = []
    card.default_toggled.connect(lambda rid, on: seen.append((rid, on)))
    card.findChild(QPushButton, "roleCard.defaultButton.product_designer").click()
    assert seen == [("product_designer", True)]

    already = _card(qtbot, is_default=True)
    undone = []
    already.default_toggled.connect(lambda rid, on: undone.append((rid, on)))
    already.findChild(QPushButton, "roleCard.defaultButton.product_designer").click()
    assert undone == [("product_designer", False)]


def test_the_open_button_is_addressable_per_role(qtbot):
    """Every card used to carry `roleCard.openButton`, so "open the actuary role"
    was unexpressible to a test or an accessibility client -- name lookup returns
    the first match. The same defect the REQUEST button's comment describes."""
    card = _card(qtbot)
    assert card.findChild(QPushButton, "roleCard.openButton.product_designer") \
        is not None
