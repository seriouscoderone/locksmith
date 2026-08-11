# No seam for user-facing date/time formatting — 17 call sites, 3 mechanisms, 5 formats

**Status:** backlog · **Raised:** 2026-08-11 · **Priority:** medium
**Prompted by:** the 0.4.0 Windows outage in `actuary/page.py` (`%-I` →
`ValueError: Invalid format string` → page never constructed → role read ACTIVE
with no workspace). Fixed at the single site; the seam it argues for is this item.
**Guard already in place:** `tests/test_strftime_portability.py` fails the build on
any `%-`/`%#` padding code in `src/`. That stops the *portability* class of this
bug. It does nothing about the duplication or the inconsistency below.

## What we saw

Formatting "a moment in time, for a human" is open-coded at every call site. A
survey of `src/` finds **17 `strftime` calls** and at least **five formats for
the same concept**:

| Format | Sites | Where |
|---|---|---|
| `%b %d, %Y %I:%M %p` | 8 | credentials issued/received, notifications, accept_grant, accept_rotation, accept_multisig, turret/handling |
| `%Y-%m-%d %I:%M:%S %p` | 2 | `ui/toolkit/widgets/panels.py` |
| `%Y-%m-%d %I:%M %p` | 2 | `core/remoting.py` |
| `%Y-%m-%d %H:%M:%S` | 1 | `ui/vault/remotes/view.py` |
| `%Y-%m-%d %H:%M UTC` | 1 | `ui/vault/settings/updates_widget.py` |
| `MM/DD/YYYY h:mm A` | 1 | `plugins/actuary/page.py` (`_stamp`) |

And three *mechanisms*, which is the part that makes this a seam problem rather
than a find-and-replace:

1. **Python `strftime`** — the 16 sites above. Delegates to the platform C
   library, which is why `%-I` was a Windows-only crash.
2. **Qt `QDate.toString("MM/dd/yyyy")`** — `plugins/cuo/date_field.py`. Different
   escape vocabulary entirely (`yyyy`, not `%Y`), platform-independent, and
   already correctly separates display format from ISO payload.
3. **Hand-rolled f-string** — `plugins/actuary/page.py:_stamp`, added by the fix,
   because the documented format is not expressible in portable `strftime`.

The actuary comment cites `ux-patterns.md:390` as the authority for
`MM/DD/YYYY h:mm A`. **That file does not exist** — not in this repo, not in
`~/code/ugard`. So the one site that followed a written convention followed one
nobody else can read, while the *de facto* convention (`%b %d, %Y %I:%M %p`,
8 sites) is written down nowhere at all.

**The audit already found one live defect.** `issue.py:983` calls `.strftime()`
on a Qt `QDateTime` (`AttributeError`) *and* would write a display format into an
ACDC `date-time` attribute if it worked. Filed separately as
`2026-08-11-issue-dialog-crashes-on-date-time-fields.md` — fix it on its own,
before this refactor, so a crash fix is not buried in a mechanical sweep.

## Why it matters beyond tidiness

- **The failure is invisible where it is written.** Every dev machine and the
  macOS CI runner accept glibc extensions. Only a Windows user running the
  shipped app finds them, and by then it presents as "the role has no workspace"
  — nothing about the symptom points at a date format.
- **Blast radius is set by call position, not by importance.** The same one-line
  mistake is a cosmetic wrong-looking date in a list row, and a dead feature when
  it happens to sit in a constructor. `_scan_for_mandates` is called from
  `__init__`, so the throw escaped through `get_pages` and killed the page.
- **Two brands, one codebase.** A role page is the brand's product surface. Three
  timestamp dialects across the roles is visible to the customer.

## The seam

A formatting module that owns *rendering a moment for a human*, keyed by
**intent** rather than by format string. Sketch:

```python
# src/locksmith/ui/formatting.py  (framework, not plugin — roles must share it)

def timestamp(when: dt.datetime) -> str:      # "Aug 11, 2026 1:05 PM"  (the 8-site default)
def timestamp_numeric(when) -> str:           # "08/11/2026 1:05 PM"    (actuary heartbeat)
def date_only(when) -> str:                   # "Aug 11, 2026"
def utc_stamp(when) -> str:                   # "2026-08-11 13:05 UTC"  (logs/updates)
def relative(when, *, now=None) -> str:       # "2 minutes ago"          (net-new, wanted by heartbeats)
```

Properties the seam must have, each earned by something above:

- **Named intents, not format strings.** A caller asking for
  `timestamp_numeric(x)` cannot introduce a sixth format. That is the actual
  defect — not that `%-I` is wrong, but that every call site gets to decide.
- **No platform-specific codes, structurally.** Unpadded hours are built as
  `now.hour % 12 or 12`, never `%-I`/`%#I`. One implementation to get right, and
  `test_strftime_portability.py` keeps guarding the perimeter.
- **Display and payload stay separate.** `date_field.py` already draws this line
  correctly (`MM/dd/yyyy` on screen, ISO in the payload) and must keep it — these
  functions are for *display only*. Nothing here may ever produce a value that
  reaches an ACDC attribute, where the format is the schema's business
  (`format: date` is ISO, full stop). Worth an explicit note in the module
  docstring, because "we have a date helper now" is exactly how an ISO payload
  starts getting rendered through a display formatter.
- **Framework-level, so plugins can reach it.** It belongs next to
  `ui/colors.py` and `ui/styles.py`, which role plugins already import. A helper
  living inside one role plugin would be copied into the next one.
- **UTC vs local made explicit at the call site.** `updates_widget` is the only
  site that says "UTC" and it is the only one showing a UTC value; the rest show
  naive local time. Two functions, named, rather than a `utc=True` flag nobody
  passes.

## Not in scope for this item

The three role pages (`actuary`, `cuo`, `product_designer`) each build their own
`QTimer` poll loop, and only `actuary` renders a "Last checked" heartbeat from
it. A shared *polling role page* base — poll cadence, heartbeat label, empty
state — is a real second seam, and a larger one, since it touches page lifecycle
rather than a pure function. Filed here only so the two are not conflated: this
item is the pure-function seam and can land on its own.

## Migration

Mechanical and safely incremental — no behavior change for the 8 sites that
already share a format:

1. Add `ui/formatting.py` with the intents above, unit-tested at the hour
   boundaries (midnight → 12 AM, noon → 12 PM) the way
   `test_the_heartbeat_stamp_is_platform_independent` does.
2. Convert the 8 `%b %d, %Y %I:%M %p` sites to `timestamp()`. Pure refactor.
3. Convert the stragglers, deciding per site whether the difference was
   intentional (`updates_widget`'s UTC: yes) or drift (`panels.py`'s seconds:
   probably not).
4. Point `actuary/page.py:_stamp` at `timestamp_numeric` and delete it.
5. Write the convention down — in the module docstring, which is the one place
   that cannot go missing the way `ux-patterns.md` did.
