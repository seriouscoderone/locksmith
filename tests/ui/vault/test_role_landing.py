"""Where a HOA vault opens, and why.

The rule: a pinned page if one is set and registered; else the ONE active role
surface when exactly one is revealed; else "home"; else "settings". Nothing is
ever written on the user's behalf.

Every case here is resolved the way the app resolves it -- `default_page_key()`
filters `preferred_default_page_keys()` down to keys that are actually
REGISTERED. That filter is the whole safety net: a pin naming a role whose
credential was revoked degrades on its own and can never reach `_show_page`'s
"No page registered" error.
"""
from types import SimpleNamespace

import pytest

from locksmith.db.basing import LandingPrefs
from locksmith.ui.vault.hoa_page import HoaVaultPage


class _Landing:
    """The per-vault Komer, in memory. Same get/pin shape as `db.landing`."""

    def __init__(self, pinned=""):
        self._prefs = LandingPrefs(pinned_page_key=pinned)

    def get(self, keys=None):
        return self._prefs

    def pin(self, keys=None, val=None):
        self._prefs = val


def _page(pinned="", active=(), registered=("home", "settings"), landing=None):
    """A HoaVaultPage with only the collaborators the landing decision reads.

    `__new__`, deliberately: constructing one needs a window, a nav menu and a
    live vault, none of which the resolution touches. What is exercised here is
    the real method on the real class, not a reimplementation.
    """
    page = HoaVaultPage.__new__(HoaVaultPage)
    landing = landing if landing is not None else _Landing(pinned)
    page.app = SimpleNamespace(
        vault=SimpleNamespace(db=SimpleNamespace(landing=landing)),
        plugin_manager=SimpleNamespace(active_role_page_keys=lambda: list(active)))
    page._pages = {key: object() for key in registered}
    return page


def _lands_on(page):
    return page.default_page_key()


def test_no_roles_lands_on_the_roles_overview():
    """The first-run state: a real person has not granted anything yet."""
    assert _lands_on(_page()) == "home"


def test_a_single_role_opens_straight_into_it():
    """The owner's rule, and the case it is exactly right for."""
    page = _page(active=("cuo",), registered=("home", "settings", "cuo"))
    assert _lands_on(page) == "cuo"


def test_a_single_role_is_derived_never_written():
    """No pin is created behind the user's back. Auto-pinning would be a
    lock-in they never chose and would then have to discover to undo."""
    landing = _Landing()
    page = _page(active=("cuo",), registered=("home", "settings", "cuo"),
                 landing=landing)
    _lands_on(page)
    assert landing.get().pinned_page_key == ""


def test_several_roles_with_no_pin_land_on_the_overview():
    """Deliberately NOT a guess. The owner's rule is undefined for several
    roles, and the overview is where the control to choose one lives."""
    page = _page(active=("cuo", "actuary"),
                 registered=("home", "settings", "cuo", "actuary"))
    assert _lands_on(page) == "home"


def test_a_pin_wins_over_everything_registered():
    page = _page(pinned="actuary", active=("cuo", "actuary"),
                 registered=("home", "settings", "cuo", "actuary"))
    assert _lands_on(page) == "actuary"


def test_a_pin_naming_a_revoked_role_falls_through_to_the_survivor():
    """The revocation case, and the reason resolution is registered-only. The
    pinned page is simply not in the registry once its gate flips."""
    page = _page(pinned="actuary", active=("cuo",),
                 registered=("home", "settings", "cuo"))
    assert _lands_on(page) == "cuo"


def test_a_pin_survives_revocation_rather_than_being_cleared():
    """Revoke -> re-grant is a real arc. Forgetting the choice would make the
    re-grant a mystery, so the record is kept and simply does not apply."""
    landing = _Landing("actuary")
    page = _page(active=(), registered=("home", "settings"), landing=landing)
    assert _lands_on(page) == "home"
    assert landing.get().pinned_page_key == "actuary"


def test_every_role_revoked_lands_on_the_overview():
    page = _page(pinned="actuary", active=(), registered=("home", "settings"))
    assert _lands_on(page) == "home"


def test_with_no_home_page_it_lands_on_settings_not_nowhere():
    """A brand with onboarding off registers no "home". `settings` is the one
    page `_register_core_pages` always registers, so there is always a real
    destination and never a blind route."""
    page = _page(pinned="actuary", active=(), registered=("settings",))
    assert _lands_on(page) == "settings"


def test_it_never_offers_identifiers():
    """The stock wallet default, which a peeled HOA never registers -- the
    source of the measured "No page registered for key 'identifiers'"."""
    page = _page(active=("cuo",), registered=("home", "settings", "cuo"))
    assert "identifiers" not in page.preferred_default_page_keys()


def test_the_preference_is_read_fresh_for_every_vault():
    """One VaultPage instance is constructed at window build and shared across
    every vault opened in the process, so a cached read would carry one vault's
    choice into the next."""
    page = _page(pinned="actuary", active=(),
                 registered=("home", "settings", "actuary"))
    assert _lands_on(page) == "actuary"
    page.app.vault.db.landing = _Landing("")          # a different vault opens
    assert _lands_on(page) == "home"


def test_a_vault_less_page_resolves_without_raising():
    """The Roles surface is constructed before any vault exists."""
    page = HoaVaultPage.__new__(HoaVaultPage)
    page.app = SimpleNamespace(vault=None, plugin_manager=None)
    page._pages = {"home": object(), "settings": object()}
    assert page.pinned_landing_key() is None
    assert _lands_on(page) == "home"


@pytest.mark.parametrize("broken", ["raises", "missing"])
def test_an_unreadable_role_set_still_lands_somewhere(broken):
    """A landing hint must never be able to stop the vault opening."""
    def boom():
        raise RuntimeError("gates unavailable")

    manager = SimpleNamespace(active_role_page_keys=boom) if broken == "raises" \
        else SimpleNamespace()
    page = _page()
    page.app.plugin_manager = manager
    assert _lands_on(page) == "home"
