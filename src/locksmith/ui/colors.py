# -*- encoding: utf-8 -*-
"""
locksmith.ui.colors module

Centralized color definitions for the Locksmith UI.
All colors used throughout the application should be defined here
to ensure consistency and easy theming/modifications.
"""

# =============================================================================
# Primary Brand Colors
# =============================================================================
PRIMARY = "#F57B03"  # Orange - main brand color
PRIMARY_HOVER = "#D66A02"  # Darker orange for hover states
PRIMARY_PRESSED = "#E67E00"  # Orange for pressed states

# =============================================================================
# Background Colors
# =============================================================================
BACKGROUND_WINDOW = "#F2F3FA"  # Main window background
BACKGROUND_CONTENT = "#F8F9FF"  # Content area/dialog background
BACKGROUND_HOVER = "#F5F5F5"  # Hover background for interactive elements
BACKGROUND_NEUTRAL = "#E0E0E0"  # Neutral gray background
BACKGROUND_NEUTRAL_HOVER = "#D0D0D0"  # Neutral gray hover
BACKGROUND_COLLAPSIBLE_HOVER = "#DFE0E6"  # Collapsible section hover
BACKGROUND_DISABLED = "#EEEEEE"  # Disabled button background

# Selection/Highlight backgrounds
BACKGROUND_SELECTION = "#E8E9F0"  # Selection background
BACKGROUND_HIGHLIGHT = "#DCDDE5"  # Highlight/hover in lists

# Table backgrounds
BACKGROUND_TABLE_HEADER = "#EEEFF5"  # Table header background
BACKGROUND_TABLE_ROW_HOVER = "#E0F2F1"  # Row hover (teal tint)
BACKGROUND_TABLE_ROW_SELECTED = "#D4EBE9"  # Row selected
BACKGROUND_TABLE_ROW_PRESSED = "#C8E6E4"  # Row pressed

# Success/Error/Danger backgrounds
BACKGROUND_ERROR = "#FFEBEE"  # Light red background for errors
BACKGROUND_SUCCESS = "#E8F5E9"  # Light green background for success
BACKGROUND_DANGER = "#FEF2F2"  # Danger zone background
BACKGROUND_DANGER_BORDER = "#FECACA"  # Danger zone border

# =============================================================================
# Text Colors
# =============================================================================
TEXT_PRIMARY = "#2D2F33"  # Dark text - main text color
TEXT_DARK = "#1A1C20"  # Very dark text for emphasis
TEXT_SECONDARY = "#6E7074"  # Gray text for secondary information
TEXT_MUTED = "#888888"  # Muted text for placeholders/disabled
TEXT_SUBTLE = "#666666"  # Subtle gray text
TEXT_MENU = "#333333"  # Menu text color
TEXT_MONOSPACE_SECONDARY = "#6B7280"  # Monospace text secondary

# =============================================================================
# Border & Divider Colors
# =============================================================================
BORDER = "#D0D5DD"  # Standard border color
BORDER_NEUTRAL = "#CCCCCC"  # Neutral gray border
BORDER_DARK = "#757575"  # Dark border
BORDER_TABLE = "#E5E7EB"  # Table borders
BORDER_FOCUS = "#9CA3AF"  # Focus ring border
DIVIDER = "#E8E8E8"  # Divider lines

# =============================================================================
# Interactive Element Colors
# =============================================================================
RADIO_BUTTON = "#43474E"  # Radio button/checkbox indicator color

# Scrollbar
SCROLLBAR_HANDLE_HOVER = "#A0A0A0"  # Scrollbar handle on hover

# Toggle Switch
TOGGLE_TRACK_OFF = "#E6E6E6"  # Toggle track when off
TOGGLE_TRACK_ON = "#2C3E50"  # Toggle track when on (dark blue-grey)
TOGGLE_THUMB = "#D3544E"  # Toggle thumb (reddish-orange)

# Blue accent (for settings/forms)
BLUE_ACCENT = "#3B82F6"  # Blue accent color
BLUE_BORDER = "#007AFF"  # Blue border for focus

# Selection/Active state blue (Material Design Blue 500)
BLUE_SELECTION = "#2196F3"  # Blue for selection borders and active states
BLUE_SELECTION_BG = "#E3F2FD"  # Light blue background for selections

# =============================================================================
# Status Colors
# =============================================================================
# Danger/Error reds (Tailwind scale)
DANGER = "#DC2626"  # Tailwind red-600 (base danger/delete)
DANGER_HOVER = "#B91C1C"  # Tailwind red-700
DANGER_PRESSED = "#991B1B"  # Tailwind red-800
DANGER_LIGHT = "#F87171"  # Tailwind red-400 (disabled danger)

# Success greens
SUCCESS = "#4CAF50"  # Success green (Material)
SUCCESS_TEXT = "#2E7D32"  # Success text (dark green)
SUCCESS_INDICATOR = "#16A34A"  # Tailwind green-600 (authenticated)

# Warning orange
WARNING_TEXT = "#C2410C"  # Orange-800 for warning text
WARNING_BUTTON = "#EA580C"  # Orange-600 for warning buttons

# Warning yellow
WARNING_YELLOW = "#FFC107"

# The caution-block pair. Named here rather than left as literals because
# `LocksmithDialog._build_warning_banner` already ships exactly these two values
# hardcoded (the only hardcoded colours in that file), and a second consumer was
# about to paste them a second time.
BACKGROUND_WARNING = "#FEF3C7"  # Amber-100 warning fill
WARNING_BORDER = "#F59E0B"      # Amber-500 warning accent/left rule

# =============================================================================
# Contrast Colors
# =============================================================================
WHITE = "#FFFFFF"
BLACK = "#000000"

# =============================================================================
# Toolbar Colors
# =============================================================================
TOOLBAR_DARK = "#1A252C"  # Dark toolbar button background


# =============================================================================
# Primary button fill — separate from PRIMARY on purpose
# =============================================================================
# PRIMARY is the brand accent: links, focus rings, avatars, badges, selection.
# It is judged against the page, where it only has to clear 3:1 as a graphical
# object. A FILLED BUTTON is different -- it carries white label text, so it has
# to clear 4.5:1 as normal text, and no accent bright enough to work as an accent
# also clears that. Measured: white on Usurance Teal 600 #2AABB3 is 2.77:1 and
# white on vanilla orange #F57B03 is 2.72:1 -- both fail, in both brands.
#
# This is a contradiction in the suite, not a defect in either brand:
# design-system.md:218 mandates "Primary = Teal 600 filled, White text" while
# :296-300 mandates 4.5:1 for normal text and 3:1 even for large buttons, so the
# mandated pairing fails the mandated floor. Splitting the token is how both
# rules can hold at once -- the accent stays the accent, and the button fill is
# darkened until white is legible on it.
#
# Defaults preserve today's appearance exactly. `apply_theme_overrides` falls
# these back to the brand's own PRIMARY when a brand does not opt in, so a brand
# that sets `primary` alone never inherits another brand's button colour.
PRIMARY_BUTTON = "#F57B03"          # Filled-primary background
PRIMARY_BUTTON_HOVER = "#D66A02"    # ...darker on hover
PRIMARY_BUTTON_PRESSED = "#E67E00"  # ...and on press


# =============================================================================
# Per-brand theme overrides
# =============================================================================
# Maps brand.toml [theme] keys → the module-level accent constants above. Only
# the accent set is brandable; neutrals and semantic (danger/success) colors are
# shared across all brands. Called once at startup BEFORE the QSS is built.
_THEME_KEY_TO_CONST = {
    "primary": "PRIMARY",
    "primary_hover": "PRIMARY_HOVER",
    "primary_pressed": "PRIMARY_PRESSED",
    "primary_button": "PRIMARY_BUTTON",
    "primary_button_hover": "PRIMARY_BUTTON_HOVER",
    "primary_button_pressed": "PRIMARY_BUTTON_PRESSED",
    "toolbar_dark": "TOOLBAR_DARK",
}

#: Button fills fall back to the brand's own accent, NOT to the module default.
#: Without this a brand that overrides `primary` and nothing else would keep the
#: vanilla orange button fill -- the module default is orange, so the fallback
#: has to be computed after the overrides land, not before.
_BUTTON_FALLBACKS = {
    "PRIMARY_BUTTON": "PRIMARY",
    "PRIMARY_BUTTON_HOVER": "PRIMARY_HOVER",
    "PRIMARY_BUTTON_PRESSED": "PRIMARY_PRESSED",
}


def apply_theme_overrides(theme: dict) -> None:
    """Overwrite the accent constants from a brand's theme dict (in place)."""
    g = globals()
    for key, const_name in _THEME_KEY_TO_CONST.items():
        value = theme.get(key)
        if value:
            g[const_name] = value
    # Then the button fills, for any brand that did not name them. Computed
    # AFTER the loop so the fallback is this brand's accent rather than the
    # module default -- otherwise a brand overriding `primary` alone would keep
    # the vanilla orange button fill.
    for const_name, accent_name in _BUTTON_FALLBACKS.items():
        theme_key = next(k for k, v in _THEME_KEY_TO_CONST.items() if v == const_name)
        if not theme.get(theme_key):
            g[const_name] = g[accent_name]
