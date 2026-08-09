# -*- encoding: utf-8 -*-
"""Every user-visible string on the mandate form.

Produced by three independent drafts judged against the brand voice pillars
("Established and self-assured, never flashy") and `ux-patterns.md` §11: error text
is specific and actionable, never "Invalid input."; help text carries format hints;
sentence case throughout.

The verb at the commit point is SIGN, deliberately, while the page H1 stays
"Declare a product mandate" -- the page is named for the act, the button for the
commitment. That is an owner decision (design spec §5.1); do not "fix" it into one
vocabulary.
"""
from __future__ import annotations

TOKENS = frozenset({
    "code", "cuo_name", "line_of_business", "jurisdiction",
    "existing_opens", "existing_closes", "said",
})

#: Field sequence for the form AND for error reporting. Deliberately NOT read from
#: the schema. Measured during execution: the bundled template's
#: `payload_schema.properties` block is ALPHABETIZED, and while its `required` array
#: happens to carry the authored order, `required` is a JSON-Schema *set* -- nothing
#: distinguishes "authored order" from "incidentally alphabetical", and something has
#: already alphabetized `properties` in that very file. Presentation order is a UI
#: decision; keeping it here means a re-serialized schema cannot silently reorder the
#: form. `MandateSchema.order` remains a canary, not an authority.
FIELD_ORDER = (
    "line_of_business", "jurisdiction", "coverages",
    "window_opens", "window_closes", "thesis",
)

H1 = "Declare a product mandate"

PAGE_INTRO = (
    "Submitting signs this mandate with your chief underwriting authority and "
    "adds it permanently to your own published record.",
    "You are publishing, not filing: nothing here can be edited afterwards, and "
    "anyone who asks reads all of it, your thesis word for word.",
)

FIELD_LABEL = {
    "line_of_business": "Line of business",
    "jurisdiction": "Jurisdiction",
    "coverages": "Coverages",
    "window_opens": "In force from",
    "window_closes": "In force through",
    "thesis": "Thesis",
}

FIELD_HELP = {
    "line_of_business": "One line per mandate. A second line is a second mandate.",
    "jurisdiction": (
        "Format US-UT, one jurisdiction per mandate. Only the format is checked; "
        "the app cannot tell US-UT from US-TU, so read your code back before you "
        "sign."),
    # The parenthesised examples used to read as the allowed set -- the first CUO
    # to see this screen went looking for the autocomplete. There is no allowed
    # set: the payload schema puts no `enum` on `coverages.items`, only the shape
    # `^[A-Z0-9][A-Z0-9-]*$`, and its own description says the coverages are
    # declared "in her own language". So the copy has to say so out loud.
    "coverages": (
        "At least one code, uppercase, no repeats — for example BI, PD or COMP. "
        "There is no fixed list: these are the coverages you are declaring, in "
        "your own words, and they publish exactly as written."),
    "window_opens": (
        "Both dates count as in force. In force through must fall after in force "
        "from, so the shortest window is two days."),
    "window_closes": (
        "Both dates count as in force. In force through must fall after in force "
        "from, so the shortest window is two days."),
    "thesis": (
        "One sentence of business intent, in your own words. It publishes "
        "verbatim, so write it for a reader outside the company."),
}

FIELD_PLACEHOLDER = {
    "line_of_business": "Choose a line of business",
    "jurisdiction": "US-UT",
    "coverages": "BI",
    "window_opens": "MM/DD/YYYY",
    "window_closes": "MM/DD/YYYY",
    "thesis": "One sentence of business intent",
}

#: A LABEL, not a placeholder, for the entry box inside a list control.
#:
#: `LocksmithTextListWidget` is built on `FloatingLabelLineEdit`, whose own
#: docstring says the text "animates up to become an inline label when focused or
#: filled". Feeding it `FIELD_PLACEHOLDER["coverages"]` therefore promoted the
#: EXAMPLE VALUE "BI" to the field's permanent name: at rest the box read "BI",
#: and on focus "BI" floated into the border notch beside the real "Coverages *"
#: label above it. Measured on the live app -- it reads as either "this field is
#: called BI" or "BI is already entered", and it is why the first CUO to use the
#: screen went looking for an autocomplete.
#:
#: A placeholder is an example of the VALUE and disappears on typing; a floating
#: label is the field's NAME and persists. They are not interchangeable, and this
#: is the only control in the form that takes the second kind. The outer label
#: names the list, this one names one entry to add -- which is also what makes
#: the neighbouring "+" button legible.
FIELD_ENTRY_LABEL = {
    "coverages": "Coverage code",
}

FORM_PRIMARY = "Review mandate"
FORM_CANCEL = "Cancel"
IN_FLIGHT = "Signing…"

#: The declared state. The SAID appears in FULL, never truncated: it is the
#: handle a reader uses to fetch the mandate, and half of one is no handle.
DECLARED = "Mandate declared. {said}"
DECLARED_COPY = "Copy the mandate SAID"

#: Reaches the CUO through `REVIEW_SIGNER` when no identifier can be resolved.
#: The `cuo_role` credential carries protocol fields only, so no personal name
#: exists anywhere in the ecosystem to read; the signer is normally named by
#: their identifier's own local alias.
UNNAMED_SIGNER = "this identifier"

REVIEW_TITLE = "Review this mandate before signing"
REVIEW_SIGNER = (
    "Signing as {cuo_name}, Chief Underwriting Officer, on the authority granted "
    "to you by Usurance administration.")
REVIEW_CAUTION = (
    "Signing is final. These values can never be edited, and the whole mandate, "
    "thesis included, goes to anyone who asks for it. To correct a mandate, "
    "declare a new one. Withdrawing later records that you stopped pursuing it "
    "and leaves what you declared readable.")
REVIEW_CONFIRM = "Sign mandate"
REVIEW_BACK = "Keep editing"
REVIEW_IN_FORCE_LABEL = "In force"
REVIEW_THESIS_LABEL = "Thesis, published in full"

JURISDICTION_PATTERN = (
    "Jurisdiction must be US, a dash, then two uppercase letters. Enter it like "
    "US-UT.")
COVERAGE_PATTERN = (
    "Coverage code {code} must use capital letters, digits and hyphens only, "
    "starting with a letter or digit, as in BI or COMP-EXT. Retype it in that "
    "form.")
COVERAGE_DUPLICATE = (
    "{code} is listed twice. Remove the second entry; each coverage is named "
    "once.")
WINDOW_ORDER = (
    "In force through must fall after in force from, and a window of a single "
    "day is not accepted. Move in force through to a later date.")
WINDOW_OVERLAP = (
    "You already have a mandate for {line_of_business} in {jurisdiction} in "
    "force {existing_opens} through {existing_closes}. Withdraw that mandate or "
    "set this window to start after it closes.")

#: Public, user-visible copy -- the form renders these directly to the CUO when a
#: required field is empty. Deliberately NOT underscore-prefixed: an earlier draft
#: named this `_REQUIRED`, which hid it from every policy test in this module (they
#: all skip underscore-prefixed attributes) and let a forbidden word slip through
#: undetected. See `test_the_forbidden_word_scan_actually_reaches_the_required_messages`.
REQUIRED = {
    "line_of_business": "Choose a line of business.",
    "jurisdiction": "Enter a jurisdiction, like US-UT.",
    "coverages": "Add at least one coverage code.",
    "window_opens": "Enter the date this mandate comes into force.",
    "window_closes": "Enter the last date this mandate is in force.",
    "thesis": "Write one sentence of business intent.",
}


def error_summary(count: int) -> str:
    """The submit-time banner. Counts correctly at one.

    Every draft of this copy shipped "Fix 1 errors before signing.", and so does
    the spec's own example string, so the pluralisation lives here rather than in
    a format call at the call site.
    """
    if not isinstance(count, int) or count < 1:
        raise ValueError(f"error_summary is for 1 or more errors, got {count!r}")
    noun = "error" if count == 1 else "errors"
    return f"Fix {count} {noun} before signing."


def required_error(field: str) -> str:
    return REQUIRED.get(field, f"{FIELD_LABEL.get(field, field)} is required.")


def enum_error(field: str, value: str, allowed: tuple[str, ...]) -> str:
    label = FIELD_LABEL.get(field, field).lower()
    return (f"{value} is not one of the available options for {label}. "
            f"Choose from {', '.join(allowed)}.")


def pattern_error(field: str) -> str:
    if field == "jurisdiction":
        return JURISDICTION_PATTERN
    return f"{FIELD_LABEL.get(field, field)} is not in the required format."


def date_error(field: str) -> str:
    return f"Enter {FIELD_LABEL.get(field, field).lower()} as a date."
