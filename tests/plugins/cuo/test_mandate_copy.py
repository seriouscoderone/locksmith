"""Copy is data, and it has a contract: no forbidden words, no unratified tokens,
and a summary that counts correctly at one.

The count-aware summary exists because every draft of this copy shipped
"Fix 1 errors before signing." -- the spec's own example string has the same bug.
"""
import re
import string

import pytest

from locksmith.plugins.cuo import mandate_copy as copy

_FORBIDDEN = ("please", "simply", "just ", "invalid input", "successfully")


def _all_strings():
    for name in dir(copy):
        if name.startswith("_"):
            continue
        value = getattr(copy, name)
        if isinstance(value, str):
            yield name, value
        elif isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str):
                    yield f"{name}[{key}]", item
        elif isinstance(value, tuple):
            for i, item in enumerate(value):
                if isinstance(item, str):
                    yield f"{name}[{i}]", item


def test_no_forbidden_word_appears_anywhere():
    for name, text in _all_strings():
        lowered = text.lower()
        for word in _FORBIDDEN:
            assert word not in lowered, f"{name} contains {word!r}: {text!r}"


def test_no_string_shouts():
    for name, text in _all_strings():
        assert "!" not in text, f"{name} uses an exclamation mark"


def test_every_interpolation_token_is_ratified():
    for name, text in _all_strings():
        used = {f for _, f, _, _ in string.Formatter().parse(text) if f}
        unknown = used - copy.TOKENS
        assert not unknown, (
            f"{name} uses unratified token(s) {unknown}; a token nobody fills "
            f"renders as literal braces")


def test_tokens_is_exactly_the_set_of_tokens_actually_used():
    """Ratification cuts both ways. An unratified token renders as literal braces in
    front of a user; a ratified-but-unused one is a claim about strings that do not
    exist, and it is how the set drifts out of step with the copy."""
    used = set()
    for _, text in _all_strings():
        used |= {f for _, f, _, _ in string.Formatter().parse(text) if f}
    assert used == copy.TOKENS, (
        f"unratified={used - copy.TOKENS}, ratified-but-unused={copy.TOKENS - used}")


def test_the_summary_counts_one_error_correctly():
    assert copy.error_summary(1) == "Fix 1 error before signing."
    assert copy.error_summary(3) == "Fix 3 errors before signing."


def test_the_summary_refuses_a_nonsense_count():
    with pytest.raises(ValueError):
        copy.error_summary(0)
    with pytest.raises(ValueError):
        copy.error_summary(1.5)


def test_every_submitted_field_has_a_label_help_and_placeholder():
    submitted = {"line_of_business", "jurisdiction", "coverages",
                 "window_opens", "window_closes", "thesis"}
    assert submitted <= set(copy.FIELD_LABEL)
    assert submitted <= set(copy.FIELD_HELP)
    assert submitted <= set(copy.FIELD_PLACEHOLDER), (
        'ux-patterns.md: "No field should render without a placeholder"')


def test_a_list_entry_prompt_is_not_an_example_value():
    """The shipped defect, pinned. `LocksmithTextListWidget` was handed
    `FIELD_PLACEHOLDER["coverages"]` while it still floated its text into the
    border as the field's NAME, so the example value "BI" became the field's
    label, beside the real "Coverages *" above it. The page now also passes
    `float_label=False`, but the copy rule outlives that: this slot names what is
    being ADDED, and an example value in it is wrong either way -- floated as a
    name, or sat in the box implying the field is already filled."""
    for name, prompt in copy.FIELD_ENTRY_PROMPT.items():
        assert prompt != copy.FIELD_PLACEHOLDER.get(name), (
            f"FIELD_ENTRY_PROMPT[{name!r}] is the example VALUE. This slot names "
            "the thing being added, singular.")
        assert prompt != copy.FIELD_LABEL.get(name), (
            f"FIELD_ENTRY_PROMPT[{name!r}] repeats the outer field label. The outer "
            "one names the list, this one names a single entry to add.")


def test_the_coverages_help_denies_a_fixed_list():
    """A CUO reading "(BI, PD, COMP)" went looking for the autocomplete. There is
    no allowed set -- the payload schema puts no `enum` on `coverages.items`, only
    a shape -- so the copy has to say so rather than leave examples looking
    exhaustive."""
    help_text = copy.FIELD_HELP["coverages"].lower()
    assert "no fixed list" in help_text or "not a fixed list" in help_text, (
        f"coverages help does not deny a fixed list: {copy.FIELD_HELP['coverages']!r}")
    assert "for example" in help_text or "e.g." in help_text, (
        "the example codes must be marked as examples")


def test_the_intro_states_both_irreversible_facts():
    """The defect this copy replaces was prose that read as PRIVATE. Both facts
    must survive any future edit for brevity."""
    intro = " ".join(copy.PAGE_INTRO).lower()
    assert "edited" in intro and "permanent" in intro
    assert "anyone" in intro or "publish" in intro


def test_the_caution_says_it_cannot_be_undone_in_some_form():
    """Reads the lede AND the body: the caution is two strings now and "final"
    lives in the lede, so checking one half would let the other be emptied."""
    caution = f"{copy.REVIEW_CAUTION_HEAD} {copy.REVIEW_CAUTION}".lower()
    assert "final" in caution or "cannot be undone" in caution
    assert "never be edited" in caution or "cannot be edited" in caution


def test_field_order_covers_exactly_the_schema_s_submitted_fields():
    """The canary for the decision to keep order out of the schema: if the schema
    gains or loses a submitted field, this fails rather than the form silently
    dropping a control or rendering an unlabelled one."""
    from locksmith.core.branding import egf_local_dir
    from locksmith.plugins.cuo.schema_source import load_mandate_schema

    schema = load_mandate_schema(egf_local_dir())
    assert set(copy.FIELD_ORDER) == set(schema.fields), (
        f"FIELD_ORDER and the schema disagree: "
        f"only-in-order={set(copy.FIELD_ORDER) - set(schema.fields)}, "
        f"only-in-schema={set(schema.fields) - set(copy.FIELD_ORDER)}")


def test_field_order_is_not_alphabetical():
    """An alphabetized FIELD_ORDER would mean somebody sorted it by accident -- the
    exact drift this constant exists to resist."""
    assert list(copy.FIELD_ORDER) != sorted(copy.FIELD_ORDER)
    assert copy.FIELD_ORDER[0] == "line_of_business"


def test_the_enum_error_lists_what_is_allowed():
    message = copy.enum_error("line_of_business", "automobile", ("auto", "property"))
    assert "automobile" in message and "auto" in message


def test_required_errors_exist_for_every_field_name_used():
    for field in copy.FIELD_ORDER:
        message = copy.required_error(field)
        assert message and message[0].isupper() and message.endswith(".")


def test_the_forbidden_word_scan_actually_reaches_the_required_messages():
    """The scan skips underscore-prefixed attributes, which once hid REQUIRED --
    six strings the form renders directly -- from every policy test in this file.
    Assert the scan sees them, by name, so a future rename cannot quietly re-hide
    them."""
    scanned = {name for name, _ in _all_strings()}
    for field in copy.FIELD_ORDER:
        assert f"REQUIRED[{field}]" in scanned, (
            f"REQUIRED[{field}] is not reached by _all_strings(), so no forbidden-"
            f"word, shouting or token check applies to it")


def test_there_is_a_required_message_for_every_field():
    assert set(copy.REQUIRED) == set(copy.FIELD_ORDER)
