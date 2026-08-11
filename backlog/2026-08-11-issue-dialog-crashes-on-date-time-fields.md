# Issue-credential dialog raises AttributeError on any `format: date-time` field

**Status:** backlog · **Raised:** 2026-08-11 · **Priority:** high (crash on a shipped path)
**Found by:** the call-site audit for
`2026-08-11-no-seam-for-user-facing-datetime-formatting.md`. Filed separately
because it is a live defect, not a cleanup — it should not land inside a
formatting refactor commit.

## What we saw

`ui/vault/credentials/issued/issue.py:983`, in `_get_field_value`:

```python
if field_type == 'string' and field_format == 'date-time':
    if hasattr(widget, 'input_widget'):
        dt = widget.input_widget.dateTime()          # -> QDateTime
        return dt.strftime("%b %d, %Y %I:%M %p")     # comment says "ISO 8601 format"
```

`QDateTime` is a Qt type with no `.strftime`. Reproduced directly:

```
AttributeError: 'PySide6.QtCore.QDateTime' object has no attribute 'strftime'
```

The path is reachable. The date-time branch of `_create_field_widget`
(`issue.py:719-752`) wraps the `QDateTimeEdit` in a container and sets
`container.input_widget = widget`, so the `hasattr` guard passes and the
`return None` fallback is never taken.

## Two bugs stacked at one line

1. **The crash.** Qt formatting vocabulary (`QDateTime.toString`) and Python's
   (`datetime.strftime`) were confused. Nothing catches it because no test
   exercises `_get_field_value` with a date-time field.
2. **Display format into an ACDC payload.** Even working, `"%b %d, %Y %I:%M %p"`
   yields `Aug 11, 2026 1:05 PM` — not ISO 8601, whatever the comment claims —
   and this value goes into a credential attribute whose schema says
   `format: date-time`. The correct output is
   `dt.toPython().isoformat()` (or `dt.toString(Qt.ISODate)`), which is the
   schema's business, not the UI's preference. See the display/payload boundary
   `plugins/cuo/date_field.py` already draws correctly.

## Why it has not bitten yet

`_parse_schema_fields` excludes `{'d', 'i', 'dt', 'u'}` (`issue.py:384`), so the
auto-populated `dt` never reaches the form. Role credentials issued today
(Actuary Role, CUO Role) carry no other date-time field, and the role plugins
use their own purpose-built forms rather than this generic dialog.

But the shipped Usurance EGF has **five form-reachable `date-time` fields**
across four schemas — `assembled_at`, `received_at`, `declared_at`,
`attested_at`, `observed_at` — plus 15 `format: date` fields, which take the
default string branch and want their own look. Anyone issuing one of those
through the generic dialog hits the crash.

## Fix

Return ISO from the Qt widget, and test the extractor per field type:

```python
return widget.input_widget.dateTime().toPython().isoformat()
```

A test over `_get_field_value` with each `field_def` shape it claims to handle
(`date-time`, `array`, `number`, `integer`, `boolean`, plain string) is what was
missing; the function is a pure static method taking a widget and a dict, so it
is cheap to pin — the reproduction above is six lines.

Worth checking `format: date` in the same pass: it currently falls through to the
default string branch, so a schema `date` field is a free-text box that can
produce a non-ISO value with no validation at all.
